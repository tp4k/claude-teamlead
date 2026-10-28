#!/usr/bin/env python3
"""Exercise routing, decision propagation, metrics and manifest regressions."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import current_brief
import mutate
import review_briefs
import run_config
import run_metrics
import workflow_profile
from test_next import World, git


class Outcomes(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def eligible(self) -> World:
        w = World(self.root / "world", workflowProfile="adaptive")
        config = json.loads(w.read("config.json"))
        config["scopeFence"] = True
        w.put("config.json", json.dumps(config))
        w.put("questions.md", w.read("questions.md").replace(
            "public: yes", "public: no"))
        w.put("briefs/impl-ws1-r1.md", w.read("briefs/impl-ws1-r1.md")
              + "\n## Scope\n```scope\napp.py\n```\n")
        self.assess(w)
        return w

    def assess(self, w: World) -> None:
        w.put("workflow-assessment.json", json.dumps({
            "fingerprint": workflow_profile.fingerprint(w.run), "bounded": True,
            "risks": dict.fromkeys(workflow_profile.RISKS, False),
            "evidence": dict.fromkeys(workflow_profile.EVIDENCE,
                                      "app.py:1; local check"),
        }))

    def test_flag_opt_in_and_default(self) -> None:
        flags, _ = run_config.parse_flags("fix typo --workflow-profile=adaptive")
        self.assertEqual(flags["workflowProfile"], "adaptive")
        with self.assertRaises(run_config.Fail):
            run_config.parse_flags("--workflow-profile=fast")
        w = World(self.root / "default")
        self.assertEqual(workflow_profile.selection(w.run)[0], "standard")

    def test_adaptive_keeps_verification_and_final_gate(self) -> None:
        w = self.eligible()
        self.assertEqual(workflow_profile.selection(w.run)[0], "adaptive")
        first = w.step()
        self.assertIn("baseline-ws1.md", first.out)
        w.put("baseline-ws1.md", "OUTCOME: PASS\n")
        self.assertEqual(w.step().kinds(), ["teamlead:implementer"])
        sha = w.commit("implement")
        w.report(1, 1, [sha])
        self.assertEqual(w.step().kinds(), ["teamlead:verifier"])
        w.verifier(1, 1)
        w.put("verifier-r1.md", f"head: {sha}\n" + w.read("verifier-r1.md"))
        w.mutation(1, 1)
        gate = w.step()
        self.assertIn("--final-gate", gate.out)
        self.assertNotIn("review-r1-code", gate.out)
        self.assertNotIn("final-report.md", gate.out)
        w.codex_review(1)
        self.assertEqual(w.step().kinds(), ["teamlead:triage"])
        decision = {"id": "final-cleanup", "revision": 1, "action": "defer",
                    "reason": "optional cleanup", "evidence": "caller checks pass"}
        w.gate_triage(1, "APPROVED_WITH_NOTES", "```decision-records\n"
                      + json.dumps([decision]) + "\n```\n")
        self.assertIn("final-report.md", w.step().out)
        self.assertIn("final-cleanup r1: defer", w.read("current-decisions.md"))
        phases = run_metrics.read(w.run)["phases"]
        self.assertTrue(any(p["durationSeconds"] is not None for p in phases.values()))
        self.assertTrue(all(p["tokens"]["cached"] is None for p in phases.values()))

    def test_risks_staleness_explicit_reviews_and_rework_keep_standard(self) -> None:
        w = self.eligible()
        original = w.read("workflow-assessment.json")
        for risk in workflow_profile.RISKS:
            assessment = json.loads(original)
            assessment["risks"][risk] = True
            w.put("workflow-assessment.json", json.dumps(assessment))
            self.assertEqual(workflow_profile.selection(w.run)[0], "standard", risk)
        w.put("workflow-assessment.json", original)
        w.put("plan.md", w.read("plan.md") + "new behavior\n")
        self.assertEqual(workflow_profile.selection(w.run)[0], "standard")
        self.assess(w)
        config = json.loads(w.read("config.json"))
        config["options"]["securityReview"] = "on"
        w.put("config.json", json.dumps(config))
        self.assertEqual(workflow_profile.selection(w.run)[0], "standard")
        config["options"]["securityReview"] = "off"
        config["options"]["codexCodeReview"] = "off"
        w.put("config.json", json.dumps(config))
        self.assertEqual(workflow_profile.selection(w.run)[0], "standard")
        config["options"]["codexCodeReview"] = "on"
        w.put("config.json", json.dumps(config))
        w.rework_brief(1, 2)
        self.assertEqual(workflow_profile.selection(w.run)[0], "standard")

    def test_missing_mutation_and_stale_verifier_cannot_skip_to_gate(self) -> None:
        w = self.eligible()
        w.pin_base()
        sha = w.commit("implement")
        w.report(1, 1, [sha])
        w.verifier(1, 1)
        halted = w.step()
        self.assertEqual(halted.code, 1)
        self.assertNotIn("--final-gate", halted.out)
        w.mutation(1, 1)
        w.put("verifier-r1.md", f"head: {sha}\nOUTCOME: PASS\n")
        w.commit("later change")
        w.put("briefs/review-r1-code.md", "Previously dispatched review.\n")
        self.assertEqual(w.step().kinds(), ["teamlead:verifier"])

    def test_shared_database_baselines_serialize(self) -> None:
        w = World(self.root / "db", streams=2)
        for ws in (1, 2):
            name = f"briefs/impl-ws{ws}-r1.md"
            w.put(name, w.read(name) + "\nverification resource: shared-database\n")
        first = w.step()
        self.assertEqual(len(first.spawns()), 1)
        self.assertIn("baseline-ws1.md", first.out)
        w.put("baseline-ws1.md", "OUTCOME: PASS\n")
        second = w.step()
        self.assertEqual(len(second.spawns()), 1)
        self.assertIn("baseline-ws2.md", second.out)
        self.assertNotIn("teamlead:implementer", second.out)

    def test_current_brief_keeps_latest_scope_and_prior_decisions(self) -> None:
        w = World(self.root / "brief")
        w.put("briefs/impl-ws1-r1.md", "## Scope\n```scope\nold.py\n```\n"
              "## Spec\nCaller must keep working.\n"
              "## Verification commands\n- `check`\n")
        w.put("briefs/impl-ws1-r2.md", "## Scope\n```scope\nold.py\nnew.py\n```\n"
              "## Findings to fix\nFix F1 only.\n")
        record = {"id": "F2", "revision": 1, "action": "defer",
                  "reason": "optional cleanup", "evidence": "owner scope decision"}
        w.put("triage-r1.md", "```decision-records\n"
              + json.dumps([record]) + "\n```\n")
        w.put("triage-r2.md", "VERDICT: APPROVED\n")
        view = current_brief.write(w.run, 1, 2).read_text()
        self.assertIn("old.py\nnew.py", view)
        self.assertEqual(view.count("```scope"), 1)
        self.assertIn("Caller must keep working.", view)
        self.assertIn("F2 r1: defer", view)
        archived = w.run / "report-history" / "retry" / "triage-r1.md"
        archived.parent.mkdir(parents=True)
        (w.run / "triage-r1.md").rename(archived)
        self.assertIn("F2 r1: defer", current_brief.decision_text(w.run))
        briefs = review_briefs.write_briefs(w.run, 1, 2,
                                           dict(input="no", hot="no", public="no"),
                                           w.base, current_brief.decision_text(w.run))
        self.assertTrue(briefs)
        review = w.read("briefs/review-r2-code.md")
        self.assertIn("F2 r1: defer", review)
        record.update(revision=2, action="fix",
                      reason="new caller reproduction")
        w.put("triage-gate-r1.md", "```decision-records\n"
              + json.dumps([record]) + "\n```\n")
        self.assertEqual(current_brief.decisions(w.run)[0]["action"], "fix")
        # Same revision with a different action is an error, not a silent overwrite.
        record["action"] = "decline"
        w.put("triage-r3.md", "```decision-records\n"
              + json.dumps([record]) + "\n```\n")
        with self.assertRaises(ValueError):
            current_brief.write(w.run, 1, 2)

    def test_final_review_package_receives_declines(self) -> None:
        w = World(self.root / "package")
        w.commit("change")
        record = {"id": "cleanup", "revision": 1, "action": "decline",
                  "reason": "owner excluded it", "evidence": "task scope"}
        w.put("plan.md", w.read("plan.md") + "\n```decision-records\n"
              + json.dumps([record]) + "\n```\n")
        package = self.root / "review-package"
        result = subprocess.run([sys.executable, str(Path(__file__).with_name(
            "review_package.py")), str(w.run), "--base", w.base, "--out", str(package),
            "--final-gate"], env=w.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("cleanup r1: decline",
                      (package / "current-decisions.md").read_text())
        self.assertIn("current-decisions.md", (package / "PROMPT.md").read_text())

    def test_current_brief_keeps_fenced_spec_and_constraints(self) -> None:
        w = World(self.root / "quoted")
        spec = "```markdown\n## Contract\nKeep the original caller behavior.\n```\n"
        w.put("briefs/impl-ws1-r1.md", "## Spec\n" + spec
              + "\n## Scope\n```scope\napp.py\n```\n"
              "\n## Verification commands\n- `python3 verify.py`\n")
        w.put("briefs/impl-ws1-r2.md", "## Findings to fix\nRepair one bug.\n"
              "## Scope\nSame scope as before.\n## Verification commands\nInherited.\n")
        view = current_brief.write(w.run, 1, 2).read_text()
        self.assertIn(spec, view)
        self.assertIn("```scope\napp.py\n```", view)
        self.assertIn("- `python3 verify.py`", view)
        self.assertEqual(view.count("```"), 4)

    def test_measurements_distinguish_missing_zero_and_confirmed(self) -> None:
        run = self.root / "run"
        run.mkdir()
        run_metrics.start(run, "verify", now=10)
        run_metrics.start(run, "verify", now=20)  # retry preserves initial time
        run_metrics.finish(run, "verify", now=25)
        run_metrics.finish(run, "verify", now=30)
        self.assertEqual(run_metrics.totals(run)["seconds"], 15)
        self.assertIsNone(run_metrics.totals(run)["cached"])
        run_metrics.usage(run, "verify", {"cached": 0, "uncached": 20, "output": 5},
                          "provider response")
        run_metrics.event(run, "rework", "ws1-r2", "weak test", "verifier-r1.md")
        run_metrics.event(run, "rework", "ws1-r2", "weak test", "verifier-r1.md")
        self.assertEqual(run_metrics.totals(run)["rework"], 1)
        self.assertIsNone(run_metrics.totals(run)["confirmedFindings"])
        data = run_metrics.read(run)
        data["outcomeObservation"] = "post-run review inspected on day 7"
        run_metrics.save(run, data)
        self.assertEqual(run_metrics.totals(run)["confirmedFindings"], 0)
        run_metrics.event(run, "confirmed-pr-finding", "F1", "incomplete fix",
                          "reproduction")
        self.assertEqual(run_metrics.totals(run)["confirmedFindings"], 1)
        comparison = run_metrics.compare([(run, self.root / "missing"), (run, run)])
        self.assertEqual(comparison["metrics"]["cached"]["availablePairs"], 1)
        self.assertEqual(comparison["metrics"]["cached"]["medianCandidate"], 0)

    def test_codex_usage_records_available_fields_without_guessing(self) -> None:
        run = self.root / "usage"
        run.mkdir()
        run_metrics.start(run, "gate", now=1)
        events = run / "gate-r1.jsonl"
        events.write_text(json.dumps({"type": "turn.completed", "usage": {
            "input_tokens": 100, "cached_input_tokens": 60, "output_tokens": 5,
        }}) + "\n")
        run_metrics.codex_usage(run, "gate", [events])
        tokens = run_metrics.read(run)["phases"]["gate"]["tokens"]
        self.assertEqual(tokens, {"cached": 60, "uncached": 40, "output": 5})
        events.write_text(json.dumps({"type": "turn.completed", "usage": {
            "input_tokens": 100, "output_tokens": 7,
        }}) + "\n")
        run_metrics.codex_usage(run, "gate", [events])
        tokens = run_metrics.read(run)["phases"]["gate"]["tokens"]
        self.assertEqual(tokens, {"cached": None, "uncached": None, "output": 7})

    def test_manifest_script_names_and_close_open_lines_stay_mutable(self) -> None:
        w = World(self.root / "manifest")
        manifest = '''{
  "dependencies": {
    "example": "2"
  }, "scripts": {
    "dependencies": "node check.js",
    "engines": "node engine.js"
  },
  "pnpm": {"overrides": {"other": "3"}}
}
'''
        (w.repo / "package.json").write_text(manifest)
        git(w.repo, "add", "package.json")
        git(w.repo, "commit", "-qm", "manifest")
        candidates = mutate.generic_mutants(str(w.repo),
                                             {"package.json": set(range(1, 10))}, 100)
        lines = {m.line for m in candidates}
        self.assertTrue({5, 6} <= lines)
        self.assertNotIn(3, lines)
        # A mixed dependency/script line cannot safely be exempted wholesale.
        compact = ('{"dependencies":{"x":"2"},'
                   '"scripts":{"test":"run"}}')
        self.assertEqual(mutate.manifest_data_lines(compact), set())
        self.assertEqual(mutate.manifest_data_lines('{"dependencies":'), set())


if __name__ == "__main__":
    unittest.main()
