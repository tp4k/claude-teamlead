#!/usr/bin/env python3
"""Regression suite for scripts/ledger.py.

Run it with:  python3 scripts/test_ledger.py

The insert position is the contract: a row's gap is `sha256(id) mod (rows+1)`
over the ledger's data rows, so the expected files here are built from that
formula independently of the script, and each case picks a run name whose
gaps are the edge ones (above the first row, below the last) that an
off-by-one or a per-process hash would miss.

No pytest dependency, as with the other suites.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "ledger.py"
COLS = "| Date | Run | Item | Why deferred | Source |"
HEAD = f"# Deferred work\n\nnote\n\n{COLS}\n|---|---|---|---|---|\n"
OLD = [f"| 2026-01-0{i} | old-{i} | item {i} | why | triage |" for i in range(1, 5)]
NEW = [
    "| 2026-10-14 | new | first | why | triage |",
    "| 2026-10-14 | new | second | why | triage |",
]
TAIL = "\nOther notes\n"

results: list[tuple[str, bool, str]] = []


def gap(row_id: str, rows: int) -> int:
    return int(hashlib.sha256(row_id.encode()).hexdigest(), 16) % (rows + 1)


def run_name_for(first: int, second: int) -> str:
    """A run basename whose two rows land at these gaps (4 rows, then 5)."""
    for i in range(10000):
        name = f"2026-10-14-1000-t{i}"
        if gap(f"{name}-1", 4) == first and gap(f"{name}-2", 5) == second:
            return name
    raise AssertionError("no run name found")


def expected(old: list[str], new: list[str], name: str) -> list[str]:
    rows = list(old)
    for n, row in enumerate(new, start=1):
        rows.insert(gap(f"{name}-{n}", len(rows)), row)
    return rows


def apply(root: Path, name: str, rows: list[str], ledger_text: str | None):
    run = root / name
    run.mkdir()
    if rows:
        (run / "deferred-rows.md").write_text("\n".join(rows) + "\n")
    ledger = root / "docs" / "deferred-work.md"
    if ledger_text is not None:
        ledger.parent.mkdir(exist_ok=True)
        ledger.write_text(ledger_text)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "apply", str(run), "--ledger", str(ledger)],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc, ledger


def record(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def case_gap_index_from_hash(root: Path) -> None:
    for first, second in ((4, 5), (0, 0), (2, 3)):
        sub = root / f"g{first}{second}"
        sub.mkdir()
        name = run_name_for(first, second)
        text = HEAD + "\n".join(OLD) + "\n" + TAIL
        proc, ledger = apply(sub, name, NEW, text)
        want = HEAD + "\n".join(expected(OLD, NEW, name)) + "\n" + TAIL
        got = ledger.read_text()
        record(
            f"rows land at sha256(id) mod (rows+1): gaps {first},{second}",
            got == want and proc.stdout.strip() == f"LEDGER rows=2 file={ledger}",
            f"stdout={proc.stdout!r} got={got!r}",
        )


def case_existing_lines_byte_identical(root: Path) -> None:
    name = run_name_for(4, 5)
    for label, tail in (("trailing newline", TAIL), ("no trailing newline", "")):
        sub = root / label.replace(" ", "-")
        sub.mkdir()
        text = HEAD + "\n".join(OLD) + ("\n" + tail if tail else "")
        _, ledger = apply(sub, name, NEW, text)
        got = ledger.read_text()
        stripped = "".join(
            ln for ln in got.splitlines(keepends=True) if ln.rstrip("\n") not in NEW
        )
        if not tail:
            # the new last row sits after a newline the original lacked
            stripped = stripped.rstrip("\n")
        record(
            f"existing bytes unchanged ({label})",
            stripped == text and all(r in got for r in NEW),
            f"got={got!r}",
        )


def case_deterministic(root: Path) -> None:
    name = run_name_for(2, 3)
    outs = []
    for sub in ("a", "b"):
        (root / sub).mkdir()
        _, ledger = apply(root / sub, name, NEW, HEAD + "\n".join(OLD) + "\n")
        outs.append(ledger.read_text())
    record(
        "same inputs give an identical file",
        outs[0] == outs[1] and all(r in outs[0] for r in NEW),
        repr(outs),
    )


def case_multiple_rows_sequential(root: Path) -> None:
    name = run_name_for(4, 5)
    _, ledger = apply(root, name, NEW, HEAD + "\n".join(OLD) + "\n")
    lines = ledger.read_text().splitlines()
    want = expected(OLD, NEW, name)
    record(
        "rows applied in file order, each against the current row count",
        lines[6:] == want and want[-1] == NEW[1] and want[-2] == NEW[0],
        repr(lines),
    )


def case_creates_missing_ledger(root: Path) -> None:
    name = run_name_for(0, 0)
    proc, ledger = apply(root, name, NEW[:1], None)
    lines = ledger.read_text().splitlines() if ledger.exists() else []
    record(
        "missing ledger is created with heading, note, header, row",
        proc.returncode == 0
        and lines[:1] == ["# Deferred work"]
        and any(ln.startswith("| Date | Run |") for ln in lines)
        and lines[-1] == NEW[0]
        and len(lines) == 6 + 1,
        repr(lines),
    )


def case_no_rows_no_write(root: Path) -> None:
    for label, rows in (("absent file", None), ("empty file", [])):
        sub = root / label.replace(" ", "-")
        sub.mkdir()
        run = sub / "2026-10-14-1000-x"
        run.mkdir()
        if rows is not None:
            (run / "deferred-rows.md").write_text("")
        ledger = sub / "docs" / "deferred-work.md"
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "apply", str(run), "--ledger", str(ledger)],
            capture_output=True,
            text=True,
            check=False,
        )
        record(
            f"no rows, no ledger write ({label})",
            proc.returncode == 0 and not ledger.exists(),
            f"rc={proc.returncode} err={proc.stderr!r}",
        )


CASES = [
    case_gap_index_from_hash,
    case_existing_lines_byte_identical,
    case_deterministic,
    case_multiple_rows_sequential,
    case_creates_missing_ledger,
    case_no_rows_no_write,
]


def main() -> int:
    for case in CASES:
        with tempfile.TemporaryDirectory() as d:
            case(Path(d))
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            print(f"      {detail}")
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"\n=== {len(results) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
