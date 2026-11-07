"""Read-only GitHub gate: exact main revision, green runtime CI and owner environment review."""

import json
import os
import re
import subprocess


def api(path):
    return json.loads(subprocess.check_output(["gh", "api", path], text=True))


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    owner = repo.split("/")[0]
    sha = os.environ["RELEASE_SHA"]
    if not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise ValueError("exact 40-character revision required")
    environment = api(f"repos/{repo}/environments/production")
    reviewers = [
        reviewer.get("reviewer", {}).get("login", "").lower()
        for rule in environment.get("protection_rules", [])
        if rule.get("type") == "required_reviewers"
        for reviewer in rule.get("reviewers", [])
    ]
    if owner.lower() not in reviewers:
        raise ValueError("production environment must require repository-owner review")
    runs = api(
        f"repos/{repo}/actions/workflows/ci.yaml/runs?head_sha={sha}&status=success&per_page=20"
    )["workflow_runs"]
    if not any(
        r["head_branch"] == "main" and r["event"] == "push" and r["conclusion"] == "success"
        for r in runs
    ):
        raise ValueError("successful main CI required for this revision")
    subprocess.run(["git", "merge-base", "--is-ancestor", sha, "origin/main"], check=True)
    print("Exact revision, successful main CI and owner environment review requirements verified")


if __name__ == "__main__":
    main()
