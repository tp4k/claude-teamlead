#!/usr/bin/env python3
"""Regression suite for run_state.py:  python3 scripts/test_run_state.py

The script's whole claim is that the file set determines the step, so the cases
here are file sets — each one a point in the loop a resumed coordinator can
actually land on, plus the traps that make the mapping non-obvious:

  * the verifier, review and triage files carry a `ws<N>-` segment only when the
    run has more than one workstream, so both spellings have to resolve;
  * which reviewers are *expected* comes from `task.md`'s `flags:` line — with
    `--no-security-review` a missing security review is not an outstanding one;
  * the routing token has to survive its own line's tail (`VERDICT: APPROVED
    rows=3 demoted=1 …`) and the plan-validator's new scope selection, whose
    `Recommend:`/`Smaller:` lines sit *below* the real verdict;
  * an absent file means "spawn it again", not "wait" — a subagent does not
    outlive the session, which is the reason this script exists at all.

No pytest dependency — the skill's scripts run with bare python3, and a suite
that needs an install is a suite nobody runs.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

RUN_STATE = Path(__file__).resolve().parent / "run_state.py"

TASK = "Apply stacked coupons in a fixed order.\n\nflags: none\n"
PLAN = """# Plan — coupon application

## WS-1 — resolve order
reuse: pricing.discount.apply_percent
keep because: the spec's Acceptance section names this deliverable

PLAN_WRITTEN ws=1 complex=no questions=2 decisions=1 adr_conflict=no
"""
PLAN_2WS = PLAN.replace("## WS-1 — resolve order",
                        "## WS-1 — resolve order\n\n## WS-2 — serialise output")
QUESTIONS = "1. Round half-up? Recommend yes.\n\n## Routing\nPLAN_WRITTEN ws=1\n"
ANSWERED = QUESTIONS + "\n## Answers\n1. recommendation accepted\n"
VALID = ("# Plan validation\n\nVerdict: PLAN_VALID\n\n## Smaller / none\n\n"
         "Smaller: none\n")
NEEDS_FIX = ("# Plan validation\n\n"
             "Verdict: PLAN_NEEDS_FIX blockers=1 majors=0 minors=0\n")
DONE_REPORT = ("# Implementer report — WS-1 — round 1\n\n## Summary\nAdded it.\n\n"
               "```\nstatus: done\nconfidence: high — did not exercise the CLI\n"
               "commits: a1b2c3d\n```\n")
BRIEF = "# Brief — WS-1 r1\n\n## Reuse and scope\nreuse: apply_percent\n"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def mkrun(tmp: Path, files: dict[str, str]) -> Path:
    run = tmp / "2026-09-04-1200-coupons"
    (run / "briefs").mkdir(parents=True)
    (run / "repo.txt").write_text("/repo/pricing\n")
    for name, body in files.items():
        p = run / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return run


def state(run: Path, home: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run run_state.py against `run`, with $TEAMLEAD_HOME pointed somewhere empty.

    Hermetic by default and deliberately so: `rework_cap` consults the global
    config, so without the override a real `~/.teamlead/config.json` on whoever's
    machine runs this would silently change what the cap cases assert. Pass
    `home` to exercise that tier on purpose.
    """
    env = dict(os.environ, TEAMLEAD_HOME=str(home or run.parent / "empty-home"))
    argv = [sys.executable, str(RUN_STATE), str(run)]
    return subprocess.run(argv, capture_output=True, text=True, check=False, env=env)


def expect(name: str, run: Path, step: str, needle: str, code: int,
           home: Path | None = None) -> None:
    r = state(run, home)
    ok = (r.returncode == code and f"step: {step}" in r.stdout
          and needle in r.stdout)
    check(name, ok, f"exit={r.returncode} (want {code})\n      out={r.stdout.strip()!r}"
                    f"\n      err={r.stderr.strip()[:300]!r}")


