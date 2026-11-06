CREATE SCHEMA deletion;
ALTER TABLE orders.orders ALTER COLUMN customer_id DROP NOT NULL;
ALTER TABLE delivery.outbox ADD COLUMN cancelled_at timestamptz;

CREATE TABLE deletion.requests (
 id uuid PRIMARY KEY, customer_id uuid NOT NULL UNIQUE, correlation_id uuid NOT NULL,
 state text NOT NULL CHECK(state IN ('REQUESTED','IN_PROGRESS','RETRYING','COMPLETED_REPORTED','PARTIALLY_FAILED','FAILED')),
 schema_version integer NOT NULL DEFAULT 1 CHECK(schema_version=1),
 actor text NOT NULL CHECK(actor='demo-operator'), retry_round integer NOT NULL DEFAULT 0 CHECK(retry_round BETWEEN 0 AND 3),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX deletion_request_state_idx ON deletion.requests(state,created_at);
CREATE TABLE deletion.idempotency_keys (
 key_hash text PRIMARY KEY CHECK(length(key_hash)=64), request_id uuid NOT NULL REFERENCES deletion.requests(id),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE deletion.tombstones (
 customer_id uuid PRIMARY KEY, request_id uuid NOT NULL UNIQUE REFERENCES deletion.requests(id),
 lifecycle text NOT NULL DEFAULT 'DELETING' CHECK(lifecycle IN ('DELETING','DELETED')),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE deletion.tasks (
 id uuid PRIMARY KEY, request_id uuid NOT NULL REFERENCES deletion.requests(id),
 target text NOT NULL CHECK(target IN ('customer','orders','cache','search','analytics','event_history')),
 state text NOT NULL CHECK(state IN ('PENDING','DISPATCHED','RUNNING','SUCCEEDED_REPORTED','RETRY_WAIT','FAILED_TERMINAL')),
 attempt_count integer NOT NULL DEFAULT 0 CHECK(attempt_count>=0),
 cycle_attempts integer NOT NULL DEFAULT 0 CHECK(cycle_attempts>=0),
 max_attempts integer NOT NULL DEFAULT 3 CHECK(max_attempts BETWEEN 1 AND 5),
 active_attempt uuid, next_attempt_at timestamptz NOT NULL DEFAULT now(), lease_until timestamptz,
 last_failure_code text, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(request_id,target)
);
CREATE INDEX deletion_due_idx ON deletion.tasks(state,next_attempt_at);
CREATE INDEX deletion_lease_idx ON deletion.tasks(lease_until) WHERE state IN ('DISPATCHED','RUNNING');
CREATE TABLE deletion.attempts (
 id uuid PRIMARY KEY, task_id uuid NOT NULL REFERENCES deletion.tasks(id), attempt_no integer NOT NULL CHECK(attempt_no>0),
 outcome text NOT NULL CHECK(outcome IN ('DISPATCHED','RUNNING','SUCCEEDED_REPORTED','RETRY_WAIT','FAILED_TERMINAL')),
 worker_id text, failure_code text, dispatched_at timestamptz NOT NULL DEFAULT now(), started_at timestamptz,
 finished_at timestamptz, duration_ms integer CHECK(duration_ms>=0), UNIQUE(task_id,attempt_no)
);
ALTER TABLE deletion.tasks ADD CONSTRAINT active_attempt_fk FOREIGN KEY(active_attempt) REFERENCES deletion.attempts(id);
CREATE TABLE deletion.events (
 sequence bigserial PRIMARY KEY, request_id uuid NOT NULL REFERENCES deletion.requests(id),
 task_id uuid REFERENCES deletion.tasks(id), kind text NOT NULL,
 from_state text, to_state text, code text, correlation_id uuid NOT NULL,
 actor text NOT NULL CHECK(actor IN ('demo-operator','scheduler','worker')),
 occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX deletion_timeline_idx ON deletion.events(request_id,sequence);
CREATE FUNCTION deletion.immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'deletion audit/tombstones are immutable' USING ERRCODE='23514'; END;
$$;
CREATE TRIGGER audit_append_only BEFORE UPDATE OR DELETE ON deletion.events FOR EACH ROW EXECUTE FUNCTION deletion.immutable();
CREATE TRIGGER tombstone_no_delete BEFORE DELETE ON deletion.tombstones FOR EACH ROW EXECUTE FUNCTION deletion.immutable();
CREATE FUNCTION deletion.guard_tombstone() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.customer_id<>OLD.customer_id OR NEW.request_id<>OLD.request_id OR
    (OLD.lifecycle='DELETED' AND NEW.lifecycle<>'DELETED') THEN
    RAISE EXCEPTION 'tombstone cannot be reversed' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER tombstone_monotonic BEFORE UPDATE ON deletion.tombstones FOR EACH ROW EXECUTE FUNCTION deletion.guard_tombstone();
CREATE FUNCTION deletion.guard_state() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE allowed boolean;
BEGIN
 IF NEW.state=OLD.state THEN RETURN NEW; END IF;
 IF TG_TABLE_NAME='requests' THEN
  allowed := (OLD.state='REQUESTED' AND NEW.state='IN_PROGRESS') OR
    (OLD.state IN ('IN_PROGRESS','RETRYING') AND NEW.state IN ('RETRYING','COMPLETED_REPORTED','PARTIALLY_FAILED','FAILED')) OR
    (OLD.state IN ('PARTIALLY_FAILED','FAILED') AND NEW.state='RETRYING');
  IF NEW.state='COMPLETED_REPORTED' AND
    ((SELECT count(*) FROM deletion.tasks WHERE request_id=NEW.id)<>6 OR
     EXISTS(SELECT 1 FROM deletion.tasks WHERE request_id=NEW.id AND state<>'SUCCEEDED_REPORTED')) THEN
   allowed := false;
  END IF;
 ELSE
  allowed := (OLD.state IN ('PENDING','RETRY_WAIT') AND NEW.state IN ('DISPATCHED','FAILED_TERMINAL')) OR
    (OLD.state='DISPATCHED' AND NEW.state IN ('RUNNING','RETRY_WAIT','FAILED_TERMINAL')) OR
    (OLD.state='RUNNING' AND NEW.state IN ('SUCCEEDED_REPORTED','RETRY_WAIT','FAILED_TERMINAL')) OR
    (OLD.state='FAILED_TERMINAL' AND NEW.state='PENDING');
 END IF;
 IF NOT allowed THEN RAISE EXCEPTION 'invalid deletion state transition' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER request_state_guard BEFORE UPDATE ON deletion.requests FOR EACH ROW EXECUTE FUNCTION deletion.guard_state();
CREATE TRIGGER task_state_guard BEFORE UPDATE ON deletion.tasks FOR EACH ROW EXECUTE FUNCTION deletion.guard_state();

ALTER TABLE deletion.tasks ADD CONSTRAINT task_request_pair UNIQUE(id,request_id);
ALTER TABLE deletion.events ADD CONSTRAINT audit_task_request_fk FOREIGN KEY(task_id,request_id) REFERENCES deletion.tasks(id,request_id);

ALTER TABLE deletion.tasks ADD CONSTRAINT task_attempt_budget CHECK(cycle_attempts<=max_attempts AND cycle_attempts<=attempt_count);
