#!/usr/bin/env python3
"""Regression suite for hooks/gate-agent-spawns.py.

    python3 scripts/test_gate_agent_spawns.py

The failure this pins is a real run, `nsd-m0c-grammar/2026-09-24-1018-m0c-grammar`:
task.md with `flags: none`, a `complex=yes` plan, a PLAN_VALID validation and
four implementer briefs — and no config.json, no options card, no plan review
package. Every implementer spawn was allowed, because nothing looked. The first
case is that file set, replayed; the rest pin the two directions a gate can be
wrong in: a correct run must pass, and a spawn this hook cannot vouch for (a
stranger's agent, a prompt without `$RUN =`, a broken run dir) gets silence.

Each case pipes a PreToolUse event into the hook as the harness would, and reads
the decision from stdout — so the JSON protocol is under test too.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "gate-agent-spawns.py"

TASK = "Build the M0c grammar.\n\nflags: none\n"
QUESTIONS = ("1. Keep the old parser? Recommend no.\n\n## Routing\n"
             "PLAN_WRITTEN ws=4 complex=yes questions=2 decisions=15 "
             "adr_conflict=no\n")
ANSWERED = QUESTIONS + "\n## Answers\n1. recommendation accepted\n"
PLAN = "# Plan — M0c grammar\n\n## WS-1 — lexer\n"
VALID = "# Plan validation\n\nVerdict: PLAN_VALID\n\nSmaller: none\n"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def config(autopilot: bool = False, **options: str) -> str:
    opts = {"codexPlanReview": "hard", "opusPlanReview": "fallback",
            "humanReadablePlan": "off", "securityReview": "on",
            "perfReview": "on", "codexCodeReview": "off", "adr": "off"}
    opts.update(options)
    return json.dumps({"options": opts, "sources": {k: "default" for k in opts},
                       "autopilot": autopilot, "optionsCard": "shown"})


def mkrun(tmp: Path, files: dict[str, str]) -> Path:
    run = tmp / "runs" / "nsd-m0c-grammar" / "2026-09-24-1018-m0c-grammar"
    run.mkdir(parents=True)
    (run / "repo.txt").write_text(f"{tmp / 'repo'}\n")
    for name, body in files.items():
        (run / name).parent.mkdir(parents=True, exist_ok=True)
        (run / name).write_text(body)
    return run


M0C = {"task.md": TASK, "plan.md": PLAN, "questions.md": ANSWERED,
       "plan-validation.md": VALID, "briefs/impl-ws1-r1.md": "# Brief\n"}
REVIEWED = dict(M0C, **{
    "config.json": config(),
    "plan-review-package/PROMPT.md": "review this plan\n",
    "plan-review-package/plan-review-r1.md": "| # | finding |\n",
    "plan-triage.md": "| # | verdict |\n",
})


def spawn(role: str, run: Path | str, tool: str = "Agent",
          tail: str = ". Read your brief.") -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": tool,
            "tool_input": {"subagent_type": role, "description": "x",
                           "prompt": f"$RUN = {run}{tail}"}}


def run_hook(event: object) -> tuple[int, str | None]:
    """(exit code, deny reason or None) for one event."""
    raw = event if isinstance(event, str) else json.dumps(event)
    # cycle_gap scans $TEAMLEAD_HOME/tasks; keep it off the real ~/.teamlead.
    with tempfile.TemporaryDirectory() as home:
        env = dict(os.environ, TEAMLEAD_HOME=home)
        r = subprocess.run([sys.executable, str(HOOK)], input=raw, env=env,
                           capture_output=True, text=True, check=False)
    if not r.stdout.strip():
        return r.returncode, None
    out = json.loads(r.stdout)["hookSpecificOutput"]
    return r.returncode, (out["permissionDecisionReason"]
                          if out["permissionDecision"] == "deny" else None)


def expect_deny(name: str, event: object, *needles: str) -> None:
    code, reason = run_hook(event)
    ok = code == 0 and reason is not None and all(n in reason for n in needles)
    check(name, ok, f"exit={code} reason={reason!r}")


def expect_silent(name: str, event: object) -> None:
    code, reason = run_hook(event)
    check(name, code == 0 and reason is None, f"exit={code} reason={reason!r}")


def case_m0c_replay_denied(tmp: Path) -> None:
    run = mkrun(tmp, M0C)
    expect_deny("m0c replay: implementer with no config.json is refused at 3a",
                spawn("teamlead:implementer", run), "step 3a", "run_config.py",
                "run_state.py")


def case_m0c_planner_denied(tmp: Path) -> None:
    run = mkrun(tmp, {"task.md": TASK})
    expect_deny("a planner before step 3a is refused", spawn("teamlead:planner", run),
                "step 3a")


def case_codex_owed_before_validation(tmp: Path) -> None:
    run = mkrun(tmp, {k: v for k, v in M0C.items() if k != "plan-validation.md"}
                | {"config.json": config()})
    expect_deny("hard + complex=yes: validator refused until the Codex review "
                "started", spawn("teamlead:plan-validator", run),
                "plan_review_package.py")


def case_codex_owed_before_dispatch(tmp: Path) -> None:
    run = mkrun(tmp, dict(M0C, **{"config.json": config()}))
    expect_deny("hard + complex=yes: implementer refused until the Codex review "
                "started", spawn("teamlead:implementer", run), "step 4",
                "plan_review_package.py")


def case_reviewed_run_allowed(tmp: Path) -> None:
    run = mkrun(tmp, REVIEWED)
    expect_silent("a run that did 3a, 4a, 5 and 6 may dispatch",
                  spawn("teamlead:implementer", run))


def case_codex_failure_allowed(tmp: Path) -> None:
    files = {k: v for k, v in REVIEWED.items()
             if k not in ("plan-review-package/plan-review-r1.md", "plan-triage.md")}
    run = mkrun(tmp, files | {"config.json": config(opusPlanReview="off")})
    expect_silent("a Codex review that started and failed never blocks dispatch",
                  spawn("teamlead:implementer", run))


def case_relay_owed(tmp: Path) -> None:
    run = mkrun(tmp, dict(REVIEWED, **{"questions.md": QUESTIONS}))
    expect_deny("no ## Answers: implementer refused at the relay turn",
                spawn("teamlead:implementer", run), "step 6")


def case_autopilot_skips_relay(tmp: Path) -> None:
    run = mkrun(tmp, dict(REVIEWED, **{"questions.md": QUESTIONS,
                                       "config.json": config(autopilot=True)}))
    expect_silent("autopilot skips only the relay turn",
                  spawn("teamlead:implementer", run))


def case_planner_after_3a_allowed(tmp: Path) -> None:
    run = mkrun(tmp, {"task.md": TASK, "config.json": config()})
    expect_silent("a planner after step 3a is allowed", spawn("teamlead:planner", run))


def case_other_plugin_prefix(tmp: Path) -> None:
    run = mkrun(tmp, M0C)
    expect_deny("the plugin prefix is not assumed", spawn("my-teamlead:implementer",
                                                          run), "step 3a")


def case_task_tool_name(tmp: Path) -> None:
    run = mkrun(tmp, M0C)
    expect_deny("the older `Task` tool name is gated too",
                spawn("teamlead:implementer", run, tool="Task"), "step 3a")


def case_ungated_roles_silent(tmp: Path) -> None:
    run = mkrun(tmp, M0C)
    for role in ("teamlead:verifier", "teamlead:writer", "teamlead:plan-reviewer",
                 "implementer", "general-purpose", "code-review"):
        expect_silent(f"{role} is never gated", spawn(role, run))


def case_unresolvable_run_silent(tmp: Path) -> None:
    expect_silent("a $RUN with no repo.txt gets silence",
                  spawn("teamlead:implementer", tmp / "nowhere"))
    expect_silent("a relative $RUN gets silence",
                  spawn("teamlead:implementer", "runs/x"))
    event = spawn("teamlead:implementer", tmp)
    event["tool_input"]["prompt"] = "Implement WS-1 from the brief."
    expect_silent("a prompt without `$RUN =` gets silence", event)


def case_trailing_punctuation(tmp: Path) -> None:
    run = mkrun(tmp, M0C)
    expect_deny("`$RUN = <path>.` with the brief's full stop still resolves",
                spawn("teamlead:implementer", run, tail=".\nRead brief I."), "3a")


def case_garbage_silent(_tmp: Path) -> None:
    expect_silent("non-JSON stdin gets silence, exit 0", "{not json")
    expect_silent("a non-spawn tool gets silence",
                  {"tool_name": "Bash", "tool_input": {"command": "ls"}})
    expect_silent("a tool_input that is not an object gets silence",
                  {"tool_name": "Agent", "tool_input": "x"})


def main() -> int:
    cases = [v for k, v in globals().items() if k.startswith("case_")]
    for case in cases:
        with tempfile.TemporaryDirectory() as d:
            case(Path(d))
    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            print(f"      {detail}")
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
