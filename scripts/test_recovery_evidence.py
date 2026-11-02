#!/usr/bin/env python3
"""Check the evaluation harness against real Git, tests, and mutation results."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "evals/requirement-provenance/followup/verify_recovery.py"
spec = importlib.util.spec_from_file_location("recovery_evidence", HELPER)
assert spec is not None and spec.loader is not None
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)

SOURCE = "def labels(values):\n    return list(dict.fromkeys(values))\n"
TEST = (
    "import unittest\nfrom labels import labels\n\n"
    "class Labels(unittest.TestCase):\n"
    "    def test_first_seen(self):\n"
    "        self.assertEqual(labels(['b', 'a', 'b']), ['b', 'a'])\n"
)


class RecoveryEvidence(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.git("init", "-q")
        (self.source / "labels.py").write_text(
            "def labels(values):\n    return values\n")
        (self.source / "test_labels.py").write_text(TEST)
        self.git("add", ".")
        self.git("commit", "-qm", "RED")
        self.red = self.git("rev-parse", "HEAD")
        (self.source / "labels.py").write_text(SOURCE)
        self.git("add", ".")
        self.git("commit", "-qm", "Recovery applied by harness")
        self.head = self.git("rev-parse", "HEAD")

    def git(self, *args: str) -> str:
        env = dict(os.environ, GIT_AUTHOR_NAME="Evaluation",
                   GIT_COMMITTER_NAME="Evaluation", GIT_AUTHOR_EMAIL="eval@test",
                   GIT_COMMITTER_EMAIL="eval@test")
        return subprocess.check_output(["git", *args], cwd=self.source,
                                       env=env, text=True).strip()

    def collect(self, replacement: str = "return list(values)", **kwargs) -> dict:
        probe = {"probe": "duplicates removed", "file": "labels.py",
                 "old": "return list(dict.fromkeys(values))", "new": replacement}
        args = dict(source=self.source, out=self.root / "evidence", head=self.head,
                    base=self.red, red=self.red, probes=[probe])
        args.update(kwargs)
        return recovery.collect(**args)

    def test_complete_evidence_with_real_killed_probe(self) -> None:
        result = self.collect()
        self.assertEqual(result["outcome"], "PASS")
        self.assertEqual(result["tree"], "CLEAN")
        self.assertEqual(len(result["snapshots"]), 5)
        self.assertIn("MUTATION: PASS killed=1", result["mutation"]["output"])
        out = self.root / "evidence"
        report = (out / "verifier-r2.md").read_text()
        self.assertIn("tree: CLEAN", report)
        self.assertIn("head: " + self.head, report)
        self.assertIn("Recovery applied by harness", report)
        self.assertIn("FAIL: test_first_seen", report)
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual((self.source / "labels.py").read_text(), SOURCE)

    def test_surviving_probe_does_not_become_pass(self) -> None:
        result = self.collect("return [*dict.fromkeys(values)]")
        self.assertEqual(result["outcome"], "FAIL")
        self.assertIn("SURVIVED", result["mutation"]["output"])
        self.assertEqual(result["tree"], "CLEAN")

    def test_dirty_source_is_refused(self) -> None:
        (self.source / "untracked.txt").write_text("not committed")
        with self.assertRaisesRegex(ValueError, "Source must be clean"):
            self.collect()
        self.assertFalse((self.root / "evidence").exists())

    def test_stale_head_missing_probes_and_unsafe_output_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "Source must be clean"):
            self.collect(head=self.red)
        with self.assertRaisesRegex(ValueError, "Missing probe patches"):
            self.collect(probes=[])
        with self.assertRaisesRegex(ValueError, "outside the source"):
            self.collect(out=self.source / "evidence")


if __name__ == "__main__":
    unittest.main()
