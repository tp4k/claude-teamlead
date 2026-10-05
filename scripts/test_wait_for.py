#!/usr/bin/env python3
"""Regression suite for wait_for.py:  python3 scripts/test_wait_for.py

Every case here is a bug that shipped, so the file doubles as the record of what
`wait_for.py` gets wrong when its readiness rule is loosened again:

  * a phase that rewrites a file in place was declared ready on the second poll,
    routing the coordinator on the PREVIOUS round's verdict (`--rewritten`);
  * `--rewritten` then proved too weak on its own: an agent rewriting through
    several `Edit` calls leaves the file fresh-mtime and size-stable in the gap
    between two edits, so the wait returned 0 on a half-written plan (`--expect`);
  * the routing line was taken from the FIRST match, so a plan quoting a spec's
    `status:` field routed on the quotation (search from the end);
  * the early-exit scan read the whole file, so that same quotation produced a
    false `EARLY_EXIT` on a healthy phase (scan the routing line only);
  * a follow-up call for the same rewrite re-snapshotted the mtime baseline after the
    agent had already finished, so it could never succeed and blamed "the
    pre-dispatch copy" for a file that held the token (`--baseline`, `RETRY:`);
  * the routing keyword matched on its own, so a `Verdict on scope:` line closing
    the plan-validator's newest section outranked the real verdict — and only
    when the validator happened to phrase it that way, so it mis-routed about one
    run in three (require the colon immediately after the keyword).

No pytest dependency — the skill's scripts run with bare python3, and a suite
that needs an install is a suite nobody runs.
"""
from __future__ import annotations

import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

WAIT_FOR = Path(__file__).resolve().parent / "wait_for.py"
FAST = ["--poll", "1", "--timeout", "12"]

# A plan whose spec excerpt quotes the implementer's own status vocabulary, then
# ends with the planner's real verdict. Both old bugs fire on this one file.
SPEC_QUOTE_PLAN = """# Plan — coupon application

Goal: apply stacked coupons in a fixed order.

## WS-1 — resolve order
reuse: pricing.discount.PERCENT_BASE
keep because: the spec's Acceptance section names this deliverable

Spec excerpt, verbatim:

status: blocked | partial | done
confidence: high | med | low

## Fix log
Tightened WS-1 scope after validation.

PLAN_FIXED fixed=2 new_paths=none
"""

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, str(WAIT_FOR), *args]
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)


def delayed_write(target: Path, body: str, after: float) -> subprocess.Popen[bytes]:
    """Write `body` to `target` after `after` seconds, from a separate process.

    The whole point of `--rewritten` is a file that changes *while* the wait
    runs, so the write cannot come from the waiting process itself.
    """
    src = (
        "import time, pathlib\n"
        f"time.sleep({after})\n"
        f"pathlib.Path({str(target)!r}).write_text({body!r})\n"
    )
    return subprocess.Popen([sys.executable, "-c", src])


