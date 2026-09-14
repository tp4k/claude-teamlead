"""Prune old run directories under $TEAMLEAD_HOME/runs/ (default ~/.teamlead/runs/).

Usage: python3 prune_runs.py [--dry-run]

Policy comes from $TEAMLEAD_HOME/config.json, with the defaults in paths.py:
  maxAgeDays       delete a run older than this ...
  keepLastPerRepo  ... unless it is among the newest N runs of its repo.
Only directories matching runs/<repo>/<YYYY-MM-DD-HHMM>-<slug>/ are ever removed.
"""
from __future__ import annotations

import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

import paths

RUN_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2}-\d{4})-[a-z0-9][a-z0-9-]*$")


def run_started(name: str) -> datetime | None:
    m = RUN_NAME.match(name)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y-%m-%d-%H%M")


def prune(dry_run: bool) -> list[Path]:
    runs_dir = paths.runs_dir()
    max_age = timedelta(days=paths.setting("maxAgeDays", valid=paths.positive_int))
    keep_last = paths.setting("keepLastPerRepo", valid=paths.nonneg_int)
    cutoff = datetime.now() - max_age
    removed: list[Path] = []
    if not runs_dir.is_dir():
        return removed
    for repo_dir in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        runs = [(run_started(p.name), p) for p in repo_dir.iterdir() if p.is_dir()]
        dated = sorted(((d, p) for d, p in runs if d is not None),
                       key=lambda x: x[0], reverse=True)
        for started, path in dated[keep_last:]:
            if started < cutoff:
                removed.append(path)
                if not dry_run:
                    shutil.rmtree(path)
        if not dry_run and not any(repo_dir.iterdir()):
            repo_dir.rmdir()
    return removed


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv[1:]
    gone = prune(dry)
    verb = "would remove" if dry else "removed"
    for p in gone:
        print(f"{verb} {p.relative_to(paths.runs_dir())}")
    print(f"prune: {len(gone)} run(s) {verb}")
