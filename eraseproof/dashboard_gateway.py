"""Local-only dashboard gateway: opaque sessions, role enforcement and bounded real research jobs."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Literal
from uuid import UUID, uuid4
import hashlib
import json
import os
import re
import secrets
import sqlite3
import subprocess
import sys
import time
import zipfile
import httpx
from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from eraseproof.research_models import catalog
from eraseproof.research_report import load
from eraseproof.research_metrics import summarize
from eraseproof.deletion_models import SubmitDeletion
from eraseproof.verification_models import StartVerification

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "work/dashboard"
ROLES = ("readonly", "operator", "research")
SERVICES = ("customer", "order", "cache", "search", "analytics", "deletion", "verification")
app = FastAPI(title="EraseProof X dashboard gateway", docs_url=None, redoc_url=None)
POOL = ThreadPoolExecutor(max_workers=2)
JOB_LOCK = Lock()
LOGIN_LOCK = Lock()
LOGIN_ATTEMPTS: dict[str, list[float]] = {}


@contextmanager
def sessions():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with sqlite3.connect(STATE / "sessions.db", timeout=5) as db:
        db.row_factory = sqlite3.Row
        db.execute(
            "CREATE TABLE IF NOT EXISTS sessions (digest text PRIMARY KEY, role text NOT NULL, csrf text NOT NULL, expires real NOT NULL)"
        )
        db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
        yield db


def origin(request: Request):
    configured = os.getenv("DASHBOARD_ORIGIN", "http://127.0.0.1:3000").rstrip("/")
    if (
        request.headers.get("origin") != configured
        or request.headers.get("sec-fetch-site") == "cross-site"
    ):
        raise HTTPException(403, "Same-origin access required")


def current(request: Request):
    token = request.cookies.get("eraseproof_session", "")
    with sessions() as db:
        row = db.execute(
            "SELECT * FROM sessions WHERE digest=? AND expires>?",
            (hashlib.sha256(token.encode()).hexdigest(), time.time()),
        ).fetchone()
    if not token or not row:
        raise HTTPException(401, "Session expired. Sign in again.")
    return dict(row)


def write(request: Request, session=Depends(current)):
    origin(request)
    if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), session["csrf"]):
        raise HTTPException(403, "Request verification failed")
    return session


@app.middleware("http")
async def security(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    return response


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["readonly", "operator", "research"]
    password: str = Field(min_length=1, max_length=256)


@app.post("/api/session")
def login(body: Login, request: Request, response: Response):
    origin(request)
    host = request.client.host if request.client else "unknown"
    with LOGIN_LOCK:
        attempts = [t for t in LOGIN_ATTEMPTS.get(host, []) if t > time.time() - 60]
        if len(attempts) >= 10:
            raise HTTPException(429, "Too many sign-in attempts; wait one minute")
        if len(LOGIN_ATTEMPTS) > 1000:
            LOGIN_ATTEMPTS.clear()
        LOGIN_ATTEMPTS[host] = attempts + [time.time()]
    expected = os.getenv(f"DASHBOARD_{body.role.upper()}_PASSWORD", "")
    actual_hash = hashlib.scrypt(
        body.password.encode(), salt=b"eraseproof-dashboard-auth-v1", n=16384, r=8, p=1
    )
    expected_hash = hashlib.scrypt(
        (expected or "disabled").encode(), salt=b"eraseproof-dashboard-auth-v1", n=16384, r=8, p=1
    )
    if len(expected) < 24 or not secrets.compare_digest(actual_hash, expected_hash):
        raise HTTPException(401, "Invalid credentials or role disabled")
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with sessions() as db:
        db.execute(
            "INSERT INTO sessions VALUES(?,?,?,?)",
            (hashlib.sha256(token.encode()).hexdigest(), body.role, csrf, time.time() + 28800),
        )
    response.set_cookie(
        "eraseproof_session",
        token,
        httponly=True,
        samesite="strict",
        secure=os.getenv("DASHBOARD_SECURE_COOKIE") == "1",
        max_age=28800,
        path="/",
    )
    return {
        "role": body.role,
        "csrf": csrf,
        "research_enabled": os.getenv("DASHBOARD_ENABLE_RESEARCH") == "1",
    }


@app.get("/api/session")
def identity(session=Depends(current)):
    return {
        "role": session["role"],
        "csrf": session["csrf"],
        "research_enabled": os.getenv("DASHBOARD_ENABLE_RESEARCH") == "1",
    }


@app.delete("/api/session")
def logout(response: Response, session=Depends(write)):
    with sessions() as db:
        db.execute("DELETE FROM sessions WHERE digest=?", (session["digest"],))
    response.delete_cookie("eraseproof_session", path="/")
    return {"signed_out": True}


def service_origin(service: str):
    return os.getenv(
        f"DASHBOARD_{service.upper()}_ORIGIN", f"http://127.0.0.1:{8000 + SERVICES.index(service)}"
    ).rstrip("/")


async def upstream(service, method, path, params=None, body=None):
    credential = (
        "deletion"
        if service == "deletion"
        else "research"
        if "/research/" in path
        else "verification"
        if service == "verification"
        else "inspection"
    )
    token = os.getenv(f"{credential.upper()}_TOKEN", "")
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(float(os.getenv("DASHBOARD_UPSTREAM_TIMEOUT", "12"))),
            follow_redirects=False,
        ) as client:
            result = await client.request(
                method,
                service_origin(service) + path,
                params=params,
                json=body,
                headers={
                    f"X-{credential.title()}-Token": token,
                    "X-Operator-Token": os.getenv("OPERATOR_TOKEN", ""),
                },
            )
        if result.status_code >= 400:
            detail = "Backend rejected the request"
            try:
                value = result.json().get("detail")
                if isinstance(value, str):
                    detail = value[:200]
            except ValueError:
                pass
            raise HTTPException(result.status_code, detail)
        return result.json()
    except httpx.TimeoutException:
        raise HTTPException(
            504, "Backend timed out; outcome is unknown. Refresh before retrying a write."
        ) from None
    except (httpx.RequestError, ValueError):
        raise HTTPException(
            503, "Backend unavailable. No successful outcome has been assumed."
        ) from None


READ_PATHS = {
    "customer": r"/v1/(dashboard/(snapshot|customers|deletions|verifications)|customers/[a-f0-9-]{36}(/propagation)?)",
    "deletion": r"/v1/deletions(/metrics|/[a-f0-9-]{36}(/events)?)?",
    "verification": r"/v1/(deletions/[a-f0-9-]{36}/verifications|verifications/[a-f0-9-]{36}(/(report|evidence|timeline))?|research/(scenarios|experiments(/[a-f0-9-]{36}(/(trials|summary))?)?))",
    "cache": r"/v1/inspect/customers/[a-f0-9-]{36}",
    "search": r"/v1/inspect/customers/[a-f0-9-]{36}",
    "analytics": r"/v1/inspect/customers/[a-f0-9-]{36}",
}


@app.get("/api/live/{service}/{path:path}")
async def read_proxy(service: str, path: str, request: Request, session=Depends(current)):
    path = "/" + path
    if service not in READ_PATHS or not re.fullmatch(READ_PATHS[service], path):
        raise HTTPException(404, "Unsupported dashboard read operation")
    if len(str(request.query_params)) > 1000:
        raise HTTPException(422, "Query too large")
    return await upstream(service, "GET", path, params=request.query_params)


class CustomerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100, pattern=r"^Synthetic [A-Za-z0-9 -]+$")
    email: str = Field(max_length=200, pattern=r"^[a-zA-Z0-9._+-]+@example\.invalid$")


class OrderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: UUID
    amount_cents: int = Field(gt=0, le=100000000)
    currency: Literal["USD", "INR", "EUR"] = "USD"


@app.post("/api/live/{service}/{path:path}")
async def write_proxy(service: str, path: str, request: Request, session=Depends(write)):
    if session["role"] == "readonly":
        raise HTTPException(403, "Read-only users cannot mutate data")
    if len(await request.body()) > 4096:
        raise HTTPException(413, "Request too large")
    path = "/" + path
    try:
        body = await request.json()
        if service == "customer" and path == "/v1/customers":
            body = CustomerInput.model_validate(body).model_dump(mode="json")
        elif service == "order" and path == "/v1/orders":
            body = OrderInput.model_validate(body).model_dump(mode="json")
        elif service == "deletion" and path == "/v1/deletions":
            body = SubmitDeletion.model_validate(body).model_dump(mode="json")
        elif service == "deletion" and re.fullmatch(r"/v1/deletions/[a-f0-9-]{36}/retry", path):
            body = {}
        elif service == "verification" and re.fullmatch(
            r"/v1/deletions/[a-f0-9-]{36}/verifications", path
        ):
            body = StartVerification.model_validate(body).model_dump(mode="json")
        else:
            raise HTTPException(404, "Unsupported dashboard mutation")
    except (ValueError, TypeError):
        raise HTTPException(
            422, "Invalid operation fields; only synthetic inputs are accepted"
        ) from None
    return JSONResponse(
        await upstream(service, "POST", path, body=body),
        status_code=202 if service in ("deletion", "verification") else 201,
    )


@app.get("/api/health")
async def health(session=Depends(current)):
    import asyncio

    async def probe(name):
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                response = await client.get(service_origin(name) + "/health/ready")
                return {
                    "service": name,
                    "state": "ready" if response.status_code == 200 else "unavailable",
                    "observed_at_unix": time.time(),
                }
        except httpx.HTTPError:
            return {"service": name, "state": "unavailable", "observed_at_unix": time.time()}

    return {
        "items": await asyncio.gather(*(probe(name) for name in SERVICES)),
        "basis": "API readiness probes; worker/broker internals are not individually probed",
    }


HISTORIES = {"phase4-final": "61dd8e8-final", "phase4-initial": "4959be5-initial"}


def historical(key):
    if key not in HISTORIES:
        raise HTTPException(404, "Historical dataset not found")
    folder = ROOT / "research/phase-4/results" / HISTORIES[key]
    return folder, load(folder / "dataset.json")


@app.get("/api/policy")
def policy(session=Depends(current)):
    return json.loads((ROOT / "policies/scope-v1.json").read_text())


@app.get("/api/history")
def histories(session=Depends(current)):
    result = []
    for key in HISTORIES:
        _, data = historical(key)
        result.append(
            {
                "id": key,
                "experiment": data["experiment"],
                "summary": summarize(data["trials"]),
                "historical": True,
            }
        )
    return {"items": result}


@app.get("/api/history/{key}")
def history(key: str, session=Depends(current)):
    _, data = historical(key)
    return {
        "experiment": data["experiment"],
        "summary": summarize(data["trials"]),
        "trials": data["trials"],
        "historical": True,
    }


@app.get("/api/history/{key}/evidence/{run_id}")
def historical_evidence(key: str, run_id: UUID, session=Depends(current)):
    folder, data = historical(key)
    if not any(
        str(run_id) == p.get("verification_id") for t in data["trials"] for p in t["phases"]
    ):
        raise HTTPException(404, "Evidence is outside this dataset")
    with zipfile.ZipFile(folder / "evidence.zip") as archive:
        report = json.loads(archive.read(f"evidence/{run_id}.json"))
    return report


class ResearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: str = Field(max_length=60)
    seed: int = Field(default=101, ge=0, le=2147483647)
    acknowledge_isolated: Literal[True]


def save_job(folder: Path, body):
    temporary = folder / "status.tmp"
    temporary.write_text(json.dumps(body, indent=2))
    temporary.replace(folder / "status.json")


def run_job(folder, body, project):
    try:
        body["state"] = "RUNNING"
        save_job(folder, body)
        with (folder / "runner.log").open("w") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "eraseproof.research_runner",
                    "--project",
                    project,
                    "--scenario",
                    body["scenario"],
                    "--seed",
                    str(body["seed"]),
                    "--tier",
                    "small",
                    "--max-seconds",
                    "180",
                    "--output",
                    str(folder / "results"),
                ],
                cwd=ROOT,
                env={**os.environ, "ERASEPROOF_RESEARCH_FAULTS": "1"},
                stdout=log,
                stderr=log,
            )
            body["pid"] = process.pid
            save_job(folder, body)
            try:
                code = process.wait(timeout=250)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                code = 124
        body["state"] = "COMPLETED" if code == 0 else "FAILED"
        body["exit_code"] = code
    except Exception as exc:
        body["state"] = "FAILED"
        body["error_code"] = type(exc).__name__
    finally:
        body["finished_at_unix"] = time.time()
        save_job(folder, body)
        JOB_LOCK.release()


@app.post("/api/research/jobs", status_code=202)
def launch(body: ResearchInput, session=Depends(write)):
    if session["role"] != "research":
        raise HTTPException(403, "Research administrator role required")
    if os.getenv("DASHBOARD_ENABLE_RESEARCH") != "1" or os.getenv("APP_ENV") != "demo":
        raise HTTPException(403, "Research controls are disabled on this host")
    _, registry = catalog()
    if body.scenario not in registry:
        raise HTTPException(422, "Unknown versioned scenario")
    if not JOB_LOCK.acquire(blocking=False):
        raise HTTPException(409, "A research job is already running")
    try:
        from eraseproof.research_harness import Harness

        project = os.getenv("DASHBOARD_RESEARCH_PROJECT", "eraseproof-research")
        # No fault is triggered until all real Phase 4 local-engine/project checks pass.
        harness = Harness(project, maximum_seconds=30)
        harness.client.close()
        folder = STATE / "jobs" / str(uuid4())
        folder.mkdir(parents=True)
        job = {
            "id": folder.name,
            "scenario": body.scenario,
            "seed": body.seed,
            "state": "QUEUED",
            "created_at_unix": time.time(),
            "project": project,
        }
        save_job(folder, job)
        POOL.submit(run_job, folder, job, project)
        return {**job}
    except Exception:
        JOB_LOCK.release()
        raise HTTPException(
            409, "Research isolation validation failed. No scenario was started."
        ) from None


@app.get("/api/research/scenarios")
def scenarios(session=Depends(current)):
    version, registry = catalog()
    return {"version": version, "items": [s.model_dump() for s in registry.values()]}


@app.get("/api/research/jobs")
def jobs(session=Depends(current)):
    paths = sorted(
        (STATE / "jobs").glob("*/status.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )[:50]
    return {"items": [json.loads(p.read_text()) for p in paths]}


@app.get("/api/research/jobs/{job_id}")
def job(job_id: UUID, session=Depends(current)):
    folder = STATE / "jobs" / str(job_id)
    if not (folder / "status.json").exists():
        raise HTTPException(404, "Job not found")
    value = json.loads((folder / "status.json").read_text())
    if value["state"] in ("QUEUED", "RUNNING") and value.get("pid"):
        try:
            os.kill(value["pid"], 0)
        except ProcessLookupError:
            value["state"] = "INTERRUPTED"
    dataset = folder / "results/dataset.json"
    if dataset.exists():
        data = load(dataset)
        value["dataset"] = {
            "experiment": data["experiment"],
            "summary": summarize(data["trials"]),
            "trials": data["trials"],
        }
    return value


@app.get("/api/research/jobs/{job_id}/evidence/{run_id}")
def job_evidence(job_id: UUID, run_id: UUID, session=Depends(current)):
    folder = STATE / "jobs" / str(job_id) / "results"
    if not (folder / "dataset.json").exists():
        raise HTTPException(404, "No trial evidence yet")
    data = load(folder / "dataset.json")
    if not any(
        str(run_id) == p.get("verification_id") for t in data["trials"] for p in t["phases"]
    ):
        raise HTTPException(404, "Evidence outside this job")
    return json.loads((folder / "evidence" / f"{run_id}.json").read_text())


# Serve only the built SPA. No work/ files, credentials, or arbitrary repository paths are exposed.
@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "API route not found")
    dist = ROOT / "frontend/dist"
    resolved = (dist / path).resolve()
    if resolved.is_relative_to(dist.resolve()) and resolved.is_file():
        return FileResponse(resolved)
    if (dist / "index.html").exists():
        return FileResponse(dist / "index.html")
    raise HTTPException(503, "Dashboard assets are not built. Run npm run build in frontend.")
