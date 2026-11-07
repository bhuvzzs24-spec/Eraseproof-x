"""Only documentation/measured-artifact-only commits may skip the expensive Docker job."""

import os
from pathlib import Path
import subprocess

base = os.getenv("BASE_SHA", "")
if not base or set(base) == {"0"}:
    runtime = True
else:
    paths = subprocess.check_output(
        ["git", "diff", "--name-only", base, "HEAD"], text=True
    ).splitlines()

    def artifact(path):
        return path == "README.md" or path.startswith(
            ("docs/", "research/phase-4/results/", "research/phase-4/generated/")
        )

    runtime = any(not artifact(path) for path in paths)
with Path(os.environ["GITHUB_OUTPUT"]).open("a") as stream:
    stream.write(f"runtime={str(runtime).lower()}\n")
print("Runtime-affecting changes:", runtime)
