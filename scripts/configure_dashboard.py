"""Generate local-only role credentials without printing or overwriting secrets."""

from pathlib import Path
import secrets

path = Path(".dashboard.env")
if path.exists():
    raise SystemExit("Existing .dashboard.env preserved")
values = {
    f"DASHBOARD_{role}_PASSWORD": secrets.token_urlsafe(32)
    for role in ("READONLY", "OPERATOR", "RESEARCH")
}
values["OPERATOR_TOKEN"] = secrets.token_urlsafe(32)
values.update(
    DASHBOARD_ORIGIN="http://127.0.0.1:3000",
    DASHBOARD_ENABLE_RESEARCH="0",
    DASHBOARD_RESEARCH_PROJECT="eraseproof-research",
    APP_ENV="demo",
)
path.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
path.chmod(0o600)
print("Created .dashboard.env mode 0600. Read role passwords locally; do not commit this file.")
