export type Role = "readonly" | "operator" | "research";
export interface Session {
  role: Role;
  csrf: string;
  research_enabled: boolean;
}
export interface Customer {
  id: string;
  name: string | null;
  created_at: string;
  lifecycle: string;
  request_id: string | null;
}
export interface Page<T> {
  items: T[];
  limit: number;
  offset: number;
  total?: number;
}
export interface Attempt {
  id: string;
  attempt_no: number;
  outcome: string;
  failure_code: string | null;
  duration_ms: number | null;
  started_at: string | null;
}
export interface Task {
  id: string;
  target: string;
  state: string;
  attempt_count: number;
  last_failure_code: string | null;
  next_attempt_at: string;
  attempts: Attempt[];
}
export interface Deletion {
  id: string;
  customer_id: string;
  state: string;
  created_at: string;
  updated_at: string;
  correlation_id: string;
  tasks: Task[];
}
export interface Target {
  target: string;
  result: string;
  absent_streak: number;
  probe_failures: number;
  last_observed_at: string | null;
}
export interface Run {
  id: string;
  deletion_request_id: string;
  customer_id: string;
  correlation_id: string;
  state: string;
  result: string;
  policy_digest: string;
  policy: Record<string, unknown>;
  round_no: number;
  created_at: string;
  deadline_at: string;
  finished_at: string | null;
  targets: Target[];
  claim: string;
}
export interface Evidence {
  id: string;
  sequence: number;
  target: string;
  round_no: number;
  body: Record<string, unknown>;
  digest: string;
  previous_digest: string;
  created_at: string;
}
export interface TimelineEvent {
  sequence?: number;
  kind: string;
  code?: string | null;
  occurred_at: string;
  to_state?: string | null;
  actor?: string;
  request_id?: string;
  source?: string;
  entity_id?: string;
  state?: string | null;
}
export interface Report {
  verification: Run;
  evidence: Evidence[];
  evidence_integrity: Record<string, unknown>;
  findings: Record<string, unknown>[];
  excluded_targets: string[];
  incomplete_targets: string[];
  timeline: TimelineEvent[];
  freshness: string;
}
export interface Health {
  items: { service: string; state: string; observed_at_unix: number }[];
  basis: string;
}
export interface Snapshot {
  customer_count: number;
  deletions: { state: string; count: number }[];
  verifications: { result: string; count: number }[];
  recent_findings: Pick<
    Run,
    "id" | "customer_id" | "deletion_request_id" | "result" | "created_at"
  >[];
  activity: TimelineEvent[];
  observed_at: string;
  basis: string;
}
export interface Ratio {
  numerator: number;
  denominator: number;
  value: number | null;
  wilson_95: [number, number] | null;
}
export interface Distribution {
  n: number;
  mean: number | null;
  median: number | null;
  p95: number | null;
  stdev_population: number | null;
}
export interface Method {
  tp: number;
  fp: number;
  tn: number;
  fn: number;
  binary_oracle_rows: number;
  scored_rows: number;
  abstained_on_binary_rows: number;
  oracle_unknown_rows: number;
  clearance_with_unknown_oracle: number;
  precision: Ratio;
  recall: Ratio;
  coverage: Ratio;
  false_positive_rate: Ratio;
  false_negative_rate: Ratio;
  full_positive_detection_yield: Ratio;
  latency_seconds: Distribution;
  time_to_detection_seconds: Distribution;
  time_to_verified_absence_seconds: Distribution;
  outcomes: Record<string, number>;
  recorded_data_queries: number;
  storage_category_outcomes: Record<string, Record<string, number>>;
}
export interface Summary {
  physical_trials: number;
  completed_trials: number;
  failed_trials: number;
  timed_out_trials: number;
  interrupted_trials: number;
  decision_rows: number;
  scenarios: string[];
  methods: Record<string, Method>;
  recovery: {
    phases_succeeded: number;
    phases_failed: number;
    reappearance_cases_detected: number;
    false_operational_success_exposed: number;
  };
  retry_attempts: number;
  deletion_latency_seconds: Distribution;
}
export interface Prediction {
  prediction: string;
  outcome: string;
  elapsed_seconds: number;
  data_queries: number;
  targets?: Record<string, string>;
}
export interface Phase {
  phase: string;
  customer_id: string;
  deletion_request_id: string;
  verification_id?: string;
  operational_state?: string;
  oracle: { state: string; targets: Record<string, unknown> };
  methods: Record<string, Prediction>;
  observed_at_unix: number;
}
export interface Trial {
  id: string;
  scenario_id: string;
  seed: number;
  tier: string;
  status: string;
  attempt: number;
  phases: Phase[];
  faults: {
    action: string;
    state: string;
    at_unix: number;
    [key: string]: unknown;
  }[];
  cleanup?: Record<string, unknown>;
  error?: Record<string, unknown>;
  elapsed_seconds?: number;
}
export interface Experiment {
  id: string;
  state: string;
  code_commit: string;
  configuration_digest: string;
  configuration: Record<string, unknown>;
  started_at_unix?: number;
  created_at?: string;
  environment: Record<string, unknown>;
}
export interface Dataset {
  experiment: Experiment;
  summary: Summary;
  trials: Trial[];
  historical?: boolean;
}
export interface Scenario {
  id: string;
  name: string;
  description: string;
  category: string;
  targets: string[];
  actions: string[];
  expected_data_state: string;
  expected_orchestration: string;
  expected_verification: string;
  [key: string]: unknown;
}
export interface ResearchJob {
  id: string;
  scenario: string;
  seed: number;
  state: string;
  created_at_unix: number;
  dataset?: Dataset;
  error_code?: string;
  exit_code?: number;
}
export type Navigate = (
  workspace: string,
  params?: Record<string, string>,
) => void;
