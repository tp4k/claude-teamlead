#!/usr/bin/env python3
"""Check that pruning slims the runs it keeps without losing a report.

Run it with:  python3 scripts/test_prune_runs.py

Slimming deletes inside a run that is still wanted, so the cases are about what
it must not touch: reports, a run an agent may still be writing, and anything a
symlink reaches outside the run.
"""
from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from prune_runs import prune

OLD = time.time() - 2 * 3600


def age(path: Path) -> None:
    for dirpath, dirnames, filenames in os.walk(path):
        for name in dirnames + filenames:
            os.utime(Path(dirpath) / name, (OLD, OLD), follow_symlinks=False)
    os.utime(path, (OLD, OLD))


class SlimTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        home = Path(self.temp.name) / "home"
        os.environ["TEAMLEAD_HOME"] = str(home)
        self.addCleanup(os.environ.pop, "TEAMLEAD_HOME")
        # Today's stamp keeps the run inside maxAgeDays, so only slimming applies.
        stamp = time.strftime("%Y-%m-%d-%H%M")
        self.rundir = home / "runs" / "repo" / f"{stamp}-task"
        self.rundir.mkdir(parents=True)
        (self.rundir /"review-ws1-r1-code.md").write_text("VERDICT: APPROVED\n")
        (self.rundir /"probe-tools").mkdir()
        (self.rundir /"probe-tools" / "probe.py").write_text("print(1)\n")
        clone = self.rundir /"probe-ws1-r1-code"
        (clone / ".git").mkdir(parents=True)
        (clone / "src.ts").write_text("x\n")
        (self.rundir /"scratch" / "node_modules" / "pkg").mkdir(parents=True)

    def test_kept_run_loses_checkouts_and_node_modules_but_no_report(self) -> None:
        age(self.rundir)
        removed = prune(dry_run=False)
        self.assertEqual(
            sorted(p.relative_to(self.rundir).as_posix() for p in removed),
            ["probe-ws1-r1-code", "scratch/node_modules"],
        )
        self.assertTrue((self.rundir /"review-ws1-r1-code.md").is_file())
        self.assertTrue((self.rundir /"probe-tools" / "probe.py").is_file())
        self.assertTrue((self.rundir /"scratch").is_dir())

    def test_run_touched_within_the_hour_is_left_alone(self) -> None:
        age(self.rundir)
        (self.rundir /"verify-ws1-r2.md").write_text("OUTCOME: PASS\n")
        self.assertEqual(prune(dry_run=False), [])
        self.assertTrue((self.rundir /"probe-ws1-r1-code" / "src.ts").is_file())

    def test_symlinked_node_modules_outside_the_run_survives(self) -> None:
        outside = Path(self.temp.name) / "real_node_modules"
        (outside / "pkg").mkdir(parents=True)
        (self.rundir /"linked").mkdir()
        (self.rundir /"linked" / "node_modules").symlink_to(outside)
        age(self.rundir)
        removed = prune(dry_run=False)
        self.assertNotIn(self.rundir /"linked" / "node_modules", removed)
        self.assertTrue((outside / "pkg").is_dir())

    def test_dry_run_reports_without_deleting(self) -> None:
        age(self.rundir)
        self.assertEqual(len(prune(dry_run=True)), 2)
        self.assertTrue((self.rundir /"probe-ws1-r1-code" / "src.ts").is_file())
        self.assertTrue((self.rundir /"scratch" / "node_modules").is_dir())


if __name__ == "__main__":
    unittest.main()
