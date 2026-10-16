===== plan.md (excerpt) =====
# Plan

## Goal
Make `scripts/wait_for.py --rewritten` keep one dispatch's mtime baseline across a follow-up call after exit 2. A new dispatch of the same phase still has to start from a fresh baseline, and the timeout line has to say which of the not-ready states a file is in. Pin both observed timelines and the second-round case in `scripts/test_wait_for.py`, then document the new follow-up step where the coordinator docs teach `wait_for` usage.

## Workstreams

| id | name | complexity | depends on | files/scopes | attacker-controlled input | hot path | public surface |
|---|---|---|---|---|---|---|---|
| WS-1 | wait_for follow-up baseline via printed RETRY line | M | none | `scripts/wait_for.py`, `scripts/test_wait_for.py`, `skills/delegate/SKILL.md` | yes | no | yes |

## WS-1 — wait_for follow-up baseline via printed RETRY line

Goal (task's words): "a follow-up call for the same rewrite keeps the first call's baseline, so a file finished between calls is ready on the next call". A "NEW dispatch of the same phase … must not inherit a stale baseline", and "the timeout line distinguishes 'token present but mtime not newer than baseline' from 'pre-dispatch copy'".

Files:
- `scripts/wait_for.py` (exists)
- `scripts/test_wait_for.py` (exists)
- `skills/delegate/SKILL.md` (exists; rule 11 at line 32–34 and step 6b at line 157–161)

### Spec excerpt
Source (e): the user's verbatim task, `$RUN/task.md`:

> Fix scripts/wait_for.py in this repo (/Users/g.evdokimov/.claude/skills/teamlead): the `--rewritten` mtime baseline is snapshotted when the script STARTS, so a follow-up call (the docstring's own "wait one more chunk" advice for exit 2) re-snapshots it after the agent already finished and can never succeed. Observed 2026-10-05 in run ~/.teamlead/runs/<other-project-run>: wait #1 started 08:50:07Z, planner wrote plan.md (routing line `PLAN_FIXED fixed=3 new_paths=yes`) at 08:54:06Z, wait #1 timed out 08:54:08Z (missed by ~2s: size stability needs two polls); wait #2 started 08:54:12Z with baseline = finished file's mtime and timed out at 08:58:13Z with the false message `missing: plan.md (still the pre-dispatch copy)` although the token was present.
> Requirements: (1) a follow-up call for the same rewrite keeps the first call's baseline, so a file finished between calls is ready on the next call; (2) a NEW dispatch of the same phase (e.g. a second Fix round, where plan.md already ends in round 1's PLAN_FIXED) must not inherit a stale baseline and accept the previous round's file — design must say how one dispatch's baseline ends (e.g. a sidecar baseline persisted on timeout and cleared on exit 0/1, or an explicit dispatch-time flag; planner picks and justifies; never invent flags the coordinator docs don't teach — update SKILL.md/references where wait_for usage is documented); (3) the timeout line distinguishes "token present but mtime not newer than baseline" from "pre-dispatch copy"; (4) regression tests reproduci
…[truncated]

===== review-r1-code.md =====
# Code review — WS-1 — round 1

NEEDS_REWORK

Coverage: I checked task requirements 1–4, the design bullets (the RETRY line, `--baseline`, no persistence, the five timeout reasons in order, docs), all 7 acceptance bullets, the test plan item by item, TDD/freeze, simplicity, scope, and 3a public surface. One failure, listed in the table.

## Probes
- --baseline replaces the start snapshot → I changed `scripts/wait_for.py:143` to a bare `int(ns_arg)` → killed by `scripts/test_wait_for.py::case_observed_wait2_retry_keeps_first_baseline`
- RETRY carries the dispatch baseline → I deleted `scripts/wait_for.py:206-208` (the `--baseline` emission) → killed by `scripts/test_wait_for.py::case_observed_wait2_retry_keeps_first_baseline` (it also fails `case_observed_wait1_finish_just_before_deadline`, and `case_retry_chain_keeps_first_baseline` crashes with a ValueError)
- Reason 3 (token present, mtime not newer) comes before reason 4 → I deleted `scripts/wait_for.py:192-194` → killed by `scripts/test_wait_for.py::case_followup_without_baseline_names_token_present`

## Findings
| Sev | Location | Req/Concern | Problem → Fix |
|---|---|---|---|
| LOW | scripts/wait_for.py:206-208 | Task req (1): "a follow-up call for the same rewrite keeps the first call's baseline" | A `--rewritten` file that is absent when the first call starts has no `start_mtime_ns` entry (the documented "first write" case, `case_rewritten_file_that_appears_later`). So the RETRY line carries no `--baseline` for it, and the RETRY call snapshots the file the agent finished between the two calls. That is the original bug again. Repro in scratch: file absent, writer lands 0.5 s before the deadline of `--poll 1 --timeout 4 --rewritten f f`. Call 1 exits 2 (`not yet size-stable`). The printed RETRY exits 2 with `review.md (still the pre-dispatch copy)`, and its own RETRY line now pins `--baseline f <finished mtime>`, so every later retry fails too. Reachability is latent: no documented caller passes an absent `--rewritten` file today (SKILL.md 6b only uses plan.md). → In the RETRY loop, emit `--baseline FILE <start_mtime_ns.get(Path(FILE), 0)>` for EVERY `--rewritten` FILE. NS 0 means any real mtime is newer, so "first write" carries forward. KEEP the carry-forward of present files' NS exactly as is. ADD `case_retry_keeps_first_write_for_absent_rewritten_file`, race-free with no delayed writer: (1) `f` absent; (2) `run(tmp, "--poll", "1", "--timeout", "2", "--rewritten", str(f), str(f))` → assert exit 2; (3) `f.write_text("VERDICT: APPROVED\n")`; (4) `run_retry` the printed line → assert exit 0 and `"VERDICT: APPROVED"` in stdout. Register it in `CASES`. |

## Notes
- RED_CHANGED (2 lines): I diffed both. One is a signature re-wrap and the other splits a string literal into two adjacent literals that concatenate to the identical text. No assertion changed, and restoring the original lines would fail ruff E501, so I filed no row.
- Focus (a), flake risk is low. Writer and waiter start as back-to-back Python processes, so the write lands about 3.45 s into the waiter's run, against polls at about 3.0 s and 4.0 s (≈0.45 s margin either side). Each overshoot of `sleep(1)` pulls poll 3 later, toward the write. I ran the 4 timing cases 3× under 30 busy loops on 15 cores: 12/12 PASS. Only `case_observed_wait1` truly needs this timing; the other three could follow the race-free shape in the row above if CI ever flakes.
- `baseline_of` (`scripts/test_wait_for.py:332-334`) raises ValueError when there is no `--baseline`. A regression there aborts the whole suite before the summary, and the remaining cases go unreported. Consider returning -1 instead.
- SKILL.md:161: the added sentence is not wrapped like its neighbours (~120 cols). Rule 11 says "run the `RETRY:` line … verbatim". The command is the text after `RETRY: `, so consider saying "the command after `RETRY: `".
- I ran no probe for the non-integer NS argparse error (`wait_for.py:144-145`) because the plan has no test for it. The implementation is a plain `ap.error`.

## Verification
per $RUN/verifier-r1.md: PASS
- `python3 scripts/red_freeze.py --repo … dca71ce` (with and without `--run "python3 scripts/test_wait_for.py"`) → exit 1, RED_CHANGED: 2 of 119 lines (see Notes). The RED run shows 16 passed and 7 failed: every new case fails on its own assertion.


===== review-r1-security.md =====
APPROVED_WITH_NOTES

| Sev | Location | Req/Concern | Problem → Fix |
|---|---|---|---|

## Notes
- RETRY quoting holds: every arg goes through `shlex.join` (scripts/wait_for.py:210), so a path or `--expect` token carrying `$(…)`, `;` or spaces is single-quoted, not executed. Watched-file contents never reach the RETRY command or the reason text (only `f.name` and the coordinator's own token do), so a child agent cannot steer what the coordinator runs.
- `a.files` is appended without a `--` separator (wait_for.py:209). A wait-list path starting with `-` would turn the RETRY into an argparse error (exit 2, fails closed). No `$RUN` path starts with `-`, so not exploitable as specced.
- An arg containing a newline is quoted correctly but makes the `RETRY:` output span several lines, so a coordinator copying "the line" gets an unterminated quote (shell error, fails closed). `$RUN` paths and the SKILL.md tokens contain no newlines.
- `--baseline` accepts any int (negative, `1_000`, `+5`). A negative NS would turn off the staleness check for that file. Only the script's own RETRY output supplies NS (SKILL.md never teaches typing it), and the guard at wait_for.py:138 confines it to `--rewritten` files.

## Verification
per $RUN/verifier-r1.md: PASS


===== verifier-r1.md =====
# Verifier — round 1

OUTCOME: PASS

HEAD 9b9c27f matches the implementer's commits (dca71ce 9b9c27f); worktree clean.

## Commands

python3 scripts/test_wait_for.py → exit 0 (=== 23 passed, 0 failed)
python3 scripts/test_run_state.py → exit 0 (76 passed, 0 failed)
python3 scripts/test_skill_spec.py → exit 0 (60 passed, 0 failed)
python3 scripts/test_python_floor.py → exit 0 (8 passed, 0 failed)
ruff check . → exit 0
pyright scripts/wait_for.py scripts/test_wait_for.py → exit 0 (only a "new pyright version available" notice)

## Pre-existing analysis

none (no failures)

## Flaky

none
