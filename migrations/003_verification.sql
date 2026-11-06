CREATE TABLE deletion.order_manifest (
 request_id uuid NOT NULL REFERENCES deletion.requests(id), order_id uuid NOT NULL,
 PRIMARY KEY(request_id,order_id)
);
CREATE TABLE deletion.scope_captures (
 request_id uuid PRIMARY KEY REFERENCES deletion.requests(id), captured_at timestamptz NOT NULL DEFAULT now(),
 version text NOT NULL CHECK(version='scope-v1')
);
CREATE TRIGGER manifest_immutable BEFORE UPDATE OR DELETE ON deletion.order_manifest FOR EACH ROW EXECUTE FUNCTION deletion.immutable();
CREATE TRIGGER capture_immutable BEFORE UPDATE OR DELETE ON deletion.scope_captures FOR EACH ROW EXECUTE FUNCTION deletion.immutable();

CREATE SCHEMA verification;
CREATE TABLE verification.runs (
 id uuid PRIMARY KEY, deletion_request_id uuid NOT NULL REFERENCES deletion.requests(id),
 customer_id uuid NOT NULL, correlation_id uuid NOT NULL, idempotency_hash text NOT NULL,
 state text NOT NULL CHECK(state IN ('QUEUED','RUNNING','WAITING','FINISHED')),
 result text NOT NULL CHECK(result IN ('PENDING_CONSISTENCY','VERIFIED_ABSENT','RESIDUAL_DATA_DETECTED','FALSE_SUCCESS_DETECTED','INCONCLUSIVE','UNSUPPORTED')),
 policy jsonb NOT NULL, policy_digest text NOT NULL CHECK(length(policy_digest)=64),
 round_no integer NOT NULL DEFAULT 0 CHECK(round_no BETWEEN 0 AND 8), active_message uuid,
 lease_until timestamptz, next_check_at timestamptz NOT NULL DEFAULT now(),
 created_at timestamptz NOT NULL DEFAULT now(), deadline_at timestamptz NOT NULL,
 finished_at timestamptz, actor text NOT NULL DEFAULT 'demo-verifier' CHECK(actor='demo-verifier'),
 UNIQUE(deletion_request_id,idempotency_hash)
);
CREATE INDEX verification_due_idx ON verification.runs(state,next_check_at);
CREATE INDEX verification_history_idx ON verification.runs(deletion_request_id,created_at);
CREATE TABLE verification.targets (
 run_id uuid NOT NULL REFERENCES verification.runs(id), target text NOT NULL,
 result text NOT NULL DEFAULT 'PENDING_CONSISTENCY' CHECK(result IN ('PENDING_CONSISTENCY','VERIFIED_ABSENT','RESIDUAL_DATA_DETECTED','INCONCLUSIVE','UNSUPPORTED')),
 absent_streak integer NOT NULL DEFAULT 0 CHECK(absent_streak>=0),
 probe_failures integer NOT NULL DEFAULT 0 CHECK(probe_failures>=0), last_observed_at timestamptz, consistency_anchor timestamptz,
 PRIMARY KEY(run_id,target)
);
CREATE TABLE verification.evidence (
 id uuid PRIMARY KEY, run_id uuid NOT NULL REFERENCES verification.runs(id),
 sequence integer NOT NULL CHECK(sequence>0), target text NOT NULL,
 round_no integer NOT NULL, body jsonb NOT NULL, digest text NOT NULL CHECK(length(digest)=64),
 previous_digest text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(run_id,sequence),
 UNIQUE(run_id,round_no,target)
);
CREATE TABLE verification.timeline (
 sequence bigserial PRIMARY KEY, run_id uuid NOT NULL REFERENCES verification.runs(id),
 kind text NOT NULL, code text, occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX verification_evidence_run_idx ON verification.evidence(run_id,sequence);
CREATE TRIGGER evidence_append_only BEFORE UPDATE OR DELETE ON verification.evidence FOR EACH ROW EXECUTE FUNCTION deletion.immutable();
CREATE TRIGGER verification_timeline_append_only BEFORE UPDATE OR DELETE ON verification.timeline FOR EACH ROW EXECUTE FUNCTION deletion.immutable();
CREATE FUNCTION verification.guard_run() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.policy<>OLD.policy OR NEW.policy_digest<>OLD.policy_digest OR NEW.customer_id<>OLD.customer_id OR
    NEW.deletion_request_id<>OLD.deletion_request_id OR NEW.correlation_id<>OLD.correlation_id OR
    NEW.created_at<>OLD.created_at OR NEW.deadline_at<>OLD.deadline_at THEN
    RAISE EXCEPTION 'immutable verification scope changed' USING ERRCODE='23514';
 END IF;
 IF OLD.state='FINISHED' THEN RAISE EXCEPTION 'verification history is immutable' USING ERRCODE='23514'; END IF;
 IF NEW.state<>OLD.state AND NOT (
   (OLD.state IN ('QUEUED','WAITING') AND NEW.state IN ('RUNNING','FINISHED')) OR
   (OLD.state='RUNNING' AND NEW.state IN ('WAITING','FINISHED'))
 ) THEN RAISE EXCEPTION 'invalid verification transition' USING ERRCODE='23514'; END IF;
 IF NEW.state='FINISHED' AND NEW.result='VERIFIED_ABSENT' AND (
   (SELECT count(*) FROM verification.targets WHERE run_id=NEW.id)<>(SELECT count(*) FROM jsonb_object_keys(NEW.policy->'targets')) OR
   EXISTS(SELECT 1 FROM verification.targets WHERE run_id=NEW.id AND result<>'VERIFIED_ABSENT') OR
   NOT EXISTS(SELECT 1 FROM verification.evidence WHERE run_id=NEW.id)
 ) THEN RAISE EXCEPTION 'premature verification success' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER verification_state_guard BEFORE UPDATE ON verification.runs FOR EACH ROW EXECUTE FUNCTION verification.guard_run();

DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='verification_probe') THEN CREATE ROLE verification_probe NOLOGIN; END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='verification_coordinator') THEN CREATE ROLE verification_coordinator NOLOGIN; END IF;
END $$;
ALTER TABLE delivery.outbox ENABLE ROW LEVEL SECURITY;
CREATE POLICY verifier_read_outbox ON delivery.outbox FOR SELECT TO verification_probe USING(true);
CREATE POLICY verifier_publish ON delivery.outbox FOR INSERT TO verification_coordinator WITH CHECK(event_type='verification.command');

CREATE FUNCTION verification.guard_target() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF EXISTS(SELECT 1 FROM verification.runs WHERE id=OLD.run_id AND state='FINISHED') THEN
  RAISE EXCEPTION 'finished verification targets are immutable' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER finished_targets_immutable BEFORE UPDATE ON verification.targets FOR EACH ROW EXECUTE FUNCTION verification.guard_target();
ALTER TABLE verification.evidence ADD CONSTRAINT evidence_body_identity CHECK(
 body->>'run_id'=run_id::text AND body->>'target'=target AND (body->>'round_no')::int=round_no AND (body->>'sequence')::int=sequence AND body->>'previous_digest'=previous_digest
);
