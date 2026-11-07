import { useDeferredValue, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Check,
  ChevronRight,
  Database,
  Download,
  Plus,
  Search,
  Shield,
  Workflow,
} from "lucide-react";
import { date, download, mutation, short } from "./api";
import { useApi } from "./queries";
import {
  Badge,
  Confirm,
  Empty,
  ErrorNotice,
  Json,
  Loading,
  Metric,
  PageTitle,
  Pager,
  Panel,
  ReadOnly,
  Table,
  Timeline,
} from "./ui";
import type {
  Customer,
  Footprint,
  Deletion,
  Experiment,
  Health,
  Navigate,
  Page,
  Report,
  Run,
  RunSummary,
  Session,
  Snapshot,
  TimelineEvent,
} from "./types";
export interface WorkspaceProps {
  session: Session;
  navigate: Navigate;
  params: URLSearchParams;
}
const live = (service: string, path: string) => `/live/${service}/v1/${path}`;
export function Overview({
  session,
  navigate,
  health,
}: WorkspaceProps & { health?: Health }) {
  const snapshot = useApi<Snapshot>(
    live("customer", "dashboard/snapshot"),
    8000,
  );
  const experiments = useApi<{ items: Experiment[] }>(
    live("verification", "research/experiments?limit=5"),
    15000,
  );
  const s = snapshot.error ? undefined : snapshot.data;
  const value = (kind: "deletions" | "verifications", state: string) =>
    s
      ? s[kind].find(
          (row) => ("state" in row ? row.state : row.result) === state,
        )?.count || 0
      : "—";
  return (
    <>
      <PageTitle
        eyebrow="Live operational overview"
        title="Command center"
        description="Reported completion is a claim. Independent verification provides the observation."
        action={
          <button className="button" onClick={() => navigate("customers")}>
            <Plus size={16} />
            {session.role === "readonly"
              ? "Explore customer data"
              : "Create synthetic customer"}
          </button>
        }
      />
      {snapshot.error ? (
        <ErrorNotice error={snapshot.error} retry={() => snapshot.refetch()} />
      ) : null}
      <div className="metrics-grid">
        <Metric
          label="Synthetic customer profiles"
          value={s?.customer_count ?? "—"}
          detail="Source rows currently present"
        />
        <Metric
          label="Completed reported"
          value={value("deletions", "COMPLETED_REPORTED")}
          detail="Worker-reported operational completion"
          tone="blue"
        />
        <Metric
          label="Verified absent"
          value={value("verifications", "VERIFIED_ABSENT")}
          detail="Recorded runs · within declared scope"
          tone="green"
        />
        <Metric
          label="False-success findings"
          value={value("verifications", "FALSE_SUCCESS_DETECTED")}
          detail="Independent contradiction of completion"
          tone="amber"
        />
      </div>
      <div className="grid two">
        <Panel
          title="Deletion requests by state"
          eyebrow="Live operational ledger"
        >
          <div className="state-counts">
            {[
              "REQUESTED",
              "IN_PROGRESS",
              "RETRYING",
              "COMPLETED_REPORTED",
              "PARTIALLY_FAILED",
              "FAILED",
            ].map((state) => (
              <div key={state}>
                <Badge value={state} />
                <strong>{value("deletions", state)}</strong>
              </div>
            ))}
          </div>
        </Panel>
        <Panel
          title="Independent verification outcomes"
          eyebrow="Recorded runs, not a paired deletion rate"
        >
          <div className="state-counts">
            {[
              "VERIFIED_ABSENT",
              "FALSE_SUCCESS_DETECTED",
              "RESIDUAL_DATA_DETECTED",
              "PENDING_CONSISTENCY",
              "INCONCLUSIVE",
              "UNSUPPORTED",
            ].map((state) => (
              <div key={state}>
                <Badge value={state} />
                <strong>{value("verifications", state)}</strong>
              </div>
            ))}
          </div>
          <p className="panel-note">
            Recorded target probe-failure counters: {s?.probe_failures ?? "—"} ·
            Targets marked inconclusive: {s?.inconclusive_targets ?? "—"}. These
            are observations, not a clean bill of health.
          </p>
        </Panel>
      </div>
      <div className="grid two">
        <Panel
          title="Service readiness"
          eyebrow="Live health probes"
          action={
            <button
              className="text-button"
              onClick={() => navigate("topology")}
            >
              View topology <ArrowRight size={14} />
            </button>
          }
        >
          <div className="service-grid">
            {health ? (
              health.items.map((item) => (
                <div className="service-card" key={item.service}>
                  <span className="service-icon">
                    <Database size={17} />
                  </span>
                  <strong>{item.service}</strong>
                  <Badge value={item.state} />
                  <small>{date(item.observed_at_unix)}</small>
                </div>
              ))
            ) : (
              <Loading />
            )}
          </div>
          <p className="panel-note">
            Seven API readiness checks. Background consumers and RabbitMQ are
            not individually health-probed here.
          </p>
        </Panel>
        <Panel
          title="Independent findings"
          eyebrow="Reported versus observed"
          action={<span className="pill">Most recent 12</span>}
        >
          {s?.recent_findings.length ? (
            <div className="finding-list">
              {s.recent_findings.map((f) => (
                <button
                  key={f.id}
                  className="finding-row"
                  onClick={() =>
                    navigate("investigator", { run: f.id, source: "live" })
                  }
                >
                  <span className="finding-icon">
                    <Shield size={18} />
                  </span>
                  <span>
                    <strong>Reported completion contradicted</strong>
                    <small>
                      Customer {short(f.customer_id)} · {date(f.created_at)}
                    </small>
                    <Badge value={f.result} />
                  </span>
                  <ChevronRight size={17} />
                </button>
              ))}
            </div>
          ) : snapshot.isPending ? (
            <Loading />
          ) : (
            <Empty
              title="No recorded residual findings"
              description="This is not a deletion proof. Findings appear only when independent observations detect residue."
            />
          )}
        </Panel>
      </div>
      <div className="claim-banner">
        <div className="claim-symbol">
          <Workflow size={24} />
          <span>≠</span>
          <Shield size={24} />
        </div>
        <div>
          <h3>Operational success is not verified absence.</h3>
          <p>
            These counters describe different records, not a paired success
            rate. Open a request to compare its claim with its own store-level
            observations.
          </p>
        </div>
        <button onClick={() => navigate("verification")}>
          Open verification lab <ArrowRight size={15} />
        </button>
      </div>
      <div className="grid two">
        <Panel title="Activity stream" eyebrow="Most recent 30 recorded events">
          {s ? (
            <Timeline items={s.activity} />
          ) : snapshot.isPending ? (
            <Loading />
          ) : null}
        </Panel>
        <Panel
          title="Research executions"
          eyebrow="Live experiment records"
          action={
            <button
              className="text-button"
              onClick={() => navigate("research")}
            >
              Explore benchmarks <ArrowRight size={14} />
            </button>
          }
        >
          {experiments.error ? (
            <ErrorNotice error={experiments.error} />
          ) : experiments.isPending ? (
            <Loading />
          ) : experiments.data?.items.length ? (
            <div className="record-list">
              {experiments.data.items.map((e) => (
                <button
                  key={e.id}
                  onClick={() => navigate("research", { experiment: e.id })}
                >
                  <span>
                    <strong>Experiment {short(e.id)}</strong>
                    <small>
                      {date(e.created_at)} · code {e.code_commit.slice(0, 7)}
                    </small>
                  </span>
                  <Badge value={e.state} />
                </button>
              ))}
            </div>
          ) : (
            <Empty
              title="No live experiments recorded"
              description="Validated historical Phase 4 measurements are available separately in Research benchmarks."
              action={
                <button onClick={() => navigate("research")}>
                  Open historical measurements
                </button>
              }
            />
          )}
        </Panel>
      </div>
      <p className="source-note">
        Source: live API readiness and database read models. Snapshot:{" "}
        {date(s?.observed_at)}. Unavailable sources display no invented
        statistics.
      </p>
    </>
  );
}

