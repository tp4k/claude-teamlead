#!/usr/bin/env python3
"""Route a $RUN one phase at a time: wait, read the verdicts, print what to spawn.

    python3 $SKILL/scripts/next.py $RUN

Scaffold: every caller-facing name exists and raises NotImplementedError until
the GREEN commit.
"""
from __future__ import annotations

import sys
from pathlib import Path


def decide(run: Path, argv: list[str]) -> int:
    raise NotImplementedError("next.py decide")


def main(argv: list[str]) -> int:
    return decide(Path(argv[1]) if len(argv) > 1 else Path("."), argv[2:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
