import { useEffect, useState, useRef, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowRight,
  Boxes,
  ChevronRight,
  Command,
  Database,
  FileCheck2,
  FlaskConical,
  Gauge,
  GitBranch,
  HelpCircle,
  Hexagon,
  LogOut,
  Menu,
  Moon,
  RefreshCw,
  Search,
  Shield,
  Sun,
  TriangleAlert,
  Workflow,
} from "lucide-react";
import { api, ApiError } from "./api";
import { useApi } from "./queries";
import { ErrorNotice, Loading, WorkspaceBoundary } from "./ui";
import {
  Overview,
  Topology,
  Customers,
  Deletions,
  Verification,
} from "./operations";
import {
  Investigator,
  FaultStudio,
  Research,
  EvidenceExplorer,
} from "./research";
import type { Session, Navigate, Health } from "./types";
const navigation = [
  ["overview", "Command center", Gauge],
  ["topology", "Data topology", GitBranch],
  ["customers", "Customer data", Database],
  ["deletions", "Deletion operations", Workflow],
  ["verification", "Verification lab", Shield],
  ["investigator", "Failure investigator", TriangleAlert],
  ["faults", "Fault injection studio", FlaskConical],
  ["research", "Research benchmarks", Activity],
  ["evidence", "Evidence explorer", FileCheck2],
] as const;
function Login({ onSuccess }: { onSuccess: (session: Session) => void }) {
  const [role, setRole] = useState<Session["role"]>("readonly");
  const [password, setPassword] = useState("");
  const login = useMutation({
    mutationFn: () =>
      api<Session>("/session", {
        method: "POST",
        body: JSON.stringify({ role, password }),
      }),
    onSuccess,
  });
  function submit(e: FormEvent) {
    e.preventDefault();
    login.mutate();
  }
  return (
    <main className="login-layout">
      <section className="login-story">
        <div className="brand">
          <Hexagon size={30} />
          <span>
            ERASEPROOF <b>X</b>
          </span>
        </div>
        <p className="eyebrow">Distributed deletion intelligence</p>
        <h1>
          A completed task.
          <br />
          An independent answer.
        </h1>
        <p>
          Follow the data. Challenge reported success. Inspect what the stores
          actually show.
        </p>
        <div
          className="login-diagram"
          aria-label="Architecture metadata: reported completion is checked independently"
        >
          <span>
            <Workflow />
            Deletion orchestrator<small>Operational claim</small>
          </span>
          <ArrowRight />
          <span>
            <Shield />
            Independent verifier<small>Store-level observations</small>
          </span>
        </div>
        <p className="login-note">
          <Shield size={16} />
          Synthetic lab · Scoped evidence · No public fault controls
        </p>
      </section>
      <section className="login-card">
        <p className="eyebrow">Engineering workspace</p>
        <h2>Sign in to EraseProof X</h2>
        <p>Choose your authorized role to access the local workspace.</p>
        <form onSubmit={submit}>
          <label>
            Access role
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as Session["role"])}
            >
              <option value="readonly">Read-only observer</option>
              <option value="operator">Authorized operator</option>
              <option value="research">Research administrator</option>
            </select>
          </label>
          <label>
            Role password
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              maxLength={256}
            />
          </label>
          {login.error ? <ErrorNotice error={login.error} /> : null}
          <button className="button wide" disabled={login.isPending}>
            {login.isPending ? "Verifying access…" : "Enter workspace"}
            <ArrowRight size={16} />
          </button>
        </form>
        <div className="notice">
          <Shield size={18} />
          <p>
            Credentials remain on this host. Sessions use an HttpOnly cookie;
            privileged backend keys never enter the browser.
          </p>
        </div>
        <p className="subtle">
          Local setup: use the role password generated in{" "}
          <code>.dashboard.env</code> on the trusted host.
        </p>
      </section>
    </main>
  );
}
export default function App() {
  const client = useQueryClient();
  const sessionQuery = useApi<Session | null>("/session");
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);
  const [location, setLocation] = useState(
    () => new URLSearchParams(window.location.search),
  );
  const [navOpen, setNavOpen] = useState(false);
  const [search, setSearch] = useState("");
  const help = useRef<HTMLDialogElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem("eraseproof-theme") || "dark";
    } catch {
      return "dark";
    }
  });
  useEffect(() => {
    if (sessionQuery.data) {
      setSession(sessionQuery.data);
      setReady(true);
    } else if (
      sessionQuery.error instanceof ApiError &&
      sessionQuery.error.status === 401
    ) {
      setSession(null);
      setReady(true);
    }
  }, [sessionQuery.data, sessionQuery.error]);
  useEffect(() => {
    const expire = () => {
      setSession(null);
      client.clear();
    };
    window.addEventListener("eraseproof-session-expired", expire);
    return () =>
      window.removeEventListener("eraseproof-session-expired", expire);
  }, [client]);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("eraseproof-theme", theme);
    } catch {
      /* Theme storage is optional. */
    }
  }, [theme]);
  useEffect(() => {
    const read = () => setLocation(new URLSearchParams(window.location.search));
    window.addEventListener("popstate", read);
    return () => window.removeEventListener("popstate", read);
  }, []);
  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if (
        (event.metaKey || event.ctrlKey) &&
        event.key.toLowerCase() === "k" &&
        searchRef.current?.offsetParent !== null
      ) {
        event.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, []);
  const workspace = navigation.some((n) => n[0] === location.get("workspace"))
    ? location.get("workspace")!
    : "overview";
  const title = navigation.find((n) => n[0] === workspace)![1];
  useEffect(() => {
    document.title = `${title} · EraseProof X`;
  }, [title]);
  const navigate: Navigate = (next, params = {}) => {
    const query = new URLSearchParams({ workspace: next, ...params });
    history.pushState(null, "", "?" + query);
    setLocation(query);
    setNavOpen(false);
    window.scrollTo(0, 0);
  };
  const health = useApi<Health>(session ? "/health" : null, 15000);
  const logout = useMutation({
    mutationFn: () =>
      api("/session", {
        method: "DELETE",
        headers: { "X-CSRF-Token": session!.csrf },
      }),
    onSuccess: () => {
      setSession(null);
      client.clear();
    },
  });
  if (!ready && sessionQuery.isPending) return <Loading />;
  if (
    !ready &&
    sessionQuery.error &&
    !(
      sessionQuery.error instanceof ApiError &&
      sessionQuery.error.status === 401
    )
  )
    return (
      <main className="login-layout">
        <ErrorNotice
          error={sessionQuery.error}
          retry={() => sessionQuery.refetch()}
        />
      </main>
    );
  if (!session)
    return (
      <Login
        onSuccess={(value) => {
          client.clear();
          setSession(value);
          setReady(true);
          client.setQueryData(["/session"], value);
        }}
      />
    );
  const props = { session, navigate, params: location };
  const readyCount = health.error
    ? undefined
    : health.data?.items.filter((s) => s.state === "ready").length;
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to workspace
      </a>
      <aside id="sidebar" className={`sidebar ${navOpen ? "open" : ""}`}>
        <a
          className="brand"
          href="?workspace=overview"
          onClick={(e) => {
            e.preventDefault();
            navigate("overview");
          }}
        >
          <Hexagon size={28} />
          <span>
            ERASEPROOF <b>X</b>
          </span>
        </a>
        <div className="project-switch">
          <div className="project-icon">
            <Boxes size={19} />
          </div>
          <div>
            <strong>Synthetic research lab</strong>
            <small>Local engineering environment</small>
          </div>
        </div>
        <p className="nav-label">Operations</p>
        <nav aria-label="Engineering workspaces">
          {navigation.map(([id, label, Icon], i) => (
            <div key={id}>
              {i === 5 ? (
                <p className="nav-label">Investigation & research</p>
              ) : null}
              <a
                href={`?workspace=${id}`}
                aria-current={workspace === id ? "page" : undefined}
                className={workspace === id ? "active" : ""}
                onClick={(e) => {
                  e.preventDefault();
                  navigate(id);
                }}
              >
                <Icon size={18} />
                <span>{label}</span>
                {workspace === id ? <ChevronRight size={14} /> : null}
              </a>
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="lab-boundary">
            <span className="status-dot" />
            <span>Local synthetic workspace</span>
          </div>
          <p>
            Operational completion
            <br />
            <strong>≠ verified absence</strong>
          </p>
          <div className="user">
            <span className="avatar">
              <Shield size={17} />
            </span>
            <div>
              <strong>
                {session.role === "readonly"
                  ? "Observer"
                  : session.role === "research"
                    ? "Research admin"
                    : "Operator"}
              </strong>
              <small>Server-authorized session</small>
            </div>
            <button
              aria-label="Sign out"
              onClick={() => logout.mutate()}
              disabled={logout.isPending}
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <div className="workspace-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            <button
              className="icon-button mobile-menu"
              aria-label="Toggle navigation"
              aria-controls="sidebar"
              aria-expanded={navOpen}
              onClick={() => setNavOpen(!navOpen)}
            >
              <Menu size={20} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>{title}</strong>
          </div>
          <form
            className="global-search"
            onSubmit={(e) => {
              e.preventDefault();
              navigate("customers", { search });
            }}
          >
            <Search size={16} />
            <input
              ref={searchRef}
              aria-label="Find a synthetic customer"
              placeholder="Find a customer or UUID…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <kbd>
              <Command size={11} /> K
            </kbd>
          </form>
          <div className="top-actions">
            <span
              className={`connection ${readyCount === 7 ? "connected" : ""}`}
            >
              {readyCount === undefined
                ? health.error
                  ? "Link unavailable"
                  : "Checking link"
                : `${readyCount}/7 APIs ready`}
            </span>
            <button
              className="icon-button"
              aria-label="Refresh source data"
              onClick={() => client.invalidateQueries()}
            >
              <RefreshCw size={17} />
            </button>
            <button
              className="icon-button"
              aria-label="Toggle color theme"
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            >
              {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <button
              className="icon-button"
              aria-label="Open outcome guide"
              onClick={() => help.current?.showModal()}
            >
              <HelpCircle size={18} />
            </button>
          </div>
        </header>
        <main id="main" className="main-content">
          {logout.error ? <ErrorNotice error={logout.error} /> : null}
          <WorkspaceBoundary key={location.toString()}>
            {workspace === "overview" ? (
              <Overview
                {...props}
                health={health.error ? undefined : health.data}
              />
            ) : workspace === "topology" ? (
              <Topology
                {...props}
                health={health.error ? undefined : health.data}
              />
            ) : workspace === "customers" ? (
              <Customers {...props} />
            ) : workspace === "deletions" ? (
              <Deletions {...props} />
            ) : workspace === "verification" ? (
              <Verification {...props} />
            ) : workspace === "investigator" ? (
              <Investigator {...props} />
            ) : workspace === "faults" ? (
              <FaultStudio {...props} />
            ) : workspace === "research" ? (
              <Research {...props} />
            ) : (
              <EvidenceExplorer {...props} />
            )}
          </WorkspaceBoundary>
        </main>
        <footer className="app-footer">
          <span>
            ERASEPROOF X <b>ENGINEERING</b>
          </span>
          <span>
            Declared scope. Recorded observations. Explicit uncertainty.
          </span>
        </footer>
      </div>
      <dialog
        className="dialog"
        ref={help}
        aria-labelledby="outcome-guide-title"
      >
        <form method="dialog">
          <p className="eyebrow">Reading the evidence</p>
          <h2 id="outcome-guide-title">
            Claims and observations are different.
          </h2>
          <p>
            Completed reported means the deletion workers reported success.
            Verified absent means the independent verifier observed absence
            within its declared scope and consistency policy, at the recorded
            time.
          </p>
          <p>
            Inconclusive, pending and unsupported outcomes are not successful
            deletion proofs. Historical benchmarks are saved executions, not
            live system counters.
          </p>
          <button className="button">Close guide</button>
        </form>
      </dialog>
    </div>
  );
}
