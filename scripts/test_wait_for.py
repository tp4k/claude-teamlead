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
  * the routing keyword matched on its own, so a `Verdict on scope:` line closing
    the plan-validator's newest section outranked the real verdict — and only
    when the validator happened to phrase it that way, so it mis-routed about one
    run in three (require the colon immediately after the keyword).

No pytest dependency — the skill's scripts run with bare python3, and a suite
that needs an install is a suite nobody runs.
"""
from __future__ import annotations

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
