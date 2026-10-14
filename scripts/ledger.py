#!/usr/bin/env python3
"""Apply a run's deferred-work rows to the repo's ledger, at close.

Usage: python3 ledger.py apply <$RUN> --ledger <repo>/docs/deferred-work.md
"""
from __future__ import annotations

import sys
from pathlib import Path


def gap_index(row_id: str, rows: int) -> int:
    raise NotImplementedError


def apply(run: Path, ledger: Path) -> int:
    raise NotImplementedError


def main() -> int:
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(main())