def case_spec_quote_routes_on_verdict(tmp: Path) -> None:
    f = tmp / "plan.md"
    f.write_text(SPEC_QUOTE_PLAN)
    r = run(tmp, *FAST, str(f))
    ok = r.returncode == 0 and "PLAN_FIXED fixed=2" in r.stdout
    check("spec-quote plan routes on the real verdict, not the quotation",
          ok, f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_outcome_at_top(tmp: Path) -> None:
    f = tmp / "verifier-r1.md"
    f.write_text("OUTCOME: PASS\n\npytest -q -> exit 0\nruff check -> exit 0\n")
    r = run(tmp, *FAST, str(f))
    ok = r.returncode == 0 and "OUTCOME: PASS" in r.stdout
    check("OUTCOME at the top of the file is still found",
          ok, f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_real_blocked_exits_1(tmp: Path) -> None:
    f = tmp / "implementer-ws1-r1.md"
    f.write_text("# Report\n\nstatus: blocked\nquestion: which rounding mode?\n")
    r = run(tmp, *FAST, str(f))
    ok = r.returncode == 1 and "EARLY_EXIT" in r.stdout
    check("a genuinely blocked implementer exits 1",
          ok, f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_fallback_line(tmp: Path) -> None:
    f = tmp / "triage.md"
    f.write_text("# Triage\n\nNo rework rows this round.\n")
    r = run(tmp, *FAST, str(f))
    ok = r.returncode == 0 and "No rework rows this round." in r.stdout
    check("a file with no routing line falls back to its first prose line",
          ok, f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_rewritten_not_in_wait_list(tmp: Path) -> None:
    watched = tmp / "review-code.md"
    watched.write_text("VERDICT: APPROVE\n")
    other = tmp / "plan.md"
    other.write_text("PLAN_WRITTEN ws=1\n")
    r = run(tmp, *FAST, "--rewritten", str(other), str(watched))
    ok = r.returncode == 2 and "nothing waits on it" in r.stdout
    check("--rewritten naming a file nobody waits on exits 2 immediately",
          ok, f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_stale_rewrite_times_out(tmp: Path) -> None:
    f = tmp / "plan.md"
    f.write_text("PLAN_WRITTEN ws=2 paths=src/a.py\n")
    r = run(tmp, "--poll", "1", "--timeout", "3", "--rewritten", str(f), str(f))
    ok = (r.returncode == 2
          and "still the pre-dispatch copy" in r.stdout
          and "PLAN_WRITTEN" not in r.stdout)
    check("an unrewritten --rewritten target times out instead of routing stale",
          ok, f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_rewritten_file_that_appears_later(tmp: Path) -> None:
    """A `--rewritten` file that does not exist yet is a first write, not a stale
    one, so existence plus size stability is all it has to prove."""
    f = tmp / "plan.md"
    w = delayed_write(f, "PLAN_WRITTEN ws=1 paths=src/limiter.py\n", 2.0)
    r = run(tmp, *FAST, "--rewritten", str(f), str(f))
    w.wait()
    ok = r.returncode == 0 and "PLAN_WRITTEN ws=1" in r.stdout
    check("--rewritten on a not-yet-created file still becomes ready",
          ok, f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_fresh_rewrite_is_accepted(tmp: Path) -> None:
    """The flag must not merely time out — a real in-place rewrite has to pass."""
    f = tmp / "plan.md"
    f.write_text("PLAN_WRITTEN ws=2 paths=src/a.py\n")
    fixed = "# Plan\n\n## Fix log\nPLAN_FIXED fixed=1 new_paths=none\n"
    w = delayed_write(f, fixed, 2.0)
    r = run(tmp, *FAST, "--rewritten", str(f), str(f))
    w.wait()
    ok = r.returncode == 0 and "PLAN_FIXED fixed=1" in r.stdout
    check("a genuine in-place rewrite is accepted once its mtime moves",
          ok, f"exit={r.returncode} out={r.stdout.strip()!r}")


def delayed_writes(target: Path,
                   steps: list[tuple[float, str]]) -> subprocess.Popen[bytes]:
    """Write each `body` to `target` at its own delay, from a separate process.

    Models an agent that rewrites a file through several `Edit` calls: the file
    sits complete-looking and unchanging in the gap between two of them.
    """
    src = "import time, pathlib\np = pathlib.Path({!r})\n".format(str(target))
    for after, body in steps:
        src += f"time.sleep({after})\np.write_text({body!r})\n"
    return subprocess.Popen([sys.executable, "-c", src])


# A rewrite caught mid-flight: the header and one section are down, the phase's
# own marker is not. Same byte count on the next poll, because nothing is being
# written during the pause.
MID_EDIT = "# Plan — rewritten\n\n## Goal\nApply the answered precedence.\n"
FINISHED_EDIT = ("# Plan — rewritten\n\n## Goal\nApply the answered precedence.\n\n"
                 "## Fix log\nanswer 1: TooManyCoupons wins.\n\n"
                 "PLAN_FIXED fixed=4 new_paths=no\n")


def case_mid_edit_rewrite_fools_rewritten_alone(tmp: Path) -> None:
    """The iteration-15 defect, pinned so it cannot come back quietly.

    `--rewritten` proves only that the mtime moved and the size held for one
    poll. A multi-Edit rewrite satisfies both *between* edits, so the wait
    returns 0 on a half-written plan. Seen twice in one iteration (eval-9
    treatment, eval-6 baseline), both times worked around by a hand-rolled grep
    loop in the coordinator — which is the signal the tool was wrong, not the
    coordinator.
    """
    f = tmp / "plan.md"
    f.write_text("PLAN_WRITTEN ws=2 paths=src/a.py\n")
    w = delayed_writes(f, [(1.5, MID_EDIT), (6.0, FINISHED_EDIT)])
    r = run(tmp, *FAST, "--rewritten", str(f), str(f))
    w.wait()
    ok = r.returncode == 0 and "PLAN_FIXED" not in r.stdout
    check("BUG PINNED: --rewritten alone returns 0 on a mid-edit rewrite",
          ok, f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_expect_holds_until_the_marker_lands(tmp: Path) -> None:
    """Same timeline, with `--expect`: the wait must outlast the pause."""
    f = tmp / "plan.md"
    f.write_text("PLAN_WRITTEN ws=2 paths=src/a.py\n")
    w = delayed_writes(f, [(1.5, MID_EDIT), (6.0, FINISHED_EDIT)])
    r = run(tmp, *FAST, "--rewritten", str(f), "--expect", str(f), "PLAN_FIXED", str(f))
    w.wait()
    ok = r.returncode == 0 and "PLAN_FIXED fixed=4" in r.stdout
    check("--expect holds a mid-edit rewrite unready until its marker lands",
          ok, f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_expect_times_out_rather_than_routing_early(tmp: Path) -> None:
    """If the marker never arrives the honest answer is a timeout that names the
    reason, not a 0 on content the phase never finished."""
    f = tmp / "plan.md"
    f.write_text("PLAN_WRITTEN ws=2 paths=src/a.py\n")
    w = delayed_writes(f, [(1.0, MID_EDIT)])
    r = run(tmp, "--poll", "1", "--timeout", "5",
            "--rewritten", str(f), "--expect", str(f), "PLAN_FIXED", str(f))
    w.wait()
    ok = r.returncode == 2 and "no PLAN_FIXED in its routing line yet" in r.stdout
    check("--expect times out naming the missing marker",
          ok, f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_expect_ignores_a_prose_mention(tmp: Path) -> None:
    """A substring scan would pass on a plan that merely *describes* the marker."""
    f = tmp / "plan.md"
    f.write_text("PLAN_WRITTEN ws=1\n")
    body = ("# Plan\n\nThe Fix-mode planner ends this file with PLAN_FIXED once the "
            "answer is folded in.\n\nPLAN_WRITTEN ws=1\n")
    w = delayed_writes(f, [(1.0, body)])
    r = run(tmp, "--poll", "1", "--timeout", "5",
            "--rewritten", str(f), "--expect", str(f), "PLAN_FIXED", str(f))
    w.wait()
    ok = r.returncode == 2
    check("--expect does not accept a prose mention of the marker",
          ok, f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_expect_not_in_wait_list(tmp: Path) -> None:
    watched = tmp / "plan.md"
    watched.write_text("PLAN_FIXED fixed=1 new_paths=no\n")
    other = tmp / "review-code.md"
    other.write_text("VERDICT: APPROVE\n")
    r = run(tmp, *FAST, "--expect", str(other), "PLAN_FIXED", str(watched))
    ok = r.returncode == 2 and "nothing waits on it" in r.stdout
    check("--expect naming a file nobody waits on exits 2 immediately",
          ok, f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_scope_label_does_not_shadow_verdict(tmp: Path) -> None:
    """The plan-validator's Smaller/none section used to end with a `Verdict on
    scope:` label, and searching from the end made that line outrank the real
    verdict eleven lines above it — a third of runs routed on `none`."""
    f = tmp / "plan-validation.md"
    f.write_text("# Plan validation\n\nVerdict: PLAN_VALID\n\n## Smaller / none\n\n"
                 "**Verdict on scope:** none — already the smallest decomposition.\n")
    r = run(tmp, *FAST, str(f))
    ok = r.returncode == 0 and "PLAN_VALID" in r.stdout and "on scope" not in r.stdout
    check("a trailing `Verdict on scope:` label does not shadow the plan verdict",
          ok, f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_plan_needs_fix_is_a_routing_token(tmp: Path) -> None:
    """The bare-token half of the alternation: PLAN_* words route without a colon,
    so tightening the keyword+colon half must not cost them their match."""
    f = tmp / "plan-validation.md"
    f.write_text("# Plan validation\n\nVerdict: PLAN_NEEDS_FIX\n\n"
                 "**Verdict on scope:** drop WS-2.\n")
    r = run(tmp, *FAST, str(f))
    ok = r.returncode == 0 and "PLAN_NEEDS_FIX" in r.stdout
    check("PLAN_NEEDS_FIX routes even with a scope label after it",
          ok, f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_two_files_one_call(tmp: Path) -> None:
    """One call per phase is the whole savings claim, so the multi-file path
    matters as much as the single-file one."""
    a = tmp / "review-code.md"
    b = tmp / "review-tests.md"
    a.write_text("# Code review\n\nVERDICT: APPROVE\n")
    w = delayed_write(b, "# Test review\n\nVERDICT: NEEDS_REWORK\n", 2.0)
    r = run(tmp, *FAST, str(a), str(b))
    w.wait()
    ok = (r.returncode == 0
          and "VERDICT: APPROVE" in r.stdout
          and "VERDICT: NEEDS_REWORK" in r.stdout)
    check("one call blocks on the slower of two files and prints both",
          ok, f"exit={r.returncode} out={r.stdout.strip()!r}")

# The observed 2026-10-05 timelines: a rewrite that lands under one poll interval
# before the deadline is seen by the final poll only, so it is not yet size-stable.
CHUNK = 4
LANDS_BEFORE_DEADLINE = 3.5
PLAN_OLD = "PLAN_WRITTEN ws=2 paths=src/a.py\n"
PLAN_FIXED_3 = "# Plan\n\n## Fix log\nPLAN_FIXED fixed=3 new_paths=yes\n"
PLAN_FIXED_1 = "# Plan\n\n## Fix log\nPLAN_FIXED fixed=1 new_paths=none\n"
PLAN_FIXED_2 = "# Plan\n\n## Fix log\nround two\nPLAN_FIXED fixed=2 new_paths=none\n"
RETRY_PREFIX = "RETRY: "


def plan_args(f: Path, timeout: int) -> list[str]:
    return ["--poll", "1", "--timeout", str(timeout), "--rewritten", str(f),
            "--expect", str(f), "PLAN_FIXED", str(f)]


def retry_argv(out: str) -> list[str]:
    for line in out.splitlines():
        if line.startswith(RETRY_PREFIX):
            return shlex.split(line[len(RETRY_PREFIX):])
    return []


def run_retry(cwd: Path, argv: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a printed RETRY command exactly as printed, interpreter included."""
    if len(argv) < 2 or argv[1] != str(WAIT_FOR):
        return subprocess.CompletedProcess(argv, 99, "", "bad RETRY command")
    try:
        return subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                              check=False)
    except OSError as e:
        return subprocess.CompletedProcess(argv, 98, "", str(e))


def baseline_of(argv: list[str], f: Path) -> int:
    """The NS that RETRY's `--baseline` gives `f`, or -1 when it names no such file."""
    for i, tok in enumerate(argv[:-2]):
        if tok == "--baseline" and argv[i + 1] == str(f):
            try:
                return int(argv[i + 2])
            except ValueError:
                return -1
    return -1


def timed_out_first_call(
    tmp: Path, f: Path, body: str
) -> subprocess.CompletedProcess[str]:
    """A wait whose rewrite lands 0.5 s before the deadline, after the last poll."""
    w = delayed_write(f, body, LANDS_BEFORE_DEADLINE)
    r = run(tmp, *plan_args(f, CHUNK))
    w.wait()
    return r


def case_observed_wait1_finish_just_before_deadline(tmp: Path) -> None:
    f = tmp / "plan.md"
    f.write_text(PLAN_OLD)
    first_ns = f.stat().st_mtime_ns
    r = timed_out_first_call(tmp, f, PLAN_FIXED_3)
    argv = retry_argv(r.stdout)
    ok = (r.returncode == 2
          and "not yet size-stable" in r.stdout
          and "still the pre-dispatch copy" not in r.stdout
          and baseline_of(argv, f) == first_ns)
    check("a rewrite landing just before the deadline is size-unstable, "
          "with a RETRY line",
          ok, f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_observed_wait2_retry_keeps_first_baseline(tmp: Path) -> None:
    f = tmp / "plan.md"
    f.write_text(PLAN_OLD)
    r = timed_out_first_call(tmp, f, PLAN_FIXED_3)
    rr = run_retry(tmp, retry_argv(r.stdout))
    ok = (r.returncode == 2 and rr.returncode == 0
          and "plan.md: PLAN_FIXED fixed=3 new_paths=yes" in rr.stdout)
    check("the printed RETRY command accepts the file finished between calls",
          ok, f"exit={rr.returncode} out={rr.stdout.strip()!r}")


def case_followup_without_baseline_names_token_present(tmp: Path) -> None:
    f = tmp / "plan.md"
    f.write_text(PLAN_OLD)
    timed_out_first_call(tmp, f, PLAN_FIXED_3)
    r = run(tmp, *plan_args(f, 3))
    ok = (r.returncode == 2
          and "has PLAN_FIXED but its mtime is not newer than the baseline" in r.stdout
          and "still the pre-dispatch copy" not in r.stdout)
    check("a baseline-less re-run on a finished file says the token is present",
          ok, f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_retry_chain_keeps_first_baseline(tmp: Path) -> None:
    f = tmp / "plan.md"
    f.write_text(PLAN_OLD)
    first_ns = f.stat().st_mtime_ns
    r1 = timed_out_first_call(tmp, f, MID_EDIT)
    argv1 = retry_argv(r1.stdout)
    w = delayed_write(f, FINISHED_EDIT, LANDS_BEFORE_DEADLINE)
    r2 = run_retry(tmp, argv1)
    w.wait()
    argv2 = retry_argv(r2.stdout)
    ok = (r1.returncode == 2 and r2.returncode == 2 and bool(argv1) and bool(argv2)
          and baseline_of(argv1, f) == first_ns
          and baseline_of(argv2, f) == first_ns)
    check("a chained timeout carries the first call's baseline forward",
          ok, f"r1={r1.stdout.strip()!r} r2={r2.stdout.strip()!r}")


def case_second_round_does_not_accept_round_one_file(tmp: Path) -> None:
    f = tmp / "plan.md"
    f.write_text(PLAN_OLD)
    r1 = timed_out_first_call(tmp, f, PLAN_FIXED_1)
    done1 = run_retry(tmp, retry_argv(r1.stdout))
    stale = run(tmp, *plan_args(f, 3))
    w = delayed_write(f, PLAN_FIXED_2, 2.0)
    fresh = run(tmp, *FAST, *plan_args(f, 12)[4:])
    w.wait()
    ok = (done1.returncode == 0 and stale.returncode == 2
          and fresh.returncode == 0 and "fixed=2" in fresh.stdout)
    check("round 2's fresh wait rejects round 1's file and accepts round 2's",
          ok, f"done1={done1.returncode} stale={stale.returncode} "
              f"fresh={fresh.returncode} {fresh.stdout.strip()!r}")


def case_abandoned_wait_redispatch_does_not_accept_late_file(tmp: Path) -> None:
    f = tmp / "plan.md"
    f.write_text(PLAN_OLD)
    r1 = run(tmp, *plan_args(f, 3))
    f.write_text(PLAN_FIXED_3)
    r2 = run(tmp, *plan_args(f, 3))
    ok = RETRY_PREFIX in r1.stdout and r2.returncode == 2
    check("a re-dispatch's fresh wait rejects a file an abandoned wait never saw",
          ok, f"r1={r1.stdout.strip()!r} r2={r2.returncode} {r2.stdout.strip()!r}")


def case_baseline_not_in_rewritten_exits_2(tmp: Path) -> None:
    a = tmp / "plan.md"
    a.write_text(PLAN_OLD)
    b = tmp / "review-code.md"
    b.write_text("VERDICT: APPROVE\n")
    r = run(tmp, *FAST, "--rewritten", str(a), "--baseline", str(b), "123",
            str(a), str(b))
    ok = r.returncode == 2 and "nothing waits on it" in r.stdout
    check("--baseline naming a file that is not --rewritten exits 2 immediately",
          ok, f"exit={r.returncode} out={r.stdout.strip()!r}")


def case_retry_keeps_first_write_for_absent_rewritten_file(tmp: Path) -> None:
    f = tmp / "review.md"
    r1 = run(tmp, "--poll", "1", "--timeout", "2", "--rewritten", str(f), str(f))
    f.write_text("VERDICT: APPROVED\n")
    r2 = run_retry(tmp, retry_argv(r1.stdout))
    ok = r1.returncode == 2 and r2.returncode == 0 and "VERDICT: APPROVED" in r2.stdout
    check("a RETRY for a file absent at the first call accepts the file written since",
          ok, f"r1={r1.returncode} r2={r2.returncode} {r2.stdout.strip()!r}")


def case_retry_keeps_dash_separator(tmp: Path) -> None:
    """A wait-list file starting with `-` needs `--`; RETRY must keep it."""
    r = run(tmp, "--timeout", "0", "--", "-plan.md")
    rr = run_retry(tmp, retry_argv(r.stdout))
    ok = (r.returncode == 2 and rr.returncode == 2
          and "-plan.md" in rr.stdout and "usage:" not in rr.stderr)
    check("RETRY for a `-`-leading file runs as a timeout, not an argparse error",
          ok, f"first={r.stdout.strip()!r} retry={rr.returncode} "
              f"err={rr.stderr.strip()[:200]!r}")


def case_empty_file_reason(tmp: Path) -> None:
    """A stable zero-byte file is never ready; say empty, not size-unstable."""
    f = tmp / "empty.md"
    f.write_text("")
    r = run(tmp, "--poll", "1", "--timeout", "2", str(f))
    ok = (r.returncode == 2 and "empty.md (exists but is empty)" in r.stdout
          and "size-stable" not in r.stdout)
    check("a stable empty file times out naming it empty",
          ok, f"exit={r.returncode} out={r.stdout.strip()!r}")


CASES = [
    case_spec_quote_routes_on_verdict,
    case_outcome_at_top,
    case_real_blocked_exits_1,
    case_fallback_line,
    case_rewritten_not_in_wait_list,
    case_stale_rewrite_times_out,
    case_rewritten_file_that_appears_later,
    case_fresh_rewrite_is_accepted,
    case_mid_edit_rewrite_fools_rewritten_alone,
    case_expect_holds_until_the_marker_lands,
    case_expect_times_out_rather_than_routing_early,
    case_expect_ignores_a_prose_mention,
    case_expect_not_in_wait_list,
    case_scope_label_does_not_shadow_verdict,
    case_plan_needs_fix_is_a_routing_token,
    case_two_files_one_call,
    case_observed_wait1_finish_just_before_deadline,
    case_observed_wait2_retry_keeps_first_baseline,
    case_followup_without_baseline_names_token_present,
    case_retry_chain_keeps_first_baseline,
    case_second_round_does_not_accept_round_one_file,
    case_abandoned_wait_redispatch_does_not_accept_late_file,
    case_baseline_not_in_rewritten_exits_2,
    case_retry_keeps_first_write_for_absent_rewritten_file,
    case_retry_keeps_dash_separator,
    case_empty_file_reason,
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
