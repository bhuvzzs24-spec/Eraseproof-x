"""Execute real scenarios then summarize their measured observations; never fabricate results."""

import os
from pathlib import Path
import subprocess
import sys
import json
from eraseproof.evaluation import summarize

if os.getenv("APP_ENV", "demo") != "demo" or os.getenv("ERASEPROOF_TEST_FAULTS") != "1":
    raise SystemExit(
        "Requires demo environment and ERASEPROOF_TEST_FAULTS=1; uses disposable synthetic faults."
    )
environment = {**os.environ, "RUN_INTEGRATION": "1"}
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_verification_integration.py", "-v"],
    env=environment,
)
if result.returncode:
    raise SystemExit(result.returncode)
path = Path("work/phase3-evaluation.json")
if not path.exists():
    raise SystemExit("No measured scenario results were produced.")
data = json.loads(path.read_text())
assert summarize(data["cases"]) == data["summary"]
print(json.dumps(data["summary"], indent=2))
print("Full reproducible case measurements:", path.resolve())
