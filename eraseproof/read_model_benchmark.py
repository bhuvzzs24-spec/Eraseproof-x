"""Paired real-database profiling of the list projection; never changes verifier checks."""

from contextlib import contextmanager
import json
import statistics
import time
from eraseproof.db import connection
from eraseproof import dashboard_backend, verification


class Counted:
    def __init__(self, db):
        self.db = db
        self.calls = 0

    def execute(self, *args, **kwargs):
        self.calls += 1
        return self.db.execute(*args, **kwargs)


def measure():
    observations = []
    for repeat in range(5):
        pair = {}
        for name in ("legacy", "summary") if repeat % 2 == 0 else ("summary", "legacy"):
            counter = None

            @contextmanager
            def counted_connection():
                nonlocal counter
                with connection() as db:
                    counter = Counted(db)
                    yield counter

            started = time.perf_counter()
            if name == "legacy":
                with counted_connection() as db:
                    db.execute("SET LOCAL statement_timeout='3000ms'")
                    total = db.execute("SELECT count(*) AS n FROM verification.runs").fetchone()[
                        "n"
                    ]
                    ids = db.execute(
                        "SELECT id FROM verification.runs ORDER BY created_at DESC,id LIMIT 100"
                    ).fetchall()
                    items = [verification.view(db, r["id"]) for r in ids]
            else:
                original = dashboard_backend.connection
                try:
                    dashboard_backend.connection = counted_connection
                    result = dashboard_backend.runs(limit=100, offset=0, result=None)
                    items, total = result["items"], result["total"]
                finally:
                    dashboard_backend.connection = original
            elapsed = time.perf_counter() - started
            fields = (
                "id",
                "customer_id",
                "deletion_request_id",
                "state",
                "result",
                "round_no",
                "created_at",
                "finished_at",
            )
            pair[name] = {
                "rows": len(items),
                "total": total,
                "queries": counter.calls,
                "elapsed_seconds": elapsed,
                "metadata": [{k: item[k] for k in fields} for item in items],
            }
        assert pair["legacy"]["metadata"] == pair["summary"]["metadata"]
        for value in pair.values():
            del value["metadata"]
        observations.append(pair)
    assert observations[0]["summary"]["rows"] >= 2
    return {
        "basis": "Five paired CI PostgreSQL measurements of legacy full-view-per-row and bounded list summary; same visible metadata; warm shared host, not production throughput",
        "observations": observations,
        "median_seconds": {
            name: statistics.median(row[name]["elapsed_seconds"] for row in observations)
            for name in ("legacy", "summary")
        },
        "verification_data_plane_checks_changed": False,
    }


if __name__ == "__main__":
    print(json.dumps(measure(), indent=2))
