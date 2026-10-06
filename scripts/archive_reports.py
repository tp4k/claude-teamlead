#!/usr/bin/env python3
"""Archive current-round reports before a same-round verification retry.

Run only after every agent writing these reports finishes. Moving the reports
out of the run's top level prevents waits and resume routing from accepting
earlier evidence. Implementation reports and briefs remain in place.
"""
from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path


REPORT = re.compile(
    r"(?:(?:verifier|triage)(?:-ws\d+)?-r\d+"
    r"|review(?:-ws\d+)?-r\d+-(?:code|security|perf))\.md"
)


def archive_reports(run: Path, reports: list[Path]) -> Path | None:
    """Validate all paths before moving any report into a unique directory."""
    run = run.resolve()
    if not (run / "repo.txt").is_file():
        raise ValueError("The run directory must contain repo.txt.")
    sources: list[Path] = []
    for report in reports:
        source = report if report.is_absolute() else run / report
        if source.is_symlink():
            raise ValueError(f"Report paths must not be symlinks: {report}")
        source = source.resolve()
        if source.parent != run or not REPORT.fullmatch(source.name):
            raise ValueError(f"Not a top-level verification or review report: {report}")
        if source.exists() and not source.is_file():
            raise ValueError(f"Not a report file: {report}")
        if source.is_file() and source not in sources:
            sources.append(source)
    if not sources:
        return None
    history = run / "report-history"
    if history.is_symlink():
        raise ValueError("The report-history directory must not be a symlink.")
    history.mkdir(exist_ok=True)
    archive = Path(tempfile.mkdtemp(prefix="snapshot-", dir=history))
    for source in sources:
        source.rename(archive / source.name)
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("reports", nargs="+", type=Path)
    args = parser.parse_args()
    try:
        archive = archive_reports(args.run, args.reports)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Cannot archive reports: {exc}\n")
    print(f"REPORT_HISTORY={archive}" if archive else "No existing reports to archive.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
