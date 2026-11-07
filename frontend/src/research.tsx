import { lazy, Suspense, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Download,
  ExternalLink,
  FlaskConical,
  Play,
  Search,
  Shield,
  TriangleAlert,
} from "lucide-react";
import { date, download, mutation, percentage, short } from "./api";
import { useApi } from "./queries";
import {
  Badge,
  Empty,
  ErrorNotice,
  Json,
  Loading,
  Metric,
  PageTitle,
  Pager,
  Panel,
  Table,
  Timeline,
} from "./ui";
import type { WorkspaceProps } from "./operations";
import type {
  Dataset,
  Deletion,
  Experiment,
  Page,
  Report,
  ResearchJob,
  RunSummary,
  Scenario,
  Summary,
  Trial,
} from "./types";
const ComparisonCharts = lazy(() => import("./Charts"));
const live = (path: string) => `/live/verification/v1/${path}`;
export function useDataset(source: string, page = 0) {
  const historical = source.startsWith("phase4-");
  const jobId = source.startsWith("job:") ? source.slice(4) : null;
  const experimentId = source.startsWith("experiment:")
    ? source.slice(11)
    : null;
  const saved = useApi<Dataset>(historical ? `/history/${source}` : null);
  const job = useApi<ResearchJob>(
    jobId ? `/research/jobs/${jobId}` : null,
    (d) =>
      d && ["COMPLETED", "FAILED", "INTERRUPTED"].includes(d.state)
        ? false
        : 2000,
  );
  const experiment = useApi<Experiment>(
    experimentId ? live(`research/experiments/${experimentId}`) : null,
    10000,
  );
  const summary = useApi<Summary>(
    experimentId ? live(`research/experiments/${experimentId}/summary`) : null,
    10000,
  );
  const trials = useApi<{ items: { body: Trial }[] }>(
    experimentId
      ? live(
          `research/experiments/${experimentId}/trials?limit=20&offset=${page * 20}`,
        )
      : null,
    10000,
  );
  return {
    data:
      saved.data ||
      job.data?.dataset ||
      (experiment.data && summary.data && trials.data
        ? {
            experiment: experiment.data,
            summary: summary.data,
            trials: trials.data.items.map((t) => t.body),
          }
        : undefined),
    error:
      (!historical && !jobId && !experimentId && source !== "live"
        ? new Error(
            "Unknown evidence source. Choose a recorded dataset, job or live experiment.",
          )
        : null) ||
      saved.error ||
      job.error ||
      experiment.error ||
      summary.error ||
      trials.error,
    job: job.data,
    isLiveExperiment: !!experimentId,
  };
}
function SourceSelect({
  source,
  setSource,
}: {
  source: string;
  setSource: (source: string) => void;
}) {
  const experiments = useApi<{ items: Experiment[] }>(
    live("research/experiments?limit=100"),
  );
  const jobs = useApi<{ items: ResearchJob[] }>("/research/jobs", 5000);
  return (
    <label className="inline-label">
      Evidence source
      <select
        aria-label="Evidence source"
        value={source}
        onChange={(e) => setSource(e.target.value)}
      >
        {!["phase4-final", "phase4-initial", "live"].includes(source) &&
        !experiments.data?.items.some((e) => `experiment:${e.id}` === source) &&
        !jobs.data?.items.some((j) => `job:${j.id}` === source) ? (
          <option value={source}>Selected source · {source}</option>
        ) : null}
        <optgroup label="Saved actual CI measurements">
          <option value="phase4-final">Historical Phase 4 · final batch</option>
          <option value="phase4-initial">
            Historical Phase 4 · initial failed batch
          </option>
        </optgroup>
        <optgroup label="Current backend">
          <option value="live">Live verification runs</option>
          {experiments.data?.items.map((e) => (
            <option key={e.id} value={`experiment:${e.id}`}>
              Live experiment {short(e.id)} · {e.state}
            </option>
          ))}
        </optgroup>
        {jobs.data?.items.length ? (
          <optgroup label="Authorized dashboard research jobs">
            {jobs.data.items.map((j) => (
              <option key={j.id} value={`job:${j.id}`}>
                {j.scenario} · {short(j.id)} · {j.state}
              </option>
            ))}
          </optgroup>
        ) : null}
      </select>
    </label>
  );
}
function SourceNotice({ source }: { source: string }) {
  return (
    <div
      className={`notice ${source.startsWith("phase4-") ? "historical" : ""}`}
    >
      <Shield size={18} />
      <p>
        {source.startsWith("phase4-") ? (
          <>
            <strong>Historical measurement, not live telemetry.</strong> This is
            a validated saved execution with its own code revision, seed plan
            and observation times.
          </>
        ) : source.startsWith("job:") ? (
          <>
            <strong>Authorized research execution.</strong> Trials record actual
            observations. Completed jobs clean their synthetic fixtures;
            evidence preserves the pre-cleanup snapshot.
          </>
        ) : (
          <>
            <strong>Live backend records.</strong> These results reflect their
            recorded observation times and declared scope, not a promise about
            future absence.
          </>
        )}
      </p>
    </div>
  );
}
function useReport(source: string, run: string) {
  return useApi<Report>(
    run
      ? source.startsWith("phase4-")
        ? `/history/${source}/evidence/${run}`
        : source.startsWith("job:")
          ? `/research/jobs/${source.slice(4)}/evidence/${run}`
          : live(`verifications/${run}/report`)
      : null,
    (data) =>
      source === "live" && data?.verification.state !== "FINISHED"
        ? 2000
        : false,
  );
}
function runChoices(
  data: Dataset | undefined,
  liveRuns: RunSummary[] | undefined,
) {
  return data
    ? data.trials.flatMap((t) =>
        t.phases
          .filter((p) => p.verification_id)
          .map((p) => ({
            id: p.verification_id!,
            label: `${t.scenario_id} · ${p.phase} · ${short(p.verification_id!)}`,
            result: p.methods.eraseproof?.outcome || "Unknown",
          })),
      )
    : (liveRuns || []).map((r) => ({
        id: r.id,
        label: `${short(r.id)} · ${r.customer_id.slice(0, 8)}`,
        result: r.result,
      }));
}
export function Investigator({ navigate, params }: WorkspaceProps) {
  const [source, setSource] = useState(params.get("source") || "phase4-final");
  const [chosen, setChosen] = useState(params.get("run") || "");
  const dataset = useDataset(source);
  const liveRuns = useApi<Page<RunSummary>>(
    source === "live"
      ? "/live/customer/v1/dashboard/verifications?limit=100"
      : null,
    5000,
  );
  const choices = runChoices(dataset.data, liveRuns.data?.items);
  const selected =
    choices.some((c) => c.id === chosen) ||
    (params.get("run") === chosen && chosen)
      ? chosen
      : choices.find((c) =>
          ["FALSE_SUCCESS_DETECTED", "RESIDUAL_DATA_DETECTED"].includes(
            c.result,
          ),
        )?.id ||
        choices[0]?.id ||
        "";
  const report = useReport(source, selected);
  const phase = dataset.data?.trials
    .flatMap((t) => t.phases)
    .find((p) => p.verification_id === selected);
  const trial = dataset.data?.trials.find((t) =>
    t.phases.some((p) => p.verification_id === selected),
  );
  const deletion = useApi<Deletion>(
    source === "live" && report.data
      ? `/live/deletion/v1/deletions/${report.data.verification.deletion_request_id}`
      : null,
  );
  const r = report.data;
  const claim = phase?.operational_state || deletion.data?.state;
  return (
    <>
      <PageTitle
        eyebrow="Claim versus observation"
        title="Failure investigator"
        description="Investigate a reported success using the actual independent findings and their evidence."
      />
      <div className="toolbar">
        <SourceSelect
          source={source}
          setSource={(s) => {
            setSource(s);
            setChosen("");
          }}
        />
        <label className="inline-label">
          Verification
          <select
            value={selected}
            onChange={(e) => setChosen(e.target.value)}
            aria-label="Investigation run"
          >
            {selected && !choices.some((c) => c.id === selected) ? (
              <option value={selected}>Linked run · {selected}</option>
            ) : null}
            {choices.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <SourceNotice source={source} />
      {dataset.error || liveRuns.error || report.error ? (
        <ErrorNotice error={dataset.error || liveRuns.error || report.error} />
      ) : !selected ? (
        <Empty
          title="No independent findings to inspect"
          description="Run a verification or select a saved dataset. No contradiction is manufactured for an empty system."
        />
      ) : !r ? (
        <Loading />
      ) : (
        <>
          <div className="contradiction">
            <div className="claim-card">
              <p className="eyebrow">What the deletion system claimed</p>
              <WorkflowIcon />
              <h2>Operational status</h2>
              {claim ? (
                <Badge value={claim} />
              ) : (
                <p>Not captured in this source</p>
              )}
              <p>
                Based on task states and acknowledgments. This does not
                independently inspect stored personal information.
              </p>
            </div>
            <div className="versus">
              <span>VS</span>
              <ArrowRight />
            </div>
            <div className="observation-card">
              <p className="eyebrow">What independent verification observed</p>
              <Shield size={29} />
              <h2>Store-level result</h2>
              <Badge value={r.verification.result} />
              <p>
                {["FALSE_SUCCESS_DETECTED", "RESIDUAL_DATA_DETECTED"].includes(
                  r.verification.result,
                )
                  ? "Eligible residual data was independently observed in a supported store. Inspect the findings and observation timestamps."
                  : r.verification.result === "VERIFIED_ABSENT"
                    ? r.verification.claim
                    : "Absence has not been established. Review uncertainty, unsupported scope and consistency timing."}
              </p>
            </div>
          </div>
          <div className="metadata-row">
            <span>
              Customer <code>{r.verification.customer_id}</code>
            </span>
            <span>
              Run <code>{r.verification.id}</code>
            </span>
            <span>
              Observed <strong>{date(r.verification.finished_at)}</strong>
            </span>
          </div>
          <div className="grid two">
            <Panel
              title="Per-store observations"
              eyebrow="Actual supported adapter results"
            >
              <div className="finding-targets">
                {r.verification.targets.map((t) => (
                  <div key={t.target}>
                    <strong>{t.target}</strong>
                    <Badge value={t.result} />
                    <small>
                      {t.absent_streak} negative samples ·{" "}
                      {date(t.last_observed_at)}
                    </small>
                  </div>
                ))}
              </div>
            </Panel>
            <Panel
              title="Evidence-backed findings"
              action={
                <button
                  onClick={() => download(`investigation-${selected}.json`, r)}
                >
                  <Download size={15} />
                  Export report
                </button>
              }
            >
              {r.findings.length ? (
                <Json value={r.findings} />
              ) : (
                <Empty
                  title="No residual finding in this report"
                  description="The selected run may be absent, pending, inconclusive or unsupported. Review the per-store results."
                />
              )}
              <div className="actions">
                <button
                  className="button"
                  onClick={() =>
                    navigate("evidence", { source, run: selected })
                  }
                >
                  Open evidence explorer <ArrowRight size={15} />
                </button>
              </div>
              <p className="panel-note">
                Data categories, target outcomes and summary details come from
                sanitized observations. A hash chain checks integrity; it does
                not prove physical erasure.
              </p>
            </Panel>
          </div>
          <Panel title="Verification event history">
            <Timeline items={r.timeline} />
          </Panel>
          {trial ? (
            <Panel
              title="Fault activation and recovery timeline"
              eyebrow={`Scenario ${trial.scenario_id} · seed ${trial.seed}`}
            >
              <Timeline
                items={trial.faults.map((f) => ({
                  kind: `${f.action} / ${f.state}`,
                  occurred_at: new Date(f.at_unix * 1000).toISOString(),
                }))}
              />
              <details>
                <summary>Retained trial status and cleanup record</summary>
                <Json
                  value={{
                    status: trial.status,
                    cleanup: trial.cleanup,
                    error: trial.error,
                  }}
                />
              </details>
            </Panel>
          ) : null}
        </>
      )}
    </>
  );
}
function WorkflowIcon() {
  return <TriangleAlert size={29} />;
}
export function FaultStudio({ session, navigate, params }: WorkspaceProps) {
  const scenarios = useApi<{ version: string; items: Scenario[] }>(
    "/research/scenarios",
  );
  const [search, setSearch] = useState("");
  const [selection, setSelection] = useState("false_ack_cache");
  const [seed, setSeed] = useState(101);
  const [ack, setAck] = useState(false);
  const [selectedJob, setSelectedJob] = useState(params.get("job") || "");
  const [confirm, setConfirm] = useState(false);
  const jobs = useApi<{ items: ResearchJob[] }>("/research/jobs", 3000);
  const job = useApi<ResearchJob>(
    selectedJob ? `/research/jobs/${selectedJob}` : null,
    (d) =>
      d && ["COMPLETED", "FAILED", "INTERRUPTED"].includes(d.state)
        ? false
        : 1500,
  );
  const scenario = scenarios.data?.items.find((s) => s.id === selection);
  const client = useQueryClient();
  const launch = useMutation({
    mutationFn: () =>
      mutation<ResearchJob>(
        "/research/jobs",
        { scenario: selection, seed, acknowledge_isolated: true },
        session.csrf,
      ),
    onSuccess: (j) => {
      setSelectedJob(j.id);
      setConfirm(false);
      setAck(false);
      client.invalidateQueries();
    },
  });
  const enabled = session.role === "research" && session.research_enabled;
  const trial = job.data?.dataset?.trials[0];
  return (
    <>
      <PageTitle
        eyebrow="Explicitly isolated research"
        title="Fault injection studio"
        description="Run the real versioned scenario framework. Faults are gated, bounded, observable and cleaned up."
      />
      <div className="notice warning">
        <TriangleAlert size={18} />
        <p>
          <strong>
            {enabled
              ? "Research controls enabled on this host."
              : "Research execution disabled for this session or host."}
          </strong>{" "}
          Execution requires the research role, explicit host opt-in, a verified
          local Docker engine and marked research project. Catalog browsing is
          always read-only.
        </p>
      </div>
      <div className="grid studio-grid">
        <Panel title="Scenario catalog" eyebrow={scenarios.data?.version}>
          <label className="search-field">
            <Search size={16} />
            <input
              aria-label="Filter scenarios"
              placeholder="Find a fault, target or category"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          {scenarios.error ? (
            <ErrorNotice error={scenarios.error} />
          ) : scenarios.isPending ? (
            <Loading />
          ) : (
            <div className="scenario-list">
              {scenarios.data?.items
                .filter((s) =>
                  `${s.name} ${s.category} ${s.targets.join(" ")}`
                    .toLowerCase()
                    .includes(search.toLowerCase()),
                )
                .map((s) => (
                  <button
                    key={s.id}
                    className={s.id === selection ? "selected" : ""}
                    onClick={() => {
                      setSelection(s.id);
                      setConfirm(false);
                    }}
                  >
                    <span className="scenario-icon">
                      <FlaskConical size={17} />
                    </span>
                    <span>
                      <small>{s.category.replaceAll("_", " ")}</small>
                      <strong>{s.name}</strong>
                      <span className="subtle">
                        {s.targets.length
                          ? s.targets.join(" · ")
                          : "All six supported targets · permitted retention"}
                      </span>
                    </span>
                    <ArrowRight size={15} />
                  </button>
                ))}
            </div>
          )}
        </Panel>
        <div className="stack">
          <Panel
            title={scenario?.name || "Select a scenario"}
            eyebrow="Recorded configuration"
          >
            {scenario ? (
              <>
                <p>{scenario.description}</p>
                <div className="definition-grid">
                  <div>
                    <span>Targeted stores</span>
                    <strong>
                      {scenario.targets.join(", ") || "No injected fault"}
                    </strong>
                  </div>
                  <div>
                    <span>Assigned failure type</span>
                    <strong>
                      {scenario.actions.join(", ") || "Normal workflow"}
                    </strong>
                  </div>
                  <div>
                    <span>Expected data state</span>
                    <Badge value={scenario.expected_data_state} />
                  </div>
                  <div>
                    <span>Expected verifier result</span>
                    <Badge value={scenario.expected_verification} />
                  </div>
                </div>
                <p className="subtle">
                  Expected labels describe the protocol. Actual truth is
                  established by fresh independent fixture reads, not these
                  labels.
                </p>
                <label className="form-stack">
                  Recorded seed
                  <input
                    type="number"
                    min={0}
                    max={2147483647}
                    value={seed}
                    onChange={(e) => setSeed(Number(e.target.value))}
                  />
                </label>
                <details>
                  <summary>Inspect full versioned configuration</summary>
                  <Json value={scenario} />
                </details>
                <button
                  className="button"
                  disabled={
                    !enabled ||
                    launch.isPending ||
                    !Number.isInteger(seed) ||
                    seed < 0 ||
                    seed > 2147483647
                  }
                  onClick={() => setConfirm(true)}
                >
                  <Play size={15} />
                  Run isolated scenario + verification
                </button>
                {confirm ? (
                  <div
                    className="research-confirm"
                    role="region"
                    aria-label="Research execution confirmation"
                  >
                    <h3>Authorize one bounded physical trial</h3>
                    <p>
                      This creates synthetic fixtures, introduces the selected
                      real fault, runs deletion and independent verification,
                      then cleans the fixtures. Services may temporarily pause
                      or restart.
                    </p>
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={ack}
                        onChange={(e) => setAck(e.target.checked)}
                      />
                      I confirm this is the isolated synthetic research stack.
                    </label>
                    <div className="actions">
                      <button onClick={() => setConfirm(false)}>Cancel</button>
                      <button
                        className="button danger-button"
                        disabled={!ack || launch.isPending}
                        onClick={() => launch.mutate()}
                      >
                        {launch.isPending
                          ? "Validating isolation…"
                          : "Authorize and execute"}
                      </button>
                    </div>
                  </div>
                ) : null}
              </>
            ) : (
              <Loading />
            )}
            {launch.error ? <ErrorNotice error={launch.error} /> : null}
          </Panel>
          <Panel
            title="Research execution"
            eyebrow={
              selectedJob ? `Job ${short(selectedJob)}` : "No job selected"
            }
          >
            {job.error ? (
              <ErrorNotice error={job.error} />
            ) : job.data ? (
              <>
                <div className="toolbar">
                  <strong>
                    {job.data.scenario} · seed {job.data.seed}
                  </strong>
                  <Badge value={job.data.state} />
                </div>
                {job.data.dataset ? (
                  <div className="mini-metrics">
                    <Metric
                      label="Physical trials"
                      value={job.data.dataset.summary.physical_trials}
                      detail="Failures retained"
                    />
                    <Metric
                      label="Decision observations"
                      value={job.data.dataset.summary.decision_rows}
                      detail="Actual recorded phases"
                    />
                  </div>
                ) : (
                  <p className="subtle">
                    {["FAILED", "INTERRUPTED"].includes(job.data.state)
                      ? "No trial journal was produced. Execution ended before a durable trial started."
                      : "Waiting for the runner's first durable journal. Acceptance is not completion."}
                  </p>
                )}
                {job.data.state === "FAILED" ||
                job.data.state === "INTERRUPTED" ? (
                  <div className="notice error" role="alert">
                    <p>
                      Execution did not complete successfully. Partial results
                      remain visible. Error:{" "}
                      {job.data.error_code ||
                        `runner exit ${job.data.exit_code ?? "unknown"}`}
                      .
                    </p>
                  </div>
                ) : null}
                {trial?.phases.map((p) => (
                  <div
                    className="phase-result"
                    key={`${p.customer_id}-${p.phase}`}
                  >
                    <div>
                      <strong>{p.phase}</strong>
                      <small>
                        Operational: {p.operational_state || "not captured"}
                      </small>
                      <small>Oracle: {p.oracle.state}</small>
                    </div>
                    <Badge value={p.methods.eraseproof?.outcome || "PENDING"} />
                    {p.verification_id ? (
                      <button
                        onClick={() =>
                          navigate("investigator", {
                            source: `job:${selectedJob}`,
                            run: p.verification_id!,
                          })
                        }
                      >
                        Investigate evidence <ArrowRight size={14} />
                      </button>
                    ) : null}
                  </div>
                ))}
                {trial ? (
                  <details>
                    <summary>Real fault timeline, errors and cleanup</summary>
                    <Json
                      value={{
                        faults: trial.faults,
                        error: trial.error,
                        cleanup: trial.cleanup,
                      }}
                    />
                  </details>
                ) : null}
                {job.data.dataset ? (
                  <button
                    onClick={() =>
                      navigate("research", { source: `job:${selectedJob}` })
                    }
                  >
                    Compare real method results <ArrowRight size={15} />
                  </button>
                ) : null}
                <p className="panel-note">
                  The runner performs the actual independent verification
                  automatically. Completed trials clean fixtures; later live
                  reads may differ from the saved pre-cleanup observations.
                </p>
              </>
            ) : (
              <Empty
                title="No execution selected"
                description="Authorize a scenario or open a previous job. This workspace never substitutes a simulation for backend execution."
              />
            )}
            <div className="record-list">
              {jobs.data?.items.map((j) => (
                <button key={j.id} onClick={() => setSelectedJob(j.id)}>
                  <span>
                    <strong>{j.scenario}</strong>
                    <small>
                      {date(j.created_at_unix)} · {short(j.id)}
                    </small>
                  </span>
                  <Badge value={j.state} />
                </button>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}

export function Research({ params, navigate }: WorkspaceProps) {
  const [source, setSource] = useState(
    params.get("source") ||
      (params.get("experiment")
        ? "experiment:" + params.get("experiment")
        : "phase4-final"),
  );
  const [page, setPage] = useState(0);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState("");
  const dataset = useDataset(source, page);
  const data = dataset.data;
  const s = data?.summary;
  const rows =
    data?.trials.filter((t) =>
      `${t.scenario_id} ${t.seed} ${t.status}`
        .toLowerCase()
        .includes(filter.toLowerCase()),
    ) || [];
  const visible = dataset.isLiveExperiment
    ? rows
    : rows.slice(page * 10, (page + 1) * 10);
  const selectedTrial = data?.trials.find((t) => t.id === selected);
  return (
    <>
      <PageTitle
        eyebrow="Reproducible experimental evidence"
        title="Research benchmarks"
        description="Inspect actual trials, faithful internal baselines, explicit denominators and measured overhead."
        action={
          data ? (
            <button
              onClick={() =>
                download(`eraseproof-${source.replaceAll(":", "-")}.json`, data)
              }
            >
              <Download size={15} />
              Export loaded data
            </button>
          ) : null
        }
      />
      <div className="toolbar">
        <SourceSelect
          source={source}
          setSource={(value) => {
            setSource(value);
            setPage(0);
            setSelected("");
          }}
        />
        {data ? (
          <span className="pill">
            Code {data.experiment.code_commit.slice(0, 7)} ·{" "}
            {data.experiment.state}
          </span>
        ) : null}
      </div>
      <SourceNotice source={source} />
      {source === "live" ? (
        <Empty
          title="Select a live experiment"
          description="Choose a recorded experiment from the evidence source menu, or use the saved historical batch."
        />
      ) : dataset.error ? (
        <ErrorNotice error={dataset.error} />
      ) : !data || !s ? (
        dataset.job && ["FAILED", "INTERRUPTED"].includes(dataset.job.state) ? (
          <Panel title="Execution ended without a trial dataset">
            <Badge value={dataset.job.state} />
            <p>
              No verification outcome is available. The runner did not produce a
              durable trial journal; this is not a successful deletion.
            </p>
            <button
              onClick={() => navigate("faults", { job: dataset.job!.id })}
            >
              Inspect execution record
            </button>
          </Panel>
        ) : (
          <Loading />
        )
      ) : (
        <>
          <div className="metrics-grid">
            <Metric
              label="Physical trials"
              value={s.physical_trials}
              detail={`${s.completed_trials} complete · ${s.failed_trials} failed · ${s.timed_out_trials} timed out`}
            />
            <Metric
              label="Customer / phase observations"
              value={s.decision_rows}
              detail={`${s.scenarios.length} selected scenarios · correlated within trials`}
            />
            <Metric
              label="Residuals independently detected"
              value={s.methods.eraseproof?.tp ?? "—"}
              detail="True positives against the independent oracle"
              tone="amber"
            />
            <Metric
              label="Conclusive coverage"
              value={percentage(s.methods.eraseproof?.coverage.value ?? null)}
              detail={`${s.methods.eraseproof?.scored_rows ?? 0} / ${s.methods.eraseproof?.binary_oracle_rows ?? 0} known-truth observations`}
              tone="green"
            />
          </div>
          <Panel
            title="Internal architectural baselines"
            eyebrow="Equal fixtures and observation phases"
          >
            <p className="panel-note">
              API acknowledgment and workflow monitoring trust declared
              operational metadata. EraseProof X reads actual stores. These are
              not commercial product comparisons. Precision, recall, FPR and FNR
              use binary oracle truth and conclusive predictions. Full positive
              yield includes all known positives, including abstentions.
            </p>
            <Table label="Baseline comparison">
              <thead>
                <tr>
                  <th>Method</th>
                  <th>TP / FP / TN / FN</th>
                  <th>Precision</th>
                  <th>Recall</th>
                  <th>FPR / FNR</th>
                  <th>Full positive yield</th>
                  <th>Known-truth abstentions</th>
                  <th>Unknown truth / clearances</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(s.methods).map(([name, m]) => (
                  <tr key={name}>
                    <td>
                      <strong>{name}</strong>
                      <small>n={m.scored_rows} conclusive</small>
                    </td>
                    <td className="mono">
                      {m.tp} / {m.fp} / {m.tn} / {m.fn}
                    </td>
                    <td>
                      {percentage(m.precision.value)}
                      <small>
                        n={m.precision.denominator} · Wilson 95% CI{" "}
                        {m.precision.wilson_95
                          ? m.precision.wilson_95
                              .map((v) => `${(v * 100).toFixed(1)}%`)
                              .join("–")
                          : "undefined"}
                      </small>
                    </td>
                    <td>
                      {percentage(m.recall.value)}
                      <small>
                        n={m.recall.denominator} · Wilson 95% CI{" "}
                        {m.recall.wilson_95
                          ? m.recall.wilson_95
                              .map((v) => `${(v * 100).toFixed(1)}%`)
                              .join("–")
                          : "undefined"}
                      </small>
                    </td>
                    <td>
                      {percentage(m.false_positive_rate.value)} /{" "}
                      {percentage(m.false_negative_rate.value)}
                    </td>
                    <td>
                      {percentage(m.full_positive_detection_yield.value)}
                      <small>
                        n={m.full_positive_detection_yield.denominator} known
                        positives
                      </small>
                    </td>
                    <td>
                      {m.abstained_on_binary_rows} / {m.binary_oracle_rows}
                    </td>
                    <td>
                      {m.oracle_unknown_rows} /{" "}
                      {m.clearance_with_unknown_oracle}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Panel>
          <Suspense fallback={<Loading />}>
            <ComparisonCharts data={data} partial={dataset.isLiveExperiment} />
          </Suspense>
          <div className="grid two">
            <Panel
              title="Uncertainty and resilience"
              eyebrow="Never scored as successful negatives"
            >
              <div className="definition-grid">
                {Object.entries(s.methods.eraseproof?.outcomes || {}).map(
                  ([outcome, count]) => (
                    <div key={outcome}>
                      <Badge value={outcome} />
                      <strong>{count}</strong>
                    </div>
                  ),
                )}
              </div>
              <div className="definition-grid">
                <div>
                  <span>Reappearances detected</span>
                  <strong>{s.recovery.reappearance_cases_detected}</strong>
                </div>
                <div>
                  <span>False operational successes exposed</span>
                  <strong>
                    {s.recovery.false_operational_success_exposed}
                  </strong>
                </div>
                <div>
                  <span>Recovery phases succeeded / failed</span>
                  <strong>
                    {s.recovery.phases_succeeded} / {s.recovery.phases_failed}
                  </strong>
                </div>
                <div>
                  <span>Retry attempts</span>
                  <strong>{s.retry_attempts}</strong>
                </div>
              </div>
            </Panel>
            <Panel
              title="Verification overhead"
              eyebrow="Actual durable data-plane commands"
            >
              <div className="overhead-list">
                {Object.entries(s.methods).map(([name, m]) => (
                  <div key={name}>
                    <span>{name}</span>
                    <strong>
                      {m.recorded_data_queries.toLocaleString()} queries
                    </strong>
                    <small>
                      Mean {m.latency_seconds.mean?.toFixed(3) ?? "undefined"} s
                      · median{" "}
                      {m.latency_seconds.median?.toFixed(3) ?? "undefined"} s ·
                      p95 {m.latency_seconds.p95?.toFixed(3) ?? "undefined"} s ·
                      n={m.latency_seconds.n}
                    </small>
                    <small>
                      Residual detection: mean{" "}
                      {m.time_to_detection_seconds.mean?.toFixed(3) ??
                        "undefined"}{" "}
                      s · median{" "}
                      {m.time_to_detection_seconds.median?.toFixed(3) ??
                        "undefined"}{" "}
                      s · p95{" "}
                      {m.time_to_detection_seconds.p95?.toFixed(3) ??
                        "undefined"}{" "}
                      s · n={m.time_to_detection_seconds.n}
                    </small>
                    <small>
                      Verified absence: mean{" "}
                      {m.time_to_verified_absence_seconds.mean?.toFixed(3) ??
                        "undefined"}{" "}
                      s · p95{" "}
                      {m.time_to_verified_absence_seconds.p95?.toFixed(3) ??
                        "undefined"}{" "}
                      s · n={m.time_to_verified_absence_seconds.n}
                    </small>
                  </div>
                ))}
              </div>
              <p className="panel-note">
                Store command counts exclude oracle/control work and uncommitted
                crash-lost probes. Shared-stack CPU/memory snapshots are not
                causal per-method resource attribution.
              </p>
            </Panel>
          </div>
          <Panel
            title="Physical trial ledger"
            eyebrow={
              dataset.isLiveExperiment
                ? "Live experiment · paginated backend records"
                : "Complete saved physical-trial dataset"
            }
            action={
              <label className="search-field compact">
                <Search size={15} />
                <input
                  aria-label="Filter trials"
                  placeholder="Scenario, seed, status"
                  value={filter}
                  onChange={(e) => {
                    setFilter(e.target.value);
                    setPage(0);
                  }}
                />
              </label>
            }
          >
            <Table label="Research trials">
              <thead>
                <tr>
                  <th>Scenario / seed</th>
                  <th>Workload</th>
                  <th>Status</th>
                  <th>Observations</th>
                  <th>Elapsed</th>
                  <th>Inspect</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((t) => (
                  <tr key={t.id}>
                    <td>
                      <strong>{t.scenario_id}</strong>
                      <small>
                        Seed {t.seed} · attempt {t.attempt}
                      </small>
                    </td>
                    <td>{t.tier}</td>
                    <td>
                      <Badge value={t.status} />
                    </td>
                    <td>{t.phases.length}</td>
                    <td>{t.elapsed_seconds?.toFixed(2) ?? "in progress"} s</td>
                    <td>
                      <button onClick={() => setSelected(t.id)}>
                        Inspect trial
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
            {dataset.isLiveExperiment ? (
              <div className="pager">
                <span>
                  Backend page {page + 1} · 20 records maximum · search applies
                  to loaded page
                </span>
                <div>
                  <button
                    disabled={page === 0}
                    onClick={() => setPage(page - 1)}
                  >
                    Previous
                  </button>
                  <button
                    disabled={data.trials.length < 20}
                    onClick={() => setPage(page + 1)}
                  >
                    Next
                  </button>
                </div>
              </div>
            ) : (
              <Pager
                page={page}
                total={rows.length}
                limit={10}
                onChange={setPage}
              />
            )}
          </Panel>
          {selectedTrial ? (
            <Panel
              title={`Trial ${short(selectedTrial.id)}`}
              eyebrow={selectedTrial.scenario_id}
            >
              <div className="phase-list">
                {selectedTrial.phases.map((p) => (
                  <div className="phase-result" key={p.phase + p.customer_id}>
                    <div>
                      <strong>
                        {p.phase} · {short(p.customer_id)}
                      </strong>
                      <small>
                        Oracle: {p.oracle.state} · {date(p.observed_at_unix)}
                      </small>
                    </div>
                    <Badge value={p.methods.eraseproof?.outcome || "PENDING"} />
                    {p.verification_id ? (
                      <button
                        onClick={() =>
                          navigate("investigator", {
                            source: source.startsWith("experiment:")
                              ? "live"
                              : source,
                            run: p.verification_id!,
                          })
                        }
                      >
                        Open finding <ExternalLink size={14} />
                      </button>
                    ) : null}
                  </div>
                ))}
              </div>
              <details>
                <summary>Fault timeline, actual errors and cleanup</summary>
                <Json
                  value={{
                    faults: selectedTrial.faults,
                    error: selectedTrial.error,
                    cleanup: selectedTrial.cleanup,
                  }}
                />
              </details>
            </Panel>
          ) : null}
          <Panel title="Reproducibility and limits">
            <p>
              Wilson intervals describe these selected synthetic observations.
              Customers and phases in a trial are correlated; small samples do
              not establish population accuracy, enterprise superiority or
              compliance. The initial failed batch remains separately
              inspectable. Extended workloads remain unexecuted unless a new
              recorded experiment establishes otherwise.
            </p>
            <details>
              <summary>
                Code revision, seed plan, configuration and environment
              </summary>
              <Json value={data.experiment} />
            </details>
          </Panel>
        </>
      )}
    </>
  );
}

export function filterEvidence(
  items: Report["evidence"],
  target: string,
  outcome: string,
  search: string,
) {
  return items.filter(
    (e) =>
      (!target || e.target === target) &&
      (!outcome || e.body.result === outcome) &&
      `${e.digest} ${e.previous_digest} ${e.target} ${JSON.stringify(e.body)}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
}

export function EvidenceExplorer({ params }: WorkspaceProps) {
  const [source, setSource] = useState(params.get("source") || "phase4-final");
  const [chosen, setChosen] = useState(params.get("run") || "");
  const [target, setTarget] = useState("");
  const [outcome, setOutcome] = useState("");
  const [search, setSearch] = useState("");
  const dataset = useDataset(source);
  const runs = useApi<Page<RunSummary>>(
    source === "live"
      ? "/live/customer/v1/dashboard/verifications?limit=100"
      : null,
    5000,
  );
  const choices = runChoices(dataset.data, runs.data?.items);
  const selected = chosen || choices[0]?.id || "";
  const report = useReport(source, selected);
  const r = report.data;
  const evidence = filterEvidence(r?.evidence || [], target, outcome, search);
  return (
    <>
      <PageTitle
        eyebrow="Sanitized independent observations"
        title="Evidence explorer"
        description="Search actual probe records, policy references and evidence chains. No raw customer profile export."
        action={
          r ? (
            <button
              onClick={() => download(`verification-${selected}.json`, r)}
            >
              <Download size={15} />
              Download JSON report
            </button>
          ) : null
        }
      />
      <div className="toolbar">
        <SourceSelect
          source={source}
          setSource={(s) => {
            setSource(s);
            setChosen("");
            setTarget("");
            setOutcome("");
          }}
        />
        <label className="inline-label">
          Verification run
          <select
            aria-label="Evidence run"
            value={selected}
            onChange={(e) => setChosen(e.target.value)}
          >
            {selected && !choices.some((c) => c.id === selected) ? (
              <option value={selected}>Linked run · {selected}</option>
            ) : null}
            {choices.map((c) => (
              <option value={c.id} key={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <SourceNotice source={source} />
      {dataset.error || runs.error || report.error ? (
        <ErrorNotice error={dataset.error || runs.error || report.error} />
      ) : !selected ? (
        <Empty
          title="No evidence records"
          description="Start independent verification or choose a saved research dataset."
        />
      ) : !r ? (
        <Loading />
      ) : (
        <>
          <div className="evidence-toolbar">
            <label className="search-field">
              <Search size={16} />
              <input
                aria-label="Search evidence"
                placeholder="Digest, target or sanitized observation"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
            <label>
              Target
              <select
                aria-label="Evidence target"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
              >
                <option value="">All targets</option>
                {[...new Set(r.evidence.map((e) => e.target))].map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
            </label>
            <label>
              Outcome
              <select
                aria-label="Evidence outcome"
                value={outcome}
                onChange={(e) => setOutcome(e.target.value)}
              >
                <option value="">All outcomes</option>
                {[...new Set(r.evidence.map((e) => String(e.body.result)))].map(
                  (o) => (
                    <option key={o}>{o}</option>
                  ),
                )}
              </select>
            </label>
          </div>
          <Panel
            title={`${evidence.length} matching observations`}
            eyebrow={`Run ${short(selected)} · ${r.evidence.length} total records`}
          >
            <div className="metadata-row">
              <span>
                Policy digest <code>{r.verification.policy_digest}</code>
              </span>
              <span>
                Correlation <code>{r.verification.correlation_id}</code>
              </span>
            </div>
            {evidence.map((e) => (
              <details className="evidence-record" key={e.id}>
                <summary>
                  <span className="evidence-sequence">#{e.sequence}</span>
                  <strong>{e.target}</strong>
                  <Badge value={String(e.body.result)} />
                  <span className="mono">{e.digest.slice(0, 16)}…</span>
                  <time>{date(e.created_at)}</time>
                </summary>
                <div className="evidence-body">
                  <p>
                    Round {e.round_no} · evidence record {e.id}
                  </p>
                  <Json value={e.body} />
                  <div className="digest-row">
                    <span>Digest</span>
                    <code>{e.digest}</code>
                    <span>Previous digest</span>
                    <code>{e.previous_digest || "Chain origin"}</code>
                  </div>
                </div>
              </details>
            ))}
            {evidence.length === 0 ? (
              <Empty
                title="No matching observations"
                description="Change the target, outcome or search filter. Missing records are not evidence of absence."
              />
            ) : null}
            <details>
              <summary>Integrity result and captured policy</summary>
              <Json
                value={{
                  integrity: r.evidence_integrity,
                  policy: r.verification.policy,
                }}
              />
            </details>
            <p className="panel-note">
              Hash-chain verification detects certain alterations relative to
              the retained chain. It is not hardware attestation, physical
              erasure proof or protection from a privileged administrator.
            </p>
          </Panel>
        </>
      )}
    </>
  );
}