const nodes = [
  {
    id: "customer",
    label: "Customer service",
    x: 35,
    y: 45,
    role: "Authoritative synthetic profiles",
    category: "Source data",
    adapter: "customer",
  },
  {
    id: "order",
    label: "Order service",
    x: 35,
    y: 175,
    role: "Orders with retained fact fields",
    category: "Mixed retained and erased fields",
    adapter: "orders",
  },
  {
    id: "postgres",
    label: "PostgreSQL",
    x: 280,
    y: 105,
    role: "Source, orders, outbox, audit and coordinator state",
    category: "Shared database boundary",
    adapter: "event_history",
  },
  {
    id: "publisher",
    label: "Outbox publisher",
    x: 510,
    y: 35,
    role: "Confirmed durable event publication",
    category: "Asynchronous delivery",
    adapter: "",
  },
  {
    id: "rabbitmq",
    label: "RabbitMQ",
    x: 745,
    y: 35,
    role: "At-least-once event delivery",
    category: "Queue infrastructure",
    adapter: "",
  },
  {
    id: "consumers",
    label: "Projection consumers",
    x: 745,
    y: 165,
    role: "Idempotent cache, search and analytics workers",
    category: "Asynchronous consumers",
    adapter: "",
  },
  {
    id: "redis",
    label: "Redis",
    x: 510,
    y: 295,
    role: "Cached profiles plus permitted erasure markers",
    category: "Projection and tombstone",
    adapter: "cache",
  },
  {
    id: "opensearch",
    label: "OpenSearch",
    x: 745,
    y: 295,
    role: "Search profiles and versioned erasure markers",
    category: "Projection and tombstone",
    adapter: "search",
  },
  {
    id: "analytics",
    label: "Analytics",
    x: 280,
    y: 295,
    role: "Customer-linked analytic events in PostgreSQL",
    category: "Derived event records",
    adapter: "analytics",
  },
  {
    id: "deletion",
    label: "Deletion orchestrator",
    x: 35,
    y: 425,
    role: "Durable task state, retry budgets and lifecycle fences",
    category: "Operational claim",
    adapter: "",
  },
  {
    id: "verification",
    label: "Independent verifier",
    x: 510,
    y: 425,
    role: "Fresh read-only observations of six scoped targets",
    category: "Independent observation",
    adapter: "",
  },
];
export function Topology({ health }: WorkspaceProps & { health?: Health }) {
  const [selected, setSelected] = useState("verification");
  const policy = useApi<Record<string, unknown>>("/policy");
  const node = nodes.find((n) => n.id === selected)!;
  const targetMap: Record<string, string> = {
    redis: "cache",
    opensearch: "search",
    analytics: "analytics",
    customer: "customer",
    order: "order",
    deletion: "deletion",
    verification: "verification",
  };
  const status = health?.items.find((h) => h.service === targetMap[selected]);
  return (
    <>
      <PageTitle
        eyebrow="System architecture"
        title="Follow the data, across every boundary"
        description="Architecture metadata with current API readiness. Lines show known dependencies, not live traffic."
      />
      <div className="topology-layout">
        <Panel
          title="Distributed data topology"
          action={
            <span className="pill">scope-v1 · architecture metadata</span>
          }
        >
          <div
            className="graph-scroll"
            tabIndex={0}
            aria-label="Scrollable interactive architecture graph"
          >
            <div className="topology-canvas">
              <svg viewBox="0 0 960 525" aria-hidden="true">
                <defs>
                  <marker
                    id="arrow"
                    viewBox="0 0 10 10"
                    refX="9"
                    refY="5"
                    markerWidth="5"
                    markerHeight="5"
                    orient="auto-start-reverse"
                  >
                    <path d="M0 0L10 5L0 10" fill="currentColor" />
                  </marker>
                </defs>
                <g className="graph-edges" fill="none" markerEnd="url(#arrow)">
                  <path d="M210 80 H250 V140 H280 M210 210 H250 V150 H280 M455 140 H480 V70 H510 M685 70 H745 M832 105 V165 M832 235 V275 H600 V295 M832 235 V295 M745 200 H690 V260 H365 V295 M122 425 V365 H280 M122 425 V365 H600 V365" />
                  <path
                    className="read-edge"
                    d="M600 425 V375 H832 V365 M600 425 V365 M510 460 H470 V140 H455 M510 460 H365 V365"
                  />
                </g>
              </svg>
              {nodes.map((n) => (
                <button
                  style={{ left: n.x, top: n.y }}
                  key={n.id}
                  className={`graph-node ${n.id === selected ? "selected" : ""}`}
                  aria-pressed={n.id === selected}
                  onClick={() => setSelected(n.id)}
                >
                  <span className="eyebrow">{n.category}</span>
                  <strong>
                    {n.id === "verification" ? (
                      <Shield size={17} />
                    ) : (
                      <Database size={17} />
                    )}{" "}
                    {n.label}
                  </strong>
                  <small>
                    {n.id === "rabbitmq" ||
                    n.id === "publisher" ||
                    n.id === "consumers" ||
                    n.id === "postgres"
                      ? "Architecture metadata"
                      : "Select to inspect scope"}
                  </small>
                </button>
              ))}
            </div>
          </div>
          <div className="graph-legend">
            <span>
              <i />
              Known dependency
            </span>
            <span>
              <i className="dashed" />
              Independent read path
            </span>
            <span>11 architecture components · 6 verification targets</span>
          </div>
        </Panel>
        <Panel title={node.label} eyebrow="Selected component">
          <div className="detail-stack">
            <p>{node.role}</p>
            <div>
              <span className="eyebrow">Data category</span>
              <strong>{node.category}</strong>
            </div>
            <div>
              <span className="eyebrow">Operational visibility</span>
              {status ? (
                <>
                  <Badge value={status.state} />
                  <small>
                    {["redis", "opensearch"].includes(selected)
                      ? `Indirect via ${status.service} API readiness`
                      : "API readiness probe"}{" "}
                    · {date(status.observed_at_unix)}
                  </small>
                </>
              ) : (
                <p className="subtle">
                  No direct health probe exposed. Architecture metadata does not
                  establish runtime health.
                </p>
              )}
            </div>
            <div>
              <span className="eyebrow">Verification coverage</span>
              <p>
                {node.adapter
                  ? `Supported target: ${node.adapter}. Fresh observations remain subject to the captured policy.`
                  : "Coordination component; not a separate proof of store-level absence."}
              </p>
            </div>
            <div>
              <span className="eyebrow">Consistency assumptions</span>
              <p>
                Durable outbox, at-least-once delivery, idempotent consumers and
                permanent lifecycle fences. Negative verification requires the
                configured grace and repeat-sample policy.
              </p>
            </div>
            {node.adapter ? (
              <details>
                <summary>Declared retention and scope policy</summary>
                {policy.data ? (
                  <Json
                    value={
                      (
                        policy.data.targets as
                          Record<string, unknown> | undefined
                      )?.[node.adapter] || policy.data
                    }
                  />
                ) : policy.error ? (
                  <ErrorNotice error={policy.error} />
                ) : (
                  <Loading />
                )}
              </details>
            ) : null}
          </div>
        </Panel>
      </div>
    </>
  );
}