def case_not_a_run_directory(tmp: Path) -> None:
    """Guard first: pointed at the wrong path, say so rather than inventing a step."""
    r = state(tmp)
    ok = r.returncode == 2 and "not a run directory" in r.stdout
    check("a directory with no repo.txt exits 2", ok,
          f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_kickoff_without_task(tmp: Path) -> None:
    expect("bare run dir → step 3, write task.md", mkrun(tmp, {}),
           "3", "task.md", 0)


def case_plan_without_questions(tmp: Path) -> None:
    """questions.md is written LAST, so plan.md alone means the planner is unfinished
    — and on resume the planner is also gone, so the action is to spawn it again."""
    run = mkrun(tmp, {"task.md": TASK, "plan.md": PLAN})
    expect("plan.md but no questions.md → step 4, respawn the planner", run,
           "4", "PLANNER", 0)


def case_questions_without_validation(tmp: Path) -> None:
    run = mkrun(tmp, {"task.md": TASK, "plan.md": PLAN, "questions.md": QUESTIONS})
    expect("plan complete, unvalidated → step 4, spawn the validator", run,
           "4", "VALIDATOR", 0)


def case_needs_fix_without_fix_log(tmp: Path) -> None:
    run = mkrun(tmp, {"task.md": TASK, "plan.md": PLAN, "questions.md": QUESTIONS,
                      "plan-validation.md": NEEDS_FIX})
    expect("PLAN_NEEDS_FIX and no Fix log → step 5, Fix mode", run,
           "5", "Fix mode", 0)


def case_fix_log_present_moves_on(tmp: Path) -> None:
    """A `## Fix log` in plan.md is what distinguishes "needs fixing" from "was
    fixed"; without it the resume would loop on a fix that already happened."""
    run = mkrun(tmp, {"task.md": TASK, "plan.md": PLAN + "\n## Fix log\nclaim → fix\n",
                      "questions.md": QUESTIONS, "plan-validation.md": NEEDS_FIX})
    expect("PLAN_NEEDS_FIX with a Fix log → step 6, the relay", run,
           "6", "relay", 1)


SCOPE_CUT = ("# Plan validation\n\nVerdict: PLAN_VALID\n\n## Smaller / none\n\n"
             "WS-2 exists for symmetry; nothing imports it today.\n\n"
             "A) ship as planned — 2 streams, 6 agents\n"
             "B) fold WS-2 into WS-1 — drops the separate CLI flag — one Fix round\n\n"
             "Recommend: B — same file, sole consumer, already serialised\n\n"
             "Smaller: fold WS-2 into WS-1\n")


def case_scope_cut_leads_the_relay(tmp: Path) -> None:
    """A named cut has to arrive in the relay as something to answer. The paired
    `Smaller: none` case below is what makes this row mean anything: identical
    files, one word apart, and the relay text has to differ."""
    run = mkrun(tmp, {"task.md": TASK, "plan.md": PLAN, "questions.md": QUESTIONS,
                      "plan-validation.md": SCOPE_CUT})
    expect("a `Smaller:` cut leads the relay, named", run,
           "6", "scope selection (fold WS-2 into WS-1) FIRST", 1)


def case_smaller_none_is_not_a_decision(tmp: Path) -> None:
    """`none — already minimal` is the common answer. Turning it into a choice
    would make every run ask the user a question with one real option."""
    pv = SCOPE_CUT.replace("Smaller: fold WS-2 into WS-1",
                           "Smaller: none — already minimal, both streams are named")
    run = mkrun(tmp, {"task.md": TASK, "plan.md": PLAN, "questions.md": QUESTIONS,
                      "plan-validation.md": pv})
    r = state(run)
    ok = (r.returncode == 1 and "step: 6" in r.stdout
          and "scope selection" not in r.stdout)
    check("`Smaller: none` adds nothing to the relay", ok,
          f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_accepted_cut_that_was_never_applied(tmp: Path) -> None:
    """The failure the whole selection exists to prevent, one step later: the user
    said B, the session died, and the plan still has two streams. Fix mode logs
    `scope: chose …` into plan.md, so its absence is the evidence."""
    answered = ANSWERED + "scope: B — fold WS-2 into WS-1\n"
    run = mkrun(tmp, {"task.md": TASK, "plan.md": PLAN_2WS, "questions.md": answered,
                      "plan-validation.md": SCOPE_CUT,
                      "briefs/impl-ws1-r1.md": BRIEF, "briefs/impl-ws2-r1.md": BRIEF})
    expect("an accepted cut with no Fix-log entry routes to Fix mode, not dispatch",
           run, "6", "Scope decision: B — fold WS-2 into WS-1", 0)


def case_applied_cut_dispatches(tmp: Path) -> None:
    """The discriminating half: once the Fix log records the choice, the same
    answered questions must dispatch instead of re-fixing forever."""
    answered = ANSWERED + "scope: B — fold WS-2 into WS-1\n"
    plan = PLAN + "\n## Fix log\nscope: chose B → folded WS-2 into WS-1\n"
    run = mkrun(tmp, {"task.md": TASK, "plan.md": plan, "questions.md": answered,
                      "plan-validation.md": SCOPE_CUT, "briefs/impl-ws1-r1.md": BRIEF})
    expect("a logged cut dispatches the surviving stream", run,
           "7", "FRESH sonnet implementer", 0)


def case_ship_as_planned_dispatches(tmp: Path) -> None:
    """Answering A is a real answer and must not be mistaken for an unapplied cut
    — there is nothing to apply, so no Fix round and no `scope: chose` line."""
    answered = ANSWERED + "scope: A — ship as planned\n"
    run = mkrun(tmp, {"task.md": TASK, "plan.md": PLAN, "questions.md": answered,
                      "plan-validation.md": SCOPE_CUT, "briefs/impl-ws1-r1.md": BRIEF})
    expect("choosing A dispatches without a Fix round", run,
           "7", "FRESH sonnet implementer", 0)


def case_no_open_questions_needs_no_answers_section(tmp: Path) -> None:
    """Taken from real runs: 3 of 10 have no `## Answers` at all, every one of them a
    `No open questions.` plan. Step 6 sends the go line and continues in the same
    turn, so there is nothing to append — and reading that as "the user has not
    replied" parks the resume on a decision point that never existed."""
    run = mkrun(tmp, {"task.md": TASK, "plan.md": PLAN,
                      "questions.md": "# Open questions\n\nNo open questions.\n",
                      "plan-validation.md": VALID, "briefs/impl-ws1-r1.md": BRIEF})
    expect("`No open questions.` and no ## Answers still dispatches", run,
           "7", "FRESH sonnet implementer", 0)


def case_a_cut_holds_even_with_no_questions(tmp: Path) -> None:
    """The discriminating half: the shortcut above must key on there being nothing
    to decide, not on the questions list alone. A named cut is something to decide."""
    run = mkrun(tmp, {"task.md": TASK, "plan.md": PLAN,
                      "questions.md": "# Open questions\n\nNo open questions.\n",
                      "plan-validation.md": SCOPE_CUT, "briefs/impl-ws1-r1.md": BRIEF})
    expect("a scope cut still blocks a run with no questions", run,
           "6", "scope selection (fold WS-2 into WS-1) FIRST", 1)


def case_answers_then_no_report(tmp: Path) -> None:
    run = mkrun(tmp, {"task.md": TASK, "plan.md": PLAN, "questions.md": ANSWERED,
                      "plan-validation.md": VALID, "briefs/impl-ws1-r1.md": BRIEF})
    expect("answers in, brief written, no report → step 7, fresh implementer", run,
           "7", "FRESH sonnet implementer", 0)


def case_blocked_implementer_needs_the_user(tmp: Path) -> None:
    blocked = ("# Report\n\n```\nstatus: blocked\nconfidence: low — nothing ran\n"
               "question: which rounding mode?\n```\n")
    run = mkrun(tmp, {"task.md": TASK, "plan.md": PLAN, "questions.md": ANSWERED,
                      "plan-validation.md": VALID, "briefs/impl-ws1-r1.md": BRIEF,
                      "implementer-ws1-r1.md": blocked})
    expect("a blocked implementer exits 1 — its question is not the coordinator's",
           run, "8", "implementer blocked", 1)


def case_done_then_verifier(tmp: Path) -> None:
    run = mkrun(tmp, {"task.md": TASK, "plan.md": PLAN, "questions.md": ANSWERED,
                      "plan-validation.md": VALID, "briefs/impl-ws1-r1.md": BRIEF,
                      "implementer-ws1-r1.md": DONE_REPORT})
    expect("status: done and no verifier → step 8, spawn the verifier", run,
           "8", "VERIFIER", 0)


def case_cannot_run_needs_the_user(tmp: Path) -> None:
    """CANNOT_RUN is an environment fault. Sending it to an implementer as "your
    tests failed" is the specific mistake SKILL.md step 8a names, so it exits 1."""
    run = mkrun(tmp, {"task.md": TASK, "plan.md": PLAN, "questions.md": ANSWERED,
                      "plan-validation.md": VALID, "briefs/impl-ws1-r1.md": BRIEF,
                      "implementer-ws1-r1.md": DONE_REPORT,
                      "verifier-r1.md": "OUTCOME: CANNOT_RUN\n\npytest: not found\n"})
    expect("CANNOT_RUN exits 1 and is not called a code failure", run,
           "8", "not a code failure", 1)


def case_missing_reviewer_is_named(tmp: Path) -> None:
    run = mkrun(tmp, {"task.md": TASK, "plan.md": PLAN, "questions.md": ANSWERED,
                      "plan-validation.md": VALID, "briefs/impl-ws1-r1.md": BRIEF,
                      "implementer-ws1-r1.md": DONE_REPORT,
                      "verifier-r1.md": "OUTCOME: PASS\n\npytest -q → exit 0\n",
                      "review-r1-code.md": "VERDICT: APPROVE\n"})
    r = state(run)
    ok = (r.returncode == 0 and "step: 9" in r.stdout
          and "security" in r.stdout and "perf" in r.stdout)
    check("outstanding reviewers are named, not just counted", ok,
          f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_flags_remove_a_reviewer_from_the_expected_set(tmp: Path) -> None:
    """The discriminating half of the previous case: with the flag set, the same
    file set is *complete*, so the next action is triage rather than a respawn."""
    flags = "Apply stacked coupons.\n\nflags: --no-security-review, --no-perf-review\n"
    run = mkrun(tmp, {"task.md": flags, "plan.md": PLAN, "questions.md": ANSWERED,
                      "plan-validation.md": VALID, "briefs/impl-ws1-r1.md": BRIEF,
                      "implementer-ws1-r1.md": DONE_REPORT,
                      "verifier-r1.md": "OUTCOME: PASS\n\npytest -q → exit 0\n",
                      "review-r1-code.md": "VERDICT: APPROVE\n"})
    r = state(run)
    ok = (r.returncode == 0 and "step: 10" in r.stdout
          and "triage" in r.stdout and "security" not in r.stdout)
    check("--no-security-review makes a missing security review not outstanding",
          ok, f"exit={r.returncode} out={r.stdout.strip()!r}")


def approved_run(tmp: Path, tri: str) -> Path:
    return mkrun(tmp, {"task.md": TASK, "plan.md": PLAN, "questions.md": ANSWERED,
                       "plan-validation.md": VALID, "briefs/impl-ws1-r1.md": BRIEF,
                       "implementer-ws1-r1.md": DONE_REPORT,
                       "verifier-r1.md": "OUTCOME: PASS\n\npytest -q → exit 0\n",
                       "review-r1-code.md": "VERDICT: APPROVE\n",
                       "review-r1-security.md": "VERDICT: APPROVE\n",
                       "review-r1-perf.md": "VERDICT: APPROVE\n",
                       "triage-r1.md": tri})


def case_approved_reaches_the_ledger(tmp: Path) -> None:
    """`VERDICT: APPROVED rows=3 demoted=1 …` — the token has to survive its own
    tail. Asserted on the printed stream line ending exactly at `APPROVED`, because
    the *routing* decision here would come out the same either way: anything that
    is neither NEEDS_REWORK nor STOP falls through to approved."""
    run = approved_run(tmp, "# Triage\n\nVERDICT: APPROVED rows=3 demoted=1 notes=0\n")
    r = state(run)
    ok = (r.returncode == 0 and "step: 11" in r.stdout
          and "LEDGER WRITER" in r.stdout and "triage APPROVED\n" in r.stdout)
    check("APPROVED with a routing tail → step 11, ledger then final report", ok,
          f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_needs_rework_writes_the_next_brief(tmp: Path) -> None:
    run = approved_run(tmp, "# Triage\n\nVERDICT: NEEDS_REWORK rows=2 rework_brief=x\n")
    expect("NEEDS_REWORK at r1 → step 10, write impl-ws1-r2.md", run,
           "10", "impl-ws1-r2.md", 0)


def rework_rounds(run: Path, upto: int) -> None:
    """Add fully-reviewed NEEDS_REWORK rounds 2..upto to an approved run."""
    for rnd in range(2, upto + 1):
        (run / "briefs" / f"impl-ws1-r{rnd}.md").write_text(BRIEF)
        (run / f"implementer-ws1-r{rnd}.md").write_text(DONE_REPORT)
        (run / f"verifier-r{rnd}.md").write_text("OUTCOME: PASS\n")
        for axis in ("code", "security", "perf"):
            (run / f"review-r{rnd}-{axis}.md").write_text("VERDICT: APPROVE\n")
        (run / f"triage-r{rnd}.md").write_text("VERDICT: NEEDS_REWORK rows=1\n")


def case_rework_cap_stops(tmp: Path) -> None:
    """Three reworks is the default cap; a fourth NEEDS_REWORK means the plan or
    the spec is wrong, and that is the user's call, not another round. Both edges
    are asserted — a case that checked only the STOP would pass just as happily
    with a cap of ten, and would not notice the cap moving again."""
    run = approved_run(tmp, "# Triage\n\nVERDICT: APPROVED rows=0\n")
    rework_rounds(run, 3)
    expect("a third NEEDS_REWORK is still a rework round", run,
           "10", "impl-ws1-r4.md", 0)
    rework_rounds(run, 4)
    expect("a fourth NEEDS_REWORK exits 1 and says STOP", run, "10", "STOP", 1)


def case_rework_cap_is_configurable(tmp: Path) -> None:
    """The repo's `.teamlead.json` wins over the default, the same precedence
    adrPath uses. Asserted as a counterfactual on one unchanged file set: it is a
    rework round, then the config alone turns it into a STOP."""
    run = approved_run(tmp, "# Triage\n\nVERDICT: APPROVED rows=0\n")
    rework_rounds(run, 2)
    expect("round 2 is a rework round under the default cap", run,
           "10", "impl-ws1-r3.md", 0)
    repo = tmp / "repo"
    repo.mkdir()
    (repo / ".teamlead.json").write_text('{"reworkCap": 1}\n')
    (run / "repo.txt").write_text(f"{repo}\n")
    expect("the same file set STOPs once .teamlead.json sets reworkCap=1", run,
           "10", "STOP", 1)


def case_bad_rework_cap_falls_back(tmp: Path) -> None:
    """A stopping rule that raises is worse than one that is merely not the number
    you configured, so every unusable value falls back to the default. `true` is in
    the list because bool is an int in Python and would otherwise cap at 1."""
    run = approved_run(tmp, "# Triage\n\nVERDICT: APPROVED rows=0\n")
    rework_rounds(run, 2)
    repo = tmp / "repo"
    repo.mkdir()
    (run / "repo.txt").write_text(f"{repo}\n")
    for body in ('{"reworkCap": 0}', '{"reworkCap": true}', '{"reworkCap": "3"}',
                 '{"reworkCap": -1}', '{not json', '{}'):
        (repo / ".teamlead.json").write_text(body)
        expect(f"reworkCap {body} falls back to the default", run,
               "10", "impl-ws1-r3.md", 0)


def case_global_config_sets_the_cap(tmp: Path) -> None:
    """The global tier — $TEAMLEAD_HOME/config.json — is a cap source in its own
    right, and had no coverage while it was the plugin's own file with no way to
    point it elsewhere. Three assertions on one unchanged file set, so each one
    discriminates: the global config alone turns a rework round into a STOP; a
    repo `.teamlead.json` outranks it in the other direction; and a repo value
    that is not a usable cap falls through to the global one rather than
    shadowing it with the built-in default. That last edge is the whole reason
    `paths.setting` keeps searching past an invalid value."""
    run = approved_run(tmp, "# Triage\n\nVERDICT: APPROVED rows=0\n")
    rework_rounds(run, 2)
    home = tmp / "home"
    home.mkdir()
    (home / "config.json").write_text('{"reworkCap": 1}\n')
    expect("the global config alone STOPs a round the default would allow", run,
           "10", "STOP", 1, home=home)

    repo = tmp / "repo"
    repo.mkdir()
    (repo / ".teamlead.json").write_text('{"reworkCap": 9}\n')
    (run / "repo.txt").write_text(f"{repo}\n")
    expect("the repo's .teamlead.json outranks the global config", run,
           "10", "impl-ws1-r3.md", 0, home=home)

    (repo / ".teamlead.json").write_text('{"reworkCap": "nine"}\n')
    expect("an unusable repo value falls through to the global config, not the "
           "default", run, "10", "STOP", 1, home=home)


def case_two_workstreams_report_the_blocked_one(tmp: Path) -> None:
    """With two streams the phase files carry `ws<N>-`; WS-1 is finished and WS-2
    has only its brief, so the next action has to be WS-2's."""
    run = mkrun(tmp, {
        "task.md": TASK, "plan.md": PLAN_2WS, "questions.md": ANSWERED,
        "plan-validation.md": VALID,
        "briefs/impl-ws1-r1.md": BRIEF, "briefs/impl-ws2-r1.md": BRIEF,
        "implementer-ws1-r1.md": DONE_REPORT,
        "verifier-ws1-r1.md": "OUTCOME: PASS\n",
        "review-ws1-r1-code.md": "VERDICT: APPROVE\n",
        "review-ws1-r1-security.md": "VERDICT: APPROVE\n",
        "review-ws1-r1-perf.md": "VERDICT: APPROVE\n",
        "triage-ws1-r1.md": "VERDICT: APPROVED rows=0\n"})
    r = state(run)
    ok = (r.returncode == 0 and "step: 7" in r.stdout and "WS-2" in r.stdout
          and "WS-1 r1: impl DONE" in r.stdout and "triage APPROVED" in r.stdout)
    check("ws-qualified names resolve; the unfinished stream sets the next action",
          ok, f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_missing_status_block_is_not_a_verdict(tmp: Path) -> None:
    """Straight from a real run: 3 of 4 round-1 reports ship with no fenced `status:`
    block, and `routing_line` then falls back to the first prose line. Its first word
    read as the status, so a report saying nothing routable printed `impl added`. The
    honest rendering is "(no routing line)", and the round still moves to the
    verifier — an unroutable report is not a blocked one."""
    prose = ("# Implementer report — WS-1 — round 1\n\n## Summary\nadded the lookup "
             "table and a test for it.\n\n## Refactor requests\nnone\n")
    run = mkrun(tmp, {"task.md": TASK, "plan.md": PLAN, "questions.md": ANSWERED,
                      "plan-validation.md": VALID, "briefs/impl-ws1-r1.md": BRIEF,
                      "implementer-ws1-r1.md": prose})
    r = state(run)
    ok = (r.returncode == 0 and "step: 8" in r.stdout
          and "impl (no routing line)" in r.stdout and "impl ADDED" not in r.stdout)
    check("a report with no status block is not routed on its prose", ok,
          f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_unreadable_triage_is_not_approval(tmp: Path) -> None:
    """The same gap one phase later, where it is dangerous rather than untidy: real
    triage files exist with no `VERDICT:` line, and falling through to "not
    NEEDS_REWORK, therefore approved" would ship an unreviewed stream."""
    run = approved_run(tmp, "# Triage\n\nAll three reviewers approved the diff.\n\n"
                            "## Rework count\n1\n")
    r = state(run)
    ok = (r.returncode == 0 and "step: 10 — triage verdict unreadable" in r.stdout
          and "LEDGER WRITER" not in r.stdout)
    check("a triage with no VERDICT line is not read as approval", ok,
          f"exit={r.returncode} out={r.stdout.strip()!r}")


# The on-disk shape from roles/triage.md:70 — and the shape all ten recorded runs
# actually use. The `rereview=` field belongs to triage's spoken return line, which
# a resumed coordinator no longer has, so nothing here may depend on it.
REWORK_TRIAGE = ("# Triage — round 1\n\nVerdict: NEEDS_REWORK\n\n"
                 "## Re-review set\n"
                 "code: re-run — always\n"
                 "security: re-run — the rework edits the validation phase\n"
                 "perf: carried — APPROVED (carried from round 1), no loop added\n\n"
                 "## Rework count\n1\n")


def rework_round(run: Path, axes: tuple[str, ...]) -> None:
    """Give WS-1 a round 2 whose reviews are exactly `axes`."""
    (run / "briefs" / "impl-ws1-r2.md").write_text(BRIEF)
    (run / "implementer-ws1-r2.md").write_text(DONE_REPORT)
    (run / "verifier-r2.md").write_text("OUTCOME: PASS\n")
    for axis in axes:
        (run / f"review-r2-{axis}.md").write_text("VERDICT: APPROVE\n")


def case_carried_axis_is_not_outstanding(tmp: Path) -> None:
    """A rework round is deliberately reviewed by a narrower set — code plus the
    specialists triage said to re-run. `perf: carried` is a recorded verdict, not a
    gap, so demanding it back leaves a finished stream stuck at step 9 forever."""
    run = approved_run(tmp, REWORK_TRIAGE)
    rework_round(run, ("code", "security"))
    r = state(run)
    ok = (r.returncode == 0 and "step: 10" in r.stdout
          and "triage-r2.md" in r.stdout and "perf" not in r.stdout)
    check("a `carried` axis is not an outstanding review", ok,
          f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_rerun_axis_is_still_required(tmp: Path) -> None:
    """The discriminating half: narrowing the set must not empty it. The same
    section says security re-runs, so its absence is genuinely outstanding — and
    reading the set from triage's *return* line instead of this section would have
    hidden it, that line never being written to disk."""
    run = approved_run(tmp, REWORK_TRIAGE)
    rework_round(run, ("code",))
    r = state(run)
    ok = (r.returncode == 0 and "step: 9" in r.stdout
          and "security" in r.stdout and "perf" not in r.stdout)
    check("a `re-run` axis is still required when absent", ok,
          f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_no_rereview_section_keeps_every_axis(tmp: Path) -> None:
    """A triage file with no such section says nothing about the next round, and
    `triage.md:45` settles which way to guess: unsure means re-run, because a wrong
    "carried" costs a missed defect and a wrong "re-run" costs a few minutes. So a
    malformed triage leaves all three expected rather than quietly excusing two."""
    run = approved_run(tmp, "# Triage — round 1\n\nVerdict: NEEDS_REWORK\n\n"
                            "## Rework count\n1\n")
    rework_round(run, ("code",))
    r = state(run)
    ok = (r.returncode == 0 and "step: 9" in r.stdout
          and "security" in r.stdout and "perf" in r.stdout)
    check("no `## Re-review set` section → every axis stays expected", ok,
          f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_code_axis_never_carries(tmp: Path) -> None:
    """`triage.md:41` makes code re-run unconditionally — it owns conformance and the
    TDD discipline, and a rework's commits are exactly what nobody has checked. A
    triage that carries it anyway is malformed, and template drift is not
    hypothetical here: a recorded run already writes a basis line the template does
    not describe. So the one gate that must never be skipped is not left to the
    file's wording."""
    tri = ("# Triage — round 1\n\nVerdict: NEEDS_REWORK\n\n## Re-review set\n"
           "code: carried — APPROVED (carried from round 1)\n"
           "security: carried — APPROVED (carried from round 1)\n"
           "perf: carried — APPROVED (carried from round 1)\n\n"
           "## Rework count\n1\n")
    run = approved_run(tmp, tri)
    rework_round(run, ())
    r = state(run)
    ok = (r.returncode == 0 and "step: 9" in r.stdout
          and "(code)" in r.stdout and "security" not in r.stdout)
    check("`code: carried` is ignored — code review is never skipped", ok,
          f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_unparseable_basis_still_means_re_run(tmp: Path) -> None:
    """Verbatim from a recorded run: `perf: sanity pass again for WS-2 — …`. It means
    re-run and matches neither template keyword, so a parser keyed on `re-run` drops
    a reviewer the coordinator is about to spawn. Only `carried` may narrow."""
    tri = ("# Triage — round 1\n\nVerdict: NEEDS_REWORK\n\n## Re-review set\n"
           "code: re-run — always\n"
           "security: carried — APPROVED (carried from round 1)\n"
           "perf: sanity pass again for WS-2 — it loops over `codes`\n\n"
           "## Rework count\n1\n")
    run = approved_run(tmp, tri)
    rework_round(run, ("code",))
    r = state(run)
    ok = (r.returncode == 0 and "step: 9" in r.stdout
          and "perf" in r.stdout and "security" not in r.stdout)
    check("a basis line the template did not anticipate still means re-run", ok,
          f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_adjudicated_verifier_fail_stays_adjudicated(tmp: Path) -> None:
    """From a real run: `OUTCOME: FAIL` whose only failing test the commits never
    touched, correctly reviewed anyway and triaged APPROVED_WITH_NOTES. Re-reading
    the FAIL on resume sends the coordinator back to re-decide `touched=no` — a
    judgement already made, recorded, and built on."""
    run = approved_run(tmp, "# Triage\n\nVerdict: APPROVED_WITH_NOTES\n")
    (run / "verifier-r1.md").write_text(
        "OUTCOME: FAIL\n\ntests/legacy/test_old_export.py, touched: no\n")
    expect("a FAIL that triage already ruled on does not reopen step 8", run,
           "11", "LEDGER WRITER", 0)


def case_unadjudicated_verifier_fail_still_stops(tmp: Path) -> None:
    """The discriminating half: with no triage for the round the FAIL is genuinely
    undecided, and `touched=yes|no` is the coordinator's call to make."""
    run = approved_run(tmp, "# Triage\n\nVerdict: APPROVED\n")
    (run / "triage-r1.md").unlink()
    (run / "verifier-r1.md").write_text(
        "OUTCOME: FAIL\n\ntests/legacy/test_old_export.py, touched: no\n")
    expect("an untriaged FAIL is still the coordinator's to adjudicate", run,
           "8", "touched=no", 0)


def case_triage_closes_the_review_phase(tmp: Path) -> None:
    """A triage file is written after reading the reviews, so it settles the phase
    even when a review file is missing — the alternative re-spawns reviewers whose
    findings are already consolidated."""
    run = approved_run(tmp, "# Triage\n\nVERDICT: APPROVED rows=0\n")
    (run / "review-r1-perf.md").unlink()
    expect("triage settles the review phase even with a review file absent", run,
           "11", "LEDGER WRITER", 0)


def case_final_report_ends_the_loop(tmp: Path) -> None:
    run = approved_run(tmp, "# Triage\n\nVERDICT: APPROVED rows=0\n")
    (run / "final-report.md").write_text("# Done\n\nDelivered WS-1.\n")
    expect("final-report.md → the loop is complete", run, "11", "complete", 0)


CASES = [
    case_not_a_run_directory,
    case_kickoff_without_task,
    case_plan_without_questions,
    case_questions_without_validation,
    case_needs_fix_without_fix_log,
    case_fix_log_present_moves_on,
    case_scope_cut_leads_the_relay,
    case_smaller_none_is_not_a_decision,
    case_accepted_cut_that_was_never_applied,
    case_applied_cut_dispatches,
    case_ship_as_planned_dispatches,
    case_no_open_questions_needs_no_answers_section,
    case_a_cut_holds_even_with_no_questions,
    case_answers_then_no_report,
    case_blocked_implementer_needs_the_user,
    case_done_then_verifier,
    case_cannot_run_needs_the_user,
    case_missing_reviewer_is_named,
    case_flags_remove_a_reviewer_from_the_expected_set,
    case_approved_reaches_the_ledger,
    case_needs_rework_writes_the_next_brief,
    case_rework_cap_stops,
    case_rework_cap_is_configurable,
    case_global_config_sets_the_cap,
    case_bad_rework_cap_falls_back,
    case_two_workstreams_report_the_blocked_one,
    case_missing_status_block_is_not_a_verdict,
    case_unreadable_triage_is_not_approval,
    case_carried_axis_is_not_outstanding,
    case_rerun_axis_is_still_required,
    case_no_rereview_section_keeps_every_axis,
    case_code_axis_never_carries,
    case_unparseable_basis_still_means_re_run,
    case_adjudicated_verifier_fail_stays_adjudicated,
    case_unadjudicated_verifier_fail_still_stops,
    case_triage_closes_the_review_phase,
    case_final_report_ends_the_loop,
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
