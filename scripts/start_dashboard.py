"""Load only server-side credentials, then start the local engineering gateway."""

from pathlib import Path
import os
import uvicorn

for name in (".env", ".dashboard.env"):
    path = Path(name)
    if path.exists():
        for line in path.read_text().splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key, value)
uvicorn.run(
    "eraseproof.dashboard_gateway:app",
    host="127.0.0.1",
    port=int(os.getenv("DASHBOARD_PORT", "8010")),
    access_log=False,
)
