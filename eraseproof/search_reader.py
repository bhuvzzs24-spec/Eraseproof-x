"""Authenticated read-only OpenSearch boundary on a private network; no admin/write route."""

import os
import re
import secrets
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health/live")
def live():
    return {"status": "alive"}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def read(path: str, request: Request):
    from base64 import b64decode

    expected = os.getenv("VERIFIER_SEARCH_PASSWORD", "")
    try:
        actual = b64decode(
            request.headers.get("authorization", "").removeprefix("Basic "), validate=True
        ).decode()
    except (ValueError, UnicodeDecodeError):
        actual = ""
    if len(expected) < 32 or not secrets.compare_digest(actual, "verification:" + expected):
        return JSONResponse({"detail": "Read credential required"}, status_code=403)
    document = request.method == "GET" and re.fullmatch(r"customers/_doc/[a-f0-9-]{36}", path)
    search = request.method == "POST" and path == "customers/_search"
    if not (document or search) or request.query_params:
        return JSONResponse({"detail": "Read operation not allowed"}, status_code=403)
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 8192:
            return JSONResponse({"detail": "Read query too large"}, status_code=413)
    if search:
        import json

        try:
            query = json.loads(raw)
            if (
                set(query) != {"size", "track_total_hits", "version", "query"}
                or query["size"] != 200
                or query["track_total_hits"] is not True
                or query["version"] is not True
            ):
                raise ValueError("unsupported read")
            clause = query["query"]["bool"]
            if (
                set(clause) != {"should", "minimum_should_match"}
                or clause["minimum_should_match"] != 1
                or not 1 <= len(clause["should"]) <= 30
            ):
                raise ValueError("unsupported query")
            for item in clause["should"]:
                if list(item) == ["ids"]:
                    identifiers = item["ids"]["values"]
                    if len(identifiers) != 1 or not re.fullmatch(r"[a-f0-9-]{36}", identifiers[0]):
                        raise ValueError("invalid identifier")
                elif list(item) == ["term"]:
                    field, value = next(iter(item["term"].items()))
                    if (
                        field
                        not in {
                            "id",
                            "id.keyword",
                            "customer_id",
                            "customer_id.keyword",
                            "subject_id",
                            "subject_id.keyword",
                            "data.id",
                            "data.id.keyword",
                            "data.customer_id",
                            "data.customer_id.keyword",
                        }
                        or not isinstance(value, str)
                        or not re.fullmatch(r"[a-f0-9-]{36}", value)
                    ):
                        raise ValueError("invalid identifier field")
                else:
                    raise ValueError("scripts and arbitrary searches are forbidden")
        except (ValueError, KeyError, TypeError, IndexError, AttributeError):
            return JSONResponse(
                {"detail": "Only the declared identifier probe is allowed"}, status_code=422
            )
    try:
        async with httpx.AsyncClient(timeout=3, follow_redirects=False) as client:
            response = await client.request(
                request.method,
                "http://opensearch:9200/" + path,
                content=bytes(raw),
                headers={"Content-Type": "application/json"},
            )
        return JSONResponse(response.json(), status_code=response.status_code)
    except (httpx.HTTPError, ValueError):
        return JSONResponse({"detail": "Search read unavailable"}, status_code=503)
