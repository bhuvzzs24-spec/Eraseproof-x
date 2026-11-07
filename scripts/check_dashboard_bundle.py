"""Fail on a real host secret accidentally embedded into browser assets; never print its value."""

import os
from pathlib import Path

root = Path(__file__).resolve().parent.parent
values = {
    key: value
    for key, value in os.environ.items()
    if key.endswith(("_TOKEN", "_PASSWORD")) and len(value) >= 24
}
for name in (".env", ".dashboard.env"):
    path = root / name
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                if key.endswith(("_TOKEN", "_PASSWORD")) and len(value) >= 24:
                    values[key] = value
files = [p for p in (root / "frontend/dist").rglob("*") if p.is_file()]
if not files:
    raise SystemExit("Build the dashboard before scanning browser assets")
for path in files:
    raw = path.read_bytes()
    for key, value in values.items():
        if value.encode() in raw:
            raise SystemExit(f"Server credential {key} leaked into browser assets")
print(
    f"Checked {len(files)} browser assets against {len(values)} configured host credentials: no leaks"
)
