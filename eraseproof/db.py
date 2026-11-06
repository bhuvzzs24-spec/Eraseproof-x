from pathlib import Path
from contextlib import contextmanager
from collections.abc import Iterator
import psycopg
from psycopg.rows import dict_row
from eraseproof.config import DATABASE_URL


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    with psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=3) as conn:
        yield conn


def migrate() -> None:
    with connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(7654321)")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS public.schema_migrations (version text PRIMARY KEY)"
        )
        for path in sorted(Path("migrations").glob("*.sql")):
            if not conn.execute(
                "SELECT 1 FROM schema_migrations WHERE version=%s", (path.name,)
            ).fetchone():
                conn.execute(path.read_text())
                conn.execute("INSERT INTO schema_migrations VALUES (%s)", (path.name,))


if __name__ == "__main__":
    migrate()
