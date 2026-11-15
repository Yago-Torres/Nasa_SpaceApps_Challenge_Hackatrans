#!/usr/bin/env python3
"""Create proposed AGRO BLACK BOX GitHub Issues from planning/issues.json.

Dry run by default. Needs authenticated GitHub CLI (`gh`). No Python packages required.
Run: uv run --no-project python scripts/publish_roadmap_issues.py --repo OWNER/REPO --apply
Never marks Issues approved or mutates existing Issues.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "issues.json"
LABEL_COLORS = {
    "needs-vote": "d73a4a", "roadmap": "5319e7",
    "phase:F0": "0052cc", "phase:F1": "0e8a16", "phase:F2": "1d76db",
    "phase:F3": "fbca04", "phase:F4": "c2e0c6",
    "lead:A": "bfe5bf", "lead:B": "d4c5f9", "lead:C": "f9d0c4",
    "priority:P0": "b60205", "priority:P1": "fbca04",
}


def gh(*args: str) -> str:
    cmd = ["gh", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"GitHub CLI failed ({' '.join(cmd[:4])}): {result.stderr.strip()}")
    return result.stdout.strip()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", help="OWNER/REPO. Defaults to current git remote's GitHub repository")
    p.add_argument("--apply", action="store_true", help="Create missing Issues and labels. Dry run otherwise")
    p.add_argument("--limit", type=int, default=0, help="Only consider first N Issues (0 = all)")
    args = p.parse_args()
    if not SOURCE.is_file():
        p.error("Missing issues.json")
    issues = json.loads(SOURCE.read_text(encoding="utf8"))
    if args.limit < 0:
        p.error("--limit must be >= 0")
    if args.limit:
        issues = issues[: args.limit]
    identifiers = [item["id"] for item in issues]
    if len(identifiers) != len(set(identifiers)):
        p.error("Duplicate planning ID in source")
    repo = args.repo
    if not args.apply and not repo:
        print("DRY RUN (offline): pass --repo OWNER/REPO to check existing GitHub Issues")
        for x in issues:
            print(f"  [PROPOSED] [{x['id']}] {x['title']} ({x['lead']}, {x['phase']})")
        print(f"{len(issues)} entries; run with --repo OWNER/REPO --apply after human review")
        return 0
    if repo is None:
        repo = gh("repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        p.error("Repository must be in OWNER/REPO format")
    # State=all prevents duplicate planning IDs if an issue was previously closed.
    existing = json.loads(gh("issue", "list", "--repo", repo, "--state", "all", "--limit", "1000", "--json", "title,number,url"))
    codes = {m.group(1): x for x in existing if (m := re.match(r"\[(ABB-\d+)\]", x["title"]))}
    missing = [i for i in issues if i["id"] not in codes]
    print(f"Target: {repo} | Existing planning Issues: {len(issues)-len(missing)} | Missing: {len(missing)}")
    for item in missing:
        print(f"  {'CREATE' if args.apply else 'WOULD CREATE'} [{item['id']}] {item['title']}")
    if not args.apply:
        return 0
    if not missing:
        print("Everything already exists; no changes made.")
        return 0
    current_labels = json.loads(gh("label", "list", "--repo", repo, "--limit", "200", "--json", "name"))
    current_names = {x["name"] for x in current_labels}
    for name, color in LABEL_COLORS.items():
        if name not in current_names:
            gh("label", "create", name, "--repo", repo, "--color", color, "--description", "Roadmap planning label (not a human approval)")
    for item in missing:
        labels = ["roadmap", "needs-vote", f"phase:{item['phase']}", f"lead:{item['lead']}", f"priority:{item['priority']}"]
        dep_links = []
        for dep in item["deps"]:
            if dep in codes:
                dep_links.append(f"{dep}: #{codes[dep]['number']}")
            else:
                dep_links.append(f"{dep}: todavía sin Issue publicada")
        body = item["body"] + ("\n\n**Dependencias enlazadas en GitHub:** " + ", ".join(dep_links) if dep_links else "")
        result = gh("issue", "create", "--repo", repo, "--title", f"[{item['id']}] {item['title']}", "--body", body, "--label", ",".join(labels))
        print("  CREATED", result)
        match = re.search(r"/(\d+)$", result)
        if match:
            codes[item['id']] = {'number': int(match.group(1)), 'url': result}
    print(f"Created {len(missing)} proposals. Human approval still required.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
