#!/usr/bin/env python3
"""Check same-round retry routing and preservation of earlier reports."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from archive_reports import archive_reports
from run_state import Run, stream_next


SCRIPTS = Path(__file__).resolve().parent


class ArchiveReportsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name) / "run"
        self.run.mkdir()
        (self.run / "repo.txt").write_text(str(self.run.parent / "repo"))

    def report(self, name: str, body: str) -> Path:
        path = self.run / name
        path.write_text(body)
        return path

    def wait(self, *reports: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "wait_for.py"), "--timeout", "1",
             "--poll", "1", *map(str, reports)],
            capture_output=True, text=True,
        )

    def test_wait_and_resume_require_new_reports(self) -> None:
        briefs = self.run / "briefs"
        briefs.mkdir()
        (briefs / "impl-ws1-r1.md").write_text("# Brief\n")
        implementer = self.report("implementer-ws1-r1.md", "status: done\n")
        verifier = self.report("verifier-r1.md", "OUTCOME: PASS\n")
        review = self.report("review-r1-code.md", "VERDICT: APPROVED\n")
        triage = self.report("triage-r1.md", "VERDICT: APPROVED\n")
        old = {p.name: p.read_bytes() for p in (verifier, review, triage)}
        self.assertEqual(self.wait(verifier, review).returncode, 0)
        self.assertIsNone(stream_next(Run(self.run), 1))

        archived = archive_reports(self.run, [verifier, review, triage])
        self.assertIsNotNone(archived)
        assert archived is not None
        for name, body in old.items():
            self.assertEqual((archived / name).read_bytes(), body)
            self.assertFalse((self.run / name).exists())
        self.assertEqual(implementer.read_text(), "status: done\n")
        self.assertEqual(stream_next(Run(self.run), 1)[1], "verifier not run")
        pending = self.wait(verifier, review)
        self.assertEqual(pending.returncode, 2)
        self.assertNotIn("OUTCOME: PASS", pending.stdout)
        self.assertNotIn("VERDICT: APPROVED", pending.stdout)

        verifier.write_text("OUTCOME: FAIL\n")
        review.write_text("VERDICT: NEEDS_REWORK\n")
        fresh = self.wait(verifier, review)
        self.assertEqual(fresh.returncode, 0)
        self.assertIn("OUTCOME: FAIL", fresh.stdout)
        self.assertIn("VERDICT: NEEDS_REWORK", fresh.stdout)

    def test_multiple_streams_preserve_earlier_rounds(self) -> None:
        earlier = self.report("verifier-ws1-r1.md", "OUTCOME: PASS\n")
        current = [
            self.report("verifier-ws1-r2.md", "OUTCOME: CANNOT_RUN\n"),
            self.report("review-ws1-r2-code.md", "VERDICT: NEEDS_REWORK\n"),
            self.report("verifier-ws2-r1.md", "OUTCOME: PASS\n"),
            self.report("review-ws2-r1-security.md", "VERDICT: APPROVED\n"),
        ]
        archived = archive_reports(self.run, current)
        self.assertIsNotNone(archived)
        self.assertTrue(earlier.is_file())
        self.assertTrue(all(not p.exists() for p in current))

    def test_repeated_recovery_preserves_both_attempts(self) -> None:
        verifier = self.report("verifier-r1.md", "OUTCOME: PASS\n")
        first = archive_reports(self.run, [verifier])
        self.assertIsNone(archive_reports(self.run, [verifier]))
        verifier.write_text("OUTCOME: CANNOT_RUN\n")
        second = archive_reports(self.run, [verifier])
        self.assertNotEqual(first, second)
        assert first is not None and second is not None
        self.assertEqual((first / verifier.name).read_text(), "OUTCOME: PASS\n")
        self.assertEqual((second / verifier.name).read_text(), "OUTCOME: CANNOT_RUN\n")

    def test_validate_all_paths_before_archiving(self) -> None:
        verifier = self.report("verifier-r1.md", "OUTCOME: PASS\n")
        invalid = self.report("implementer-ws1-r1.md", "status: done\n")
        outside = self.run.parent / "review-r1-code.md"
        outside.write_text("VERDICT: APPROVED\n")
        directory = self.run / "triage-r1.md"
        directory.mkdir()
        for path in (invalid, outside, directory):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    archive_reports(self.run, [verifier, path])
                self.assertTrue(verifier.is_file())

    def test_symlinks_cannot_move_files_outside_run(self) -> None:
        outside = self.run.parent / "outside.md"
        outside.write_text("keep\n")
        report = self.run / "verifier-r1.md"
        report.symlink_to(outside)
        with self.assertRaises(ValueError):
            archive_reports(self.run, [report])
        report.unlink()
        report.write_text("OUTCOME: PASS\n")
        (self.run / "report-history").symlink_to(self.run.parent)
        with self.assertRaises(ValueError):
            archive_reports(self.run, [report])
        self.assertTrue(report.is_file())
        self.assertEqual(outside.read_text(), "keep\n")

    def test_cli_accepts_relative_and_absolute_report_paths(self) -> None:
        verifier = self.report("verifier-r1.md", "OUTCOME: PASS\n")
        review = self.report("review-r1-perf.md", "VERDICT: APPROVED\n")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "archive_reports.py"), str(self.run),
             verifier.name, str(review)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("REPORT_HISTORY=", result.stdout)
        self.assertFalse(verifier.exists())
        self.assertFalse(review.exists())


if __name__ == "__main__":
    unittest.main()
