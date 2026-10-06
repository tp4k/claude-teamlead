#!/usr/bin/env python3
"""Check that review_briefs.py applies step 9's table and writes complete briefs."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from review_briefs import mode, write_briefs

SCRIPTS = Path(__file__).resolve().parent
TAGS = {"input": "no", "hot": "yes", "public": "yes"}


class ReviewBriefTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.rundir = Path(self.temp.name) / "run"
        self.briefs = self.rundir / "briefs"
        self.briefs.mkdir(parents=True)
        (self.rundir / "repo.txt").write_text("/abs/repo\n")
        (self.rundir / "plan.md").write_text(
            "# Plan\n\n## WS-1 — weighted allocate\n\nbody\n")
        (self.rundir / "task.md").write_text("flags:\n")
        (self.briefs / "impl-ws1-r1.md").write_text("brief\n")

    def config(self, security: str, perf: str) -> None:
        (self.rundir / "config.json").write_text(json.dumps(
            {"options": {"securityReview": security, "perfReview": perf}}))

    def test_table(self) -> None:
        self.assertEqual(mode("code", "off", "no"), "full")
        self.assertEqual(mode("security", "on", "no"), "sanity")
        self.assertEqual(mode("security", "when-needed", "no"), "skip")
        self.assertEqual(mode("security", "when-needed", "yes"), "full")
        self.assertEqual(mode("perf", "off", "yes"), "skip")

    def test_round_one_writes_one_brief_per_dispatched_axis(self) -> None:
        self.config("on", "when-needed")
        settled = "1. Idle keys stay — map grows.\n"
        out = write_briefs(self.rundir, 1, 1, TAGS, "abc def", settled)
        self.assertEqual([ln.split()[:2] for ln in out],
                         [["code", "full"], ["security", "sanity"], ["perf", "full"]])
        self.assertIn("model=sonnet", out[1])
        code = (self.briefs / "review-r1-code.md").read_text()
        self.assertIn("Axis: code. Workstream: WS-1 (weighted allocate). Round: 1.",
                      code)
        self.assertIn("$RUN/verifier-r1.md", code)
        self.assertIn("Commits: abc def.", code)
        self.assertIn(settled.strip(), code)
        self.assertIn("Output: $RUN/review-r1-code.md", code)
        self.assertNotIn("Rework:", code)
        security = (self.briefs / "review-r1-security.md").read_text()
        self.assertIn("sanity pass", security)
        self.assertIn(settled.strip(), security)

    def test_skip_names_the_setting_and_tag(self) -> None:
        self.config("when-needed", "off")
        out = write_briefs(self.rundir, 1, 1, TAGS, "abc", "")
        self.assertEqual(out[1],
                         "security skip reason=securityReview=when-needed, input=no")
        self.assertEqual(out[2], "perf skip reason=perfReview=off, hot=yes")
        self.assertFalse((self.briefs / "review-r1-perf.md").exists())
        self.assertIn("none", (self.briefs / "review-r1-code.md").read_text())

    def test_rework_round_drops_carried_axes(self) -> None:
        self.config("on", "on")
        (self.briefs / "impl-ws1-r2.md").write_text("rework\n")
        (self.rundir / "triage-r1.md").write_text(
            "Verdict: NEEDS_REWORK\n\n## Re-review set\ncode: re-run — always\n"
            "security: carried — no finding\nperf: re-run — hot fix\n")
        out = write_briefs(self.rundir, 1, 2, TAGS, "fff", "")
        self.assertEqual(out[1], "security skip reason=carried by triage round 1")
        perf = (self.briefs / "review-r2-perf.md").read_text()
        self.assertIn("previous rows are in $RUN/triage-r1.md. Rework commits: fff.",
                      perf)

    def test_resolved_option_beats_task_flag(self) -> None:
        # The options card turned security back on after --no-security-review.
        (self.rundir / "task.md").write_text(
            "flags: --no-security-review --no-perf-review\n")
        self.config("on", "off")
        out = write_briefs(self.rundir, 1, 1, TAGS, "abc", "")
        self.assertTrue(out[1].startswith("security sanity"))
        self.assertEqual(out[2], "perf skip reason=perfReview=off, hot=yes")

    def test_flag_applies_when_option_missing(self) -> None:
        (self.rundir / "task.md").write_text("flags: --no-perf-review\n")
        (self.rundir / "config.json").write_text("{}")
        out = write_briefs(self.rundir, 1, 1, TAGS, "abc", "")
        self.assertTrue(out[1].startswith("security sanity"))
        self.assertEqual(out[2], "perf skip reason=perfReview=off, hot=yes")

    def test_multi_workstream_uses_infix(self) -> None:
        self.config("off", "off")
        (self.rundir / "plan.md").write_text("## WS-1 — a\n\n## WS-2 — b\n")
        out = write_briefs(self.rundir, 2, 1, TAGS, "abc", "")
        self.assertTrue(out[0].endswith("briefs/review-ws2-r1-code.md"))
        code = (self.briefs / "review-ws2-r1-code.md").read_text()
        self.assertIn("Workstream: WS-2 (b)", code)
        self.assertIn("$RUN/verifier-ws2-r1.md", code)
        self.assertIn("Output: $RUN/review-ws2-r1-code.md", code)

    def test_cli_rejects_missing_tag(self) -> None:
        self.config("on", "on")
        res = subprocess.run(
            [sys.executable, str(SCRIPTS / "review_briefs.py"), str(self.rundir),
             "--ws", "1", "--round", "1", "--tags", "input=no,hot=yes",
             "--commits", "abc"],
            capture_output=True, text=True)
        self.assertEqual(res.returncode, 2)
        self.assertIn("public=yes|no", res.stderr)


if __name__ == "__main__":
    unittest.main()
