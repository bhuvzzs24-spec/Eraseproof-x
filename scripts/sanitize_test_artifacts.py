"""Redact actual ephemeral test credentials from text diagnostics; do not change outcomes."""

import json
import os
from pathlib import Path

root = Path(__file__).resolve().parent.parent
secrets = {
    value
    for key, value in os.environ.items()
    if key.endswith(("_PASSWORD", "_TOKEN")) and len(value) >= 24
}
for name in (".env", ".dashboard.env", "work/hosted-ci/hosted.env"):
    p = root / name
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                if key.endswith(("_PASSWORD", "_TOKEN")) and len(value) >= 24:
                    secrets.add(value)
p = root / "work/hosted-ci/test-credentials.json"
if p.exists():
    secrets.add(json.loads(p.read_text())["password"])
changed = 0
for folder in (
    "frontend/test-results",
    "frontend/playwright-report",
    "frontend/test-results-hosted",
):
    for p in (root / folder).rglob("*"):
        if p.is_file() and p.suffix in (".json", ".html", ".md", ".txt"):
            text = p.read_text()
            updated = text
            for value in secrets:
                updated = updated.replace(value, "[REDACTED EPHEMERAL TEST CREDENTIAL]")
            if updated != text:
                p.write_text(updated)
                changed += 1
print(
    f"Checked text test artifacts against {len(secrets)} configured credentials; redacted {changed} files; outcomes unchanged"
)
