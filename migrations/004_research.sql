CREATE SCHEMA research;
CREATE TABLE research.experiments (
 id uuid PRIMARY KEY, state text NOT NULL CHECK(state IN ('RUNNING','COMPLETED','FAILED','INTERRUPTED')),
 code_commit text NOT NULL, configuration jsonb NOT NULL, configuration_digest text NOT NULL,
 environment jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz
);
CREATE TABLE research.trials (
 id uuid PRIMARY KEY, experiment_id uuid NOT NULL REFERENCES research.experiments(id),
 logical_key text NOT NULL, attempt integer NOT NULL CHECK(attempt>0), scenario_id text NOT NULL, seed bigint NOT NULL,
 state text NOT NULL CHECK(state IN ('RUNNING','COMPLETED','FAILED','TIMED_OUT','INTERRUPTED')),
 body jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE(experiment_id,logical_key,attempt)
);
CREATE INDEX research_trials_exp_idx ON research.trials(experiment_id,logical_key,attempt);
CREATE TABLE research.leases (
 project text PRIMARY KEY, experiment_id uuid NOT NULL, executor_id uuid NOT NULL,
 expires_at timestamptz NOT NULL
);
GRANT USAGE ON SCHEMA research TO verification_coordinator;
GRANT SELECT ON research.experiments,research.trials TO verification_coordinator;
CREATE TABLE research.fault_leases (
 project text NOT NULL, service text NOT NULL, token uuid NOT NULL, PRIMARY KEY(project,service)
);
