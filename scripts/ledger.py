#!/usr/bin/env python3
"""Apply a run's deferred-work rows to the repo's ledger, at close.

Usage: python3 ledger.py apply <$RUN> --ledger <repo>/docs/deferred-work.md

The writer agent appends rows to `$RUN/deferred-rows.md` during the run, so the
repo tree stays clean until then. Each row's id is `<basename $RUN>-<n>` (n is
1-based in file order). The row is inserted at gap index
`int(sha256(id)) mod (rows + 1)` among the ledger's data rows: 0 is above the
first one, `rows` is below the last. Rows go in one at a time, each against the
current row count. Existing lines are never rewritten, so there is no migration
and parallel branches rarely touch the same line. Never stages or commits.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

ROWS_FILE = "deferred-rows.md"
NEW_LEDGER = (
    "# Deferred work\n"
    "\n"
    "`/teamlead` runs append rows here.\n"
    "\n"
    "| Date | Run | Item | Why deferred | Source |\n"
    "|---|---|---|---|---|\n"
)
SEPARATOR = re.compile(r"\A\s*\|[\s:|-]*-{3,}[\s:|-]*\Z")


def is_row(line: str) -> bool:
    return line.lstrip().startswith("|")


def gap_index(row_id: str, rows: int) -> int:
    return int(hashlib.sha256(row_id.encode("utf-8")).hexdigest(), 16) % (rows + 1)


def read_rows(run: Path) -> list[str]:
    path = run / ROWS_FILE
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [ln for ln in lines if is_row(ln)]


def table_bounds(lines: list[str]) -> tuple[int, int]:
    """(index of the first data row, one past the last contiguous data row)."""
    for i, line in enumerate(lines):
        if SEPARATOR.match(line):
            end = i + 1
            while end < len(lines) and is_row(lines[end]):
                end += 1
            return i + 1, end
    raise ValueError("ledger has no table separator line")


def insert_row(lines: list[str], row: str, row_id: str) -> list[str]:
    """`lines` keep their line endings; the new line is spliced in alone."""
    plain = [ln.rstrip("\r\n") for ln in lines]
    first, end = table_bounds(plain)
    at = first + gap_index(row_id, end - first)
    if at == len(lines) and lines and not lines[-1].endswith("\n"):
        return lines[:-1] + [lines[-1] + "\n", row]
    return lines[:at] + [row + "\n"] + lines[at:]


def apply(run: Path, ledger: Path) -> int:
    rows = read_rows(run)
    if not rows:
        print(f"LEDGER rows=0 file={ledger}")
        return 0
    text = ledger.read_text(encoding="utf-8") if ledger.is_file() else NEW_LEDGER
    lines = text.splitlines(keepends=True)
    for n, row in enumerate(rows, start=1):
        lines = insert_row(lines, row, f"{run.resolve().name}-{n}")
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text("".join(lines), encoding="utf-8")
    print(f"LEDGER rows={len(rows)} file={ledger}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("apply", help="insert $RUN/deferred-rows.md into the ledger")
    p.add_argument("run", type=Path)
    p.add_argument("--ledger", type=Path, required=True)
    args = parser.parse_args()
    try:
        return apply(args.run, args.ledger)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
