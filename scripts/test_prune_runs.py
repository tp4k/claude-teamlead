#!/usr/bin/env python3
"""Check that pruning slims the runs it keeps without losing a report.

Run it with:  python3 scripts/test_prune_runs.py

Slimming deletes inside a run that is still wanted, so the cases are about what
it must not touch: reports, a run an agent may still be writing, and anything a
symlink reaches outside the run.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

import prune_runs
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
        (self.rundir / "review-ws1-r1-code.md").write_text("VERDICT: APPROVED\n")
        (self.rundir / "probe-tools").mkdir()
        (self.rundir / "probe-tools" / "probe.py").write_text("print(1)\n")
        clone = self.rundir / "probe-ws1-r1-code"
        (clone / ".git").mkdir(parents=True)
        (clone / "src.ts").write_text("x\n")
        (self.rundir / "scratch" / "node_modules" / "pkg").mkdir(parents=True)

    def test_kept_run_loses_checkouts_and_node_modules_but_no_report(self) -> None:
        age(self.rundir)
        removed = prune(dry_run=False)
        self.assertEqual(
            sorted(p.relative_to(self.rundir).as_posix() for p in removed),
            ["probe-ws1-r1-code", "scratch/node_modules"],
        )
        self.assertFalse((self.rundir / "probe-ws1-r1-code").exists())
        self.assertFalse((self.rundir / "scratch" / "node_modules").exists())
        self.assertTrue((self.rundir / "review-ws1-r1-code.md").is_file())
        self.assertTrue((self.rundir / "probe-tools" / "probe.py").is_file())
        self.assertTrue((self.rundir / "scratch").is_dir())

    def test_run_touched_within_the_hour_is_left_alone(self) -> None:
        age(self.rundir)
        # Rewriting an existing report leaves the run dir's own mtime aged, so
        # only the direct-child timestamps can tell that the run is live.
        (self.rundir / "review-ws1-r1-code.md").write_text("VERDICT: NEEDS_REWORK\n")
        self.assertLess(self.rundir.stat().st_mtime, time.time() - 3600)
        self.assertEqual(prune(dry_run=False), [])
        self.assertTrue((self.rundir / "probe-ws1-r1-code" / "src.ts").is_file())

    def test_symlinked_node_modules_outside_the_run_survives(self) -> None:
        outside = Path(self.temp.name) / "real_node_modules"
        (outside / "pkg").mkdir(parents=True)
        (self.rundir / "linked").mkdir()
        (self.rundir / "linked" / "node_modules").symlink_to(outside)
        age(self.rundir)
        removed = prune(dry_run=False)
        self.assertNotIn(self.rundir / "linked" / "node_modules", removed)
        self.assertTrue((outside / "pkg").is_dir())

    def test_symlinked_run_is_not_slimmed(self) -> None:
        outside = Path(self.temp.name) / "elsewhere"
        (outside / "checkout" / ".git").mkdir(parents=True)
        stamp = time.strftime("%Y-%m-%d-%H%M")
        (self.rundir.parent / f"{stamp}-link").symlink_to(outside)
        age(self.rundir)
        age(outside)
        prune(dry_run=False)
        self.assertTrue((outside / "checkout" / ".git").is_dir())

    def test_path_a_peer_prune_already_removed_is_not_an_error(self) -> None:
        age(self.rundir)
        clone = self.rundir / "probe-ws1-r1-code"
        gone = self.rundir / "probe-ws9-r1-code"
        # The peer kickoff listed both and has already deleted the first one.
        with mock.patch.object(prune_runs, "bulk_dirs", return_value=[gone, clone]):
            self.assertEqual(prune(dry_run=False), [gone, clone])
        self.assertFalse(clone.exists())

    def test_child_vanishing_mid_scan_is_not_an_error(self) -> None:
        age(self.rundir)
        listed = list(self.rundir.iterdir()) + [self.rundir / "deleted-by-peer"]
        with mock.patch.object(Path, "iterdir", lambda _: iter(listed)):
            self.assertFalse(prune_runs.recently_touched(self.rundir))

    def test_run_a_peer_deleted_whole_is_not_an_error(self) -> None:
        age(self.rundir)
        gone = self.rundir.parent / "2026-01-01-0000-deleted-by-peer"
        self.assertEqual(prune_runs.slim(gone, dry_run=False), [])

    def test_repo_dir_a_peer_removed_is_not_an_error(self) -> None:
        age(self.rundir)
        repo_dir = self.rundir.parent
        real_iterdir = Path.iterdir

        def iterdir(path: Path) -> Iterator[Path]:
            if path == repo_dir:
                raise FileNotFoundError(path)
            return real_iterdir(path)

        with mock.patch.object(Path, "iterdir", iterdir):
            self.assertEqual(prune(dry_run=False), [])

    def test_tree_a_peer_keeps_emptying_is_finished(self) -> None:
        clone = self.rundir / "probe-ws1-r1-code"
        real_rmtree = shutil.rmtree
        calls: list[Path] = []

        def racing_rmtree(path: Path) -> None:
            calls.append(path)
            if len(calls) < 3:
                raise FileNotFoundError(path)  # the peer took a child first
            real_rmtree(path)

        with mock.patch.object(prune_runs.shutil, "rmtree", racing_rmtree):
            prune_runs.remove(clone)
        self.assertEqual(len(calls), 3)
        self.assertFalse(clone.exists())

    def test_dry_run_reports_without_deleting(self) -> None:
        age(self.rundir)
        self.assertEqual(len(prune(dry_run=True)), 2)
        self.assertTrue((self.rundir / "probe-ws1-r1-code" / "src.ts").is_file())
        self.assertTrue((self.rundir / "scratch" / "node_modules").is_dir())


if __name__ == "__main__":
    unittest.main()
