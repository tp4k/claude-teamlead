"""Prune old run directories under $TEAMLEAD_HOME/runs/ (default ~/.teamlead/runs/).

Usage: python3 prune_runs.py [--dry-run]

Policy comes from $TEAMLEAD_HOME/config.json, with the defaults in paths.py:
  maxAgeDays       delete a run older than this ...
  keepLastPerRepo  ... unless it is among the newest N runs of its repo.
Only directories matching runs/<repo>/<YYYY-MM-DD-HHMM>-<slug>/ are ever removed.

A run that is kept is slimmed instead: any repository checkout and any
node_modules inside it is removed, and every report stays. A run's value is its
text — briefs, reviews, verdicts, the stream — while a checkout is a copy of
commits that already live in the repo. One run whose reviewers cloned the repo
per round kept 31 GB of probe clones next to 3 MB of reports; the reviewer role
forbids those clones now, and this is the backstop for an agent that ignores it.
A run touched within the last hour may still have an agent in it, so it is left
alone.
"""
from __future__ import annotations

import os
import re
import time
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast

import paths

RUN_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2}-\d{4})-[a-z0-9][a-z0-9-]*$")
LIVE_SECONDS = 3600


def run_started(name: str) -> datetime | None:
    m = RUN_NAME.match(name)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y-%m-%d-%H%M")


def recently_touched(run: Path) -> bool:
    # Reports are written at the top of the run dir, so its direct entries are
    # enough; walking a tree that may hold gigabytes would cost more than it saves.
    stamps = [run.stat().st_mtime] + [p.lstat().st_mtime for p in run.iterdir()]
    return time.time() - max(stamps) < LIVE_SECONDS


def bulk_dirs(run: Path) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, _ in os.walk(run):
        here = Path(dirpath)
        if here != run and (here / ".git").exists():
            found.append(here)
            dirnames.clear()
            continue
        for name in list(dirnames):
            # os.walk lists a symlink to a directory without entering it; it
            # points outside the run as often as not, so it is never ours to delete.
            if (here / name).is_symlink():
                dirnames.remove(name)
            elif name == "node_modules":
                found.append(here / name)
                dirnames.remove(name)
    return found


def slim(run: Path, dry_run: bool) -> list[Path]:
    if recently_touched(run):
        return []
    found = bulk_dirs(run)
    if not dry_run:
        for path in found:
            shutil.rmtree(path)
    return found


def prune(dry_run: bool) -> list[Path]:
    runs_dir = paths.runs_dir()
    # `valid` only lets a positive int through, and the default is one too.
    days = cast(int, paths.setting("maxAgeDays", valid=paths.positive_int))
    max_age = timedelta(days=days)
    keep_last = cast(int, paths.setting("keepLastPerRepo", valid=paths.nonneg_int))
    cutoff = datetime.now() - max_age
    removed: list[Path] = []
    if not runs_dir.is_dir():
        return removed
    for repo_dir in sorted(p for p in runs_dir.iterdir()
                           if p.is_dir() and not p.is_symlink()):
        # A symlinked run reaches outside the runs tree, where slimming would
        # delete checkouts this script never created.
        runs = [(run_started(p.name), p) for p in repo_dir.iterdir()
                if p.is_dir() and not p.is_symlink()]
        dated = sorted(((d, p) for d, p in runs if d is not None),
                       key=lambda x: x[0], reverse=True)
        for i, (started, path) in enumerate(dated):
            if i >= keep_last and started < cutoff:
                removed.append(path)
                if not dry_run:
                    shutil.rmtree(path)
            else:
                removed.extend(slim(path, dry_run))
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