export function Customers({ session, navigate, params }: WorkspaceProps) {
  const [search, setSearch] = useState(params.get("search") || "");
  const deferred = useDeferredValue(search);
  const [page, setPage] = useState(0);
  const [name, setName] = useState("Synthetic Engineering Test");
  const [email, setEmail] = useState("");
  const [selected, setSelected] = useState(params.get("customer") || "");
  const list = useApi<Page<Customer>>(
    live(
      "customer",
      `dashboard/customers?limit=20&offset=${page * 20}&search=${encodeURIComponent(deferred)}`,
    ),
    5000,
  );
  const propagation = useApi<{
    source_present: boolean;
    stores: Record<
      string,
      { state: string; data: unknown; erasure_marker?: boolean }
    >;
    receipts: Record<string, unknown>[];
  }>(
    selected ? live("customer", `customers/${selected}/propagation`) : null,
    3000,
  );
  const footprint = useApi<Footprint>(
    selected
      ? live("customer", `dashboard/customers/${selected}/footprint`)
      : null,
    3000,
  );
  const client = useQueryClient();
  const create = useMutation({
    mutationFn: () =>
      mutation<{ id: string }>(
        "/live/customer/v1/customers",
        {
          name,
          email: email || `synthetic-${crypto.randomUUID()}@example.invalid`,
        },
        session.csrf,
      ),
    onSuccess: (value) => {
      setSelected(value.id);
      client.invalidateQueries();
      setEmail("");
    },
  });
  const order = useMutation({
    mutationFn: () =>
      mutation(
        "/live/order/v1/orders",
        { customer_id: selected, amount_cents: 1234, currency: "USD" },
        session.csrf,
      ),
    onSuccess: () => client.invalidateQueries(),
  });
  const erase = useMutation({
    mutationFn: () =>
      mutation<Deletion>(
        "/live/deletion/v1/deletions",
        { customer_id: selected, idempotency_key: `dashboard:${selected}` },
        session.csrf,
      ),
    onSuccess: (value) => {
      client.invalidateQueries();
      navigate("deletions", { request: value.id });
    },
  });
  function submit(e: FormEvent) {
    e.preventDefault();
    create.mutate();
  }
  return (
    <>
      <PageTitle
        eyebrow="Supported data footprint"
        title="Customer data explorer"
        description="Synthetic source profiles, derived projections and declared retention boundaries."
      />
      <div className="grid customer-grid">
        <Panel
          title="Synthetic customers"
          eyebrow="Live source and lifecycle records"
          action={<span className="pill">20 per page</span>}
        >
          <label className="search-field">
            <Search size={16} />
            <input
              aria-label="Filter customers"
              placeholder="Name or customer UUID"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(0);
              }}
            />
          </label>
          {list.error ? (
            <ErrorNotice error={list.error} retry={() => list.refetch()} />
          ) : list.isPending ? (
            <Loading />
          ) : list.data?.items.length ? (
            <>
              <Table label="Synthetic customer records">
                <thead>
                  <tr>
                    <th>Customer</th>
                    <th>Lifecycle</th>
                    <th>Created</th>
                    <th>Inspect</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((c) => (
                    <tr
                      key={c.id}
                      className={selected === c.id ? "selected-row" : ""}
                    >
                      <td>
                        <strong>{c.name || "Erased source profile"}</strong>
                        <code>{c.id}</code>
                      </td>
                      <td>
                        <Badge value={c.lifecycle} />
                      </td>
                      <td>{date(c.created_at)}</td>
                      <td>
                        <button
                          aria-label={`Inspect customer ${c.id}`}
                          onClick={() => setSelected(c.id)}
                        >
                          Inspect <ChevronRight size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
              <Pager
                page={page}
                total={list.data.total}
                limit={20}
                onChange={setPage}
              />
            </>
          ) : (
            <Empty
              title="No matching synthetic customers"
              description="Create a fixture to observe real propagation. No demo records are inserted automatically."
            />
          )}
        </Panel>
        <div className="stack">
          <Panel
            title="Create a synthetic fixture"
            eyebrow="Authorized operation"
          >
            {session.role === "readonly" ? (
              <ReadOnly />
            ) : (
              <form className="form-stack" onSubmit={submit}>
                <label>
                  Fixture name
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    pattern="Synthetic (?:[A-Za-z0-9 ]|-)+"
                    maxLength={100}
                    required
                  />
                </label>
                <label>
                  Synthetic email (optional)
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="Generated @example.invalid"
                    pattern="(?:[a-zA-Z0-9._+]|-)+@example[.]invalid"
                  />
                </label>
                <p className="subtle">
                  Only synthetic names and example.invalid addresses are
                  accepted. A customer-created event propagates through the
                  actual outbox.
                </p>
                <button className="button" disabled={create.isPending}>
                  <Plus size={16} />
                  {create.isPending ? "Creating…" : "Create customer"}
                </button>
              </form>
            )}
            {create.error ? <ErrorNotice error={create.error} /> : null}
          </Panel>
          <Panel
            title="Known data locations"
            eyebrow={
              selected ? `Customer ${short(selected)}` : "Select a record"
            }
          >
            {selected ? (
              <>
                <code className="entity-id">{selected}</code>
                {propagation.error ? (
                  <ErrorNotice error={propagation.error} />
                ) : propagation.isPending ? (
                  <Loading />
                ) : (
                  <div className="location-list">
                    <div>
                      <span>Customer source</span>
                      <strong>
                        {propagation.data?.source_present
                          ? "Present"
                          : "Absent"}
                      </strong>
                    </div>
                    {Object.entries(propagation.data?.stores || {}).map(
                      ([store, value]) => (
                        <div key={store}>
                          <span>{store} projection</span>
                          <strong>
                            {value.erasure_marker
                              ? "Erasure marker observed"
                              : value.state}
                          </strong>
                        </div>
                      ),
                    )}
                    <p className="subtle">
                      Operational inspection, not an independent deletion proof.
                      Order facts, audit UUIDs and exact erasure markers have
                      declared retention rules.
                    </p>
                  </div>
                )}
                {footprint.error ? (
                  <ErrorNotice error={footprint.error} />
                ) : footprint.isPending ? (
                  <Loading />
                ) : footprint.data ? (
                  <>
                    <div className="definition-grid">
                      <div>
                        <span>Known order rows</span>
                        <strong>{footprint.data.orders.total}</strong>
                      </div>
                      <div>
                        <span>Source event envelopes</span>
                        <strong>
                          {footprint.data.event_history.source_events}
                        </strong>
                      </div>
                      <div>
                        <span>Other event envelopes</span>
                        <strong>
                          {footprint.data.event_history.other_events}
                        </strong>
                      </div>
                      <div>
                        <span>Consumer receipt metadata</span>
                        <strong>
                          {footprint.data.event_history.consumer_receipts}
                        </strong>
                      </div>
                      <div>
                        <span>Deletion audit events</span>
                        <strong>
                          {footprint.data.event_history.audit_events}
                        </strong>
                      </div>
                      <div>
                        <span>Lifecycle tombstone</span>
                        <strong>
                          {footprint.data.tombstone?.lifecycle || "Not present"}
                        </strong>
                      </div>
                    </div>
                    {footprint.data.orders.items.length ? (
                      <Table label="Known retained order facts">
                        <thead>
                          <tr>
                            <th>Order</th>
                            <th>Amount</th>
                            <th>Customer link</th>
                          </tr>
                        </thead>
                        <tbody>
                          {footprint.data.orders.items.map((o) => (
                            <tr key={o.id}>
                              <td>
                                <code>{o.id}</code>
                              </td>
                              <td>
                                {o.amount_cents} cents · {o.currency}
                              </td>
                              <td>
                                {o.has_customer_link ? "Present" : "Cleared"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </Table>
                    ) : null}
                    <p className="panel-note">
                      First 100 source/manifest order facts. A cleared link
                      alone does not establish anonymization.{" "}
                      {footprint.data.note} Observed{" "}
                      {date(footprint.data.observed_at)}.
                    </p>
                  </>
                ) : null}
                <div className="actions">
                  <button
                    disabled={
                      session.role === "readonly" ||
                      order.isPending ||
                      !propagation.data?.source_present
                    }
                    onClick={() => order.mutate()}
                  >
                    Add synthetic order · $12.34
                  </button>
                  <Confirm
                    label="Request deletion"
                    title="Delete this synthetic customer's eligible data?"
                    description={`Customer ${selected}. Deletion sets permanent lifecycle fences and cannot be reversed. Permitted facts and audit metadata remain.`}
                    disabled={session.role === "readonly" || erase.isPending}
                    onConfirm={() => erase.mutate()}
                  />
                </div>
                {order.isSuccess ? (
                  <p className="success-note">
                    <Check size={15} />
                    Order accepted by the real backend.
                  </p>
                ) : null}
                {order.error || erase.error ? (
                  <ErrorNotice error={order.error || erase.error} />
                ) : null}
              </>
            ) : (
              <Empty
                title="Select a customer"
                description="Inspect the source and known projections, then initiate an authorized deletion."
              />
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}

export function Deletions({ session, navigate, params }: WorkspaceProps) {
  const [page, setPage] = useState(0);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState(params.get("request") || "");
  const list = useApi<Page<Deletion>>(
    live(
      "customer",
      `dashboard/deletions?limit=20&offset=${page * 20}${filter ? "&state=" + filter : ""}`,
    ),
    5000,
  );
  const detail = useApi<Deletion>(
    selected ? live("deletion", `deletions/${selected}`) : null,
    (data) =>
      data &&
      ["COMPLETED_REPORTED", "PARTIALLY_FAILED", "FAILED"].includes(data.state)
        ? false
        : 1500,
  );
  const events = useApi<TimelineEvent[]>(
    selected
      ? live("deletion", `deletions/${selected}/events?limit=500`)
      : null,
    selected &&
      detail.data &&
      !["COMPLETED_REPORTED", "PARTIALLY_FAILED", "FAILED"].includes(
        detail.data.state,
      )
      ? 2000
      : false,
  );
  const client = useQueryClient();
  const retry = useMutation({
    mutationFn: () =>
      mutation<Deletion>(
        live("deletion", `deletions/${selected}/retry`),
        {},
        session.csrf,
      ),
    onSuccess: () => client.invalidateQueries(),
  });
  return (
    <>
      <PageTitle
        eyebrow="Distributed orchestration"
        title="Deletion operations"
        description="Track actual tasks, retries and audit events. Success reported by a worker is not independent proof."
      />
      <Panel
        title="Request ledger"
        action={
          <label className="inline-label">
            State
            <select
              value={filter}
              onChange={(e) => {
                setFilter(e.target.value);
                setPage(0);
              }}
            >
              <option value="">All states</option>
              {[
                "REQUESTED",
                "IN_PROGRESS",
                "RETRYING",
                "COMPLETED_REPORTED",
                "PARTIALLY_FAILED",
                "FAILED",
              ].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
        }
      >
        {list.error ? (
          <ErrorNotice error={list.error} retry={() => list.refetch()} />
        ) : list.isPending ? (
          <Loading />
        ) : list.data?.items.length ? (
          <>
            <Table label="Deletion requests">
              <thead>
                <tr>
                  <th>Request / customer</th>
                  <th>Operational status</th>
                  <th>Updated</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <strong>{short(r.id)}</strong>
                      <code>{r.customer_id}</code>
                    </td>
                    <td>
                      <Badge value={r.state} />
                    </td>
                    <td>{date(r.updated_at)}</td>
                    <td>
                      <button onClick={() => setSelected(r.id)}>
                        Open request
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <div className="pager">
              <span>Page {page + 1} · no inferred total</span>
              <div>
                <button disabled={!page} onClick={() => setPage(page - 1)}>
                  Previous
                </button>
                <button
                  disabled={(list.data?.items.length || 0) < 20}
                  onClick={() => setPage(page + 1)}
                >
                  Next
                </button>
              </div>
            </div>
          </>
        ) : (
          <Empty
            title="No deletion requests"
            description="Select a synthetic customer to start the supported deletion workflow."
            action={
              <button onClick={() => navigate("customers")}>
                Open customer data
              </button>
            }
          />
        )}
      </Panel>
      {selected ? (
        <>
          {detail.error ? (
            <ErrorNotice error={detail.error} />
          ) : detail.data ? (
            <Panel
              title={`Request ${short(selected)}`}
              eyebrow="Actual orchestration details"
              action={
                <div className="actions">
                  <Badge value={detail.data.state} />
                  <button
                    className="button"
                    disabled={session.role === "readonly"}
                    onClick={() =>
                      navigate("verification", { request: selected })
                    }
                  >
                    <Shield size={16} />
                    Verify independently
                  </button>
                </div>
              }
            >
              <div className="notice">
                <Workflow size={18} />
                <p>
                  <strong>Operational claim only.</strong> Completion means
                  required tasks reported success. Store-level absence requires
                  a separate verification run.
                </p>
              </div>
              <div className="metadata-row">
                <span>
                  Customer <code>{detail.data.customer_id}</code>
                </span>
                <span>
                  Correlation <code>{detail.data.correlation_id}</code>
                </span>
              </div>
              <Table label="Deletion target tasks">
                <thead>
                  <tr>
                    <th>Target</th>
                    <th>Task state</th>
                    <th>Attempts</th>
                    <th>Failure / retry history</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.data.tasks.map((t) => (
                    <tr key={t.id}>
                      <td>
                        <strong>{t.target}</strong>
                      </td>
                      <td>
                        <Badge value={t.state} />
                      </td>
                      <td>{t.attempt_count}</td>
                      <td>
                        {t.last_failure_code ? (
                          <p className="failure-code">{t.last_failure_code}</p>
                        ) : null}
                        <details>
                          <summary>
                            Inspect {t.attempts.length} durable attempts
                          </summary>
                          {t.attempts.map((a) => (
                            <div className="attempt" key={a.id}>
                              <Badge value={a.outcome} />
                              <span>
                                #{a.attempt_no} ·{" "}
                                {a.failure_code || "No failure code"} ·{" "}
                                {a.duration_ms ?? "—"} ms
                              </span>
                            </div>
                          ))}
                        </details>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
              {["PARTIALLY_FAILED", "FAILED"].includes(detail.data.state) ? (
                <Confirm
                  label="Retry failed targets"
                  title="Retry terminally failed deletion tasks?"
                  description="The backend enforces the remaining retry budget. Successful targets are not reissued."
                  disabled={session.role === "readonly" || retry.isPending}
                  onConfirm={() => retry.mutate()}
                />
              ) : null}
              {retry.error ? <ErrorNotice error={retry.error} /> : null}
            </Panel>
          ) : (
            <Loading />
          )}
          <Panel
            title="Operational audit timeline"
            eyebrow="Append-only recorded events"
          >
            {events.error ? (
              <ErrorNotice error={events.error} />
            ) : events.data ? (
              <Timeline items={events.data} />
            ) : (
              <Loading />
            )}
          </Panel>
        </>
      ) : null}
    </>
  );
}

export function Verification({ session, navigate, params }: WorkspaceProps) {
  const [request, setRequest] = useState(params.get("request") || "");
  const [selected, setSelected] = useState(params.get("run") || "");
  const [profile, setProfile] = useState("default");
  const requests = useApi<Page<Deletion>>(
    live("customer", "dashboard/deletions?limit=100"),
    5000,
  );
  const runs = useApi<Page<RunSummary>>(
    live("customer", "dashboard/verifications?limit=20"),
    5000,
  );
  const history = useApi<Run[]>(
    request ? live("verification", `deletions/${request}/verifications`) : null,
    4000,
  );
  const report = useApi<Report>(
    selected ? live("verification", `verifications/${selected}/report`) : null,
    (data) => (data?.verification.state === "FINISHED" ? false : 1500),
  );
  const client = useQueryClient();
  const start = useMutation({
    mutationFn: (requestId: string) =>
      mutation<Run>(
        live("verification", `deletions/${requestId}/verifications`),
        { idempotency_key: crypto.randomUUID(), consistency_profile: profile },
        session.csrf,
      ),
    onSuccess: (value) => {
      setSelected(value.id);
      client.invalidateQueries();
    },
  });
  const r = report.data;
  return (
    <>
      <PageTitle
        eyebrow="Independent store observations"
        title="Verification lab"
        description="Fresh probes. Captured policy. Explicit uncertainty. Every verdict is bounded by scope and observation time."
      />
      <div className="grid two">
        <Panel
          title="Start an independent verification"
          eyebrow="Authorized operator action"
        >
          <form
            className="form-stack"
            onSubmit={(e) => {
              e.preventDefault();
              start.mutate(request);
            }}
          >
            <label>
              Eligible deletion request
              <select
                value={request}
                required
                onChange={(e) => setRequest(e.target.value)}
              >
                <option value="">Select an existing deletion</option>
                {request &&
                !requests.data?.items.some((d) => d.id === request) ? (
                  <option value={request}>{request}</option>
                ) : null}
                {requests.data?.items.map((d) => (
                  <option key={d.id} value={d.id}>
                    {short(d.id)} · {d.state}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Consistency profile
              <select
                value={profile}
                onChange={(e) => setProfile(e.target.value)}
              >
                <option value="default">
                  Default policy · repeated negative observations
                </option>
                <option value="extended">
                  Extended policy · stronger consistency waits
                </option>
              </select>
            </label>
            <button
              className="button"
              disabled={
                session.role === "readonly" || !request || start.isPending
              }
            >
              <Shield size={16} />
              {start.isPending ? "Submitting…" : "Start verification"}
            </button>
            {session.role === "readonly" ? <ReadOnly /> : null}
            <p className="subtle">
              An accepted request is queued, not finished. Active runs are
              polled; finished reports remain observation snapshots.
            </p>
          </form>
          {requests.error ? <ErrorNotice error={requests.error} /> : null}
          {start.error ? <ErrorNotice error={start.error} /> : null}
        </Panel>
        <Panel
          title={
            request
              ? "Verification history for selected request"
              : "Recent verification runs"
          }
          eyebrow="Actual run records"
        >
          {(request ? history.error : runs.error) ? (
            <ErrorNotice error={request ? history.error : runs.error} />
          ) : (
            <div className="record-list">
              {(request ? history.data : runs.data?.items)?.map((run) => (
                <button key={run.id} onClick={() => setSelected(run.id)}>
                  <span>
                    <strong>Run {short(run.id)}</strong>
                    <small>
                      {date(run.created_at)} · round {run.round_no}
                    </small>
                  </span>
                  <Badge value={run.result} />
                </button>
              ))}
              {(request ? history.data : runs.data?.items)?.length === 0 ? (
                <Empty
                  title="No verification runs"
                  description="Start an authorized run for an existing deletion request."
                />
              ) : null}
            </div>
          )}
        </Panel>
      </div>
      {selected ? (
        report.error ? (
          <ErrorNotice error={report.error} retry={() => report.refetch()} />
        ) : r ? (
          <>
            <Panel
              title={`Independent report ${short(r.verification.id)}`}
              eyebrow="Observed state"
              action={
                <div className="actions">
                  <Badge value={r.verification.result} />
                  <button
                    onClick={() => download(`verification-${selected}.json`, r)}
                  >
                    <Download size={15} />
                    Export JSON report
                  </button>
                </div>
              }
            >
              <div className="run-summary">
                <div>
                  <span className="eyebrow">Execution state</span>
                  <Badge value={r.verification.state} />
                </div>
                <div>
                  <span className="eyebrow">Consistency round</span>
                  <strong>{r.verification.round_no} / 8</strong>
                </div>
                <div>
                  <span className="eyebrow">Deadline</span>
                  <strong>{date(r.verification.deadline_at)}</strong>
                </div>
                <div>
                  <span className="eyebrow">Observed freshness</span>
                  <p>{r.freshness}</p>
                </div>
              </div>
              <div className="target-grid">
                {r.verification.targets.map((t) => (
                  <div className="target-card" key={t.target}>
                    <span className="target-icon">
                      <Database size={19} />
                    </span>
                    <h3>{t.target}</h3>
                    <Badge value={t.result} />
                    <small>
                      {t.absent_streak} negative samples · {t.probe_failures}{" "}
                      failed probes
                    </small>
                    <small>{date(t.last_observed_at)}</small>
                  </div>
                ))}
              </div>
              <div className="notice">
                <Shield size={18} />
                <p>
                  <strong>Declared proof boundary:</strong>{" "}
                  {r.verification.claim}
                </p>
              </div>
              <div className="actions">
                <button
                  onClick={() =>
                    navigate("evidence", { run: selected, source: "live" })
                  }
                >
                  Inspect sanitized evidence <ArrowRight size={15} />
                </button>
                {["FALSE_SUCCESS_DETECTED", "RESIDUAL_DATA_DETECTED"].includes(
                  r.verification.result,
                ) ? (
                  <button
                    onClick={() =>
                      navigate("investigator", {
                        run: selected,
                        source: "live",
                      })
                    }
                  >
                    Investigate contradiction <ArrowRight size={15} />
                  </button>
                ) : null}
                <button
                  disabled={session.role === "readonly"}
                  onClick={() => {
                    setRequest(r.verification.deletion_request_id);
                    start.mutate(r.verification.deletion_request_id);
                  }}
                >
                  Run a fresh verification
                </button>
              </div>
              <details>
                <summary>
                  Captured consistency policy and integrity metadata
                </summary>
                <Json
                  value={{
                    policy: r.verification.policy,
                    policy_digest: r.verification.policy_digest,
                    evidence_integrity: r.evidence_integrity,
                    excluded_targets: r.excluded_targets,
                    incomplete_targets: r.incomplete_targets,
                  }}
                />
              </details>
            </Panel>
            <Panel title="Verification execution timeline">
              <Timeline items={r.timeline} />
            </Panel>
          </>
        ) : (
          <Loading />
        )
      ) : null}
    </>
  );
}
