"""Post a section review (or any Markdown file) as a GitHub issue.

Uses the GitHub token that git already stores in Windows Credential Manager
(read through `git credential fill`; never printed). Usage:

    uv run python scripts/gh_issue.py --title "..." --body-file review/01_schedule.md [--label review]
    uv run python scripts/gh_issue.py --check          # only verify access

Every section's review goes up this way so it can be read and answered from
the Claude app without opening the repo.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request

REPO = "uty101/CDS-Pricing-and-Bootstrapping"
API = f"https://api.github.com/repos/{REPO}"


def token() -> str:
    out = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for line in out.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    raise SystemExit("no GitHub credential found in the git credential store")


def call(method: str, path: str, payload: dict | None = None) -> dict | list:
    req = urllib.request.Request(
        API + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        method=method,
        headers={
            "Authorization": f"Bearer {token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--title")
    ap.add_argument("--body-file")
    ap.add_argument("--label", action="append", default=[])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    if args.check:
        repo = call("GET", "")
        print(f"repo ok: {repo['full_name']}, issues enabled: {repo['has_issues']}")
        return
    if not (args.title and args.body_file):
        ap.error("--title and --body-file are required")
    with open(args.body_file, encoding="utf-8") as fh:
        body = fh.read()
    issue = call("POST", "/issues", {"title": args.title, "body": body, "labels": args.label})
    print(issue["html_url"])


if __name__ == "__main__":
    sys.exit(main())
