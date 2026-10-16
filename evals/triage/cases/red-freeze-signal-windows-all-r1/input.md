===== plan.md (excerpt) =====
# Plan

## Goal

Close the two signal windows Codex confirmed in `run_red` (a signal before cleanup's first statement after a non-signal exception; a signal between the post-Popen check and `communicate()`), so no single SIGINT/SIGTERM can skip the group kill, the checkout restore or the handler restore, or be held until the RED command ends. Make the group-kill test and the compound-command test fail when the behaviour they claim to cover is removed.

Spec source: `/Users/g.evdokimov/.teamlead/runs/teamlead-retro/2026-10-15-1541-red-freeze-cleanup-followup/review-followup.md` (named by `$RUN/task.md`; `flags: none`). No ADR store. No project `CLAUDE.md` in the repo. Branch `analysis/run-retro-2026-10-14`, head `8e8bb3b`.

## Reviewer items

1. > After a non-signal exception, SIGTERM before the first cleanup assignment still skips group termination, checkout restoration, and handler restoration.

   **accepted** → WS-1. Re-run at `8e8bb3b`: `python3 /private/tmp/review-red-freeze-checks.py . entry` → `caught: SystemExit 143`, `handler restored: False`, `branch: ''`, `HEAD still RED: True`, `status: M src/limit.py`. Also closes the two earlier PARTIAL rows the item names. Mechanism replaced (see `do not reuse:` and Decision 1).

2. > A signal between the deferred-signal check and disabling deferral is recorded but cannot interrupt `communicate()`, potentially leaving RED checked out indefinitely.

   **accepted** → WS-1. Re-run: `… . startup` → `caught: SystemExit 143`, `elapsed: 2.06` (the whole `sleep 2`). Mechanism replaced (Decision 1).

3. > The new group-kill test reaches cleanup after its foreground writer has finished, so its claimed descendant-killing coverage proves nothing.
   > Additionally, `"REAPED" in out` also matches `"CHILD-NOT-REAPED"`.

   **accepted** → WS-1. Re-run: `… . kill` → `mutant result: (…, True, "EXIT 143\nHANDLERS True True\nREAPED\nstatus=''")`.

4. > The readiness timeout proceeds without asserting that the descendant wrote its marker, retaining a path that passes without exercising descendant termination.

   **accepted** → WS-1. Re-run: `… . ready` → `marker exists: False`, `mutant result: (…, True, '')`. Also closes the earlier PARTIAL compound-command row.

Not-in-scope items of the review-followup (`## Not in scope`) stay declined as the reviewer/user set them: the FIXED test_next row, the SETTLED `docs/deferred-work.md` row, the seven deferred-ledger notes, the CI 422 note.

accepted 4 · corrected 0 · declined 0

## Workstreams

| id | name | complexity | depends on | files/scopes | attacker-controlled input | hot path | public surface |
|---|---|---|---|---|---|---|---|
| WS-1 | run_red signal windows + kill/readiness test strength | M | none | `scripts/red_freeze.py`, `scripts/test_red_freeze.py` | yes | no | yes |

One stream: all four rows land in the same two files (rows 3–4 touch only the test file, which rows 1–2 also extend), so a split would serialize anyway.

## WS-1 — run_red signal windows + kill
…[truncated]

===== review-r1-code.md =====
# Review — WS-1 — round 1 — code

**Verdict:** NEEDS_REWORK

**Coverage:** rows 1–4, Decisions 1–10, the plan's test plan and probes, TDD (RED d67b318: RED_FROZEN, 187 lines; `--run` in a clone gives `exit 1`, 44 passed, 3 failed — all three sweep shapes, including the row-1 decode line 197 and the row-2 long-command line 190 "held 4.0s"), and public surface (`--run` exit codes and docstring contract unchanged). The one failure is in the table: the sweep is red on Python 3.9, which is CI's floor.

## Probes

list: 9 brief + 1 added; off-list clauses: 6; LIST_GAP: 0

All probes ran in per-probe copies under `$RUN/probe-ws1-r1-code/mut/<X>` of verified head 9d121c5, using `PYTHONDONTWRITEBYTECODE=1`. Bytes were restored and checked after every probe. The unmutated baseline passed the 6 targeted cases.

- row 2 "not held until the command finishes" [off-list] → deleted the loop-top `_exit_if_signalled()` at scripts/red_freeze.py:186 → killed by scripts/test_red_freeze.py::case_a_sigterm_at_any_run_red_line_is_survived (long: lines 177–187 "held 4.0s after landing")
- bounded poll interval [off-list] → `POLL_SECONDS = 0.1` → `2.0` at scripts/red_freeze.py:136 → killed by scripts/test_red_freeze.py::case_a_sigterm_at_any_run_red_line_is_survived (long: lines 187/188 "held 2.0s")
- Decision 1, handler never raises [off-list] → `raise SystemExit(128 + signum)` added after scripts/red_freeze.py:143 → killed by scripts/test_red_freeze.py::case_a_sigterm_at_any_run_red_line_is_survived (all 3 shapes)
- exit after cleanup when no exception propagates [off-list] → deleted scripts/red_freeze.py:204-205 → killed by scripts/test_red_freeze.py::case_signal_in_cleanup_after_a_normal_exit_is_not_swallowed and ::case_a_sigterm_at_any_run_red_line_is_survived (long and normal: `RETURNED 0`)
- Decision 3, clear before install [off-list variant of the brief's checkout probe] → moved `_recorded.clear()` from scripts/red_freeze.py:174 to after the handler install → killed by scripts/test_red_freeze.py::case_a_sigterm_at_any_run_red_line_is_survived (line 176 `RETURNED 0`)
- one run's signal does not leak into the next (rerun of a claimed kill) → deleted scripts/red_freeze.py:174 → killed by scripts/test_red_freeze.py::case_a_signal_in_one_run_does_not_leak_into_the_next
- first recorded signal wins (rerun of a claimed kill) → `_recorded[0]` → `[-1]` at scripts/red_freeze.py:148 → killed by scripts/test_red_freeze.py::case_second_signal_in_cleanup_keeps_the_first_exit_code
- propagating exception stands (rerun of a claimed kill) → `if not exiting:` → `if True:` at scripts/red_freeze.py:204 → killed by scripts/test_red_freeze.py::case_signal_in_cleanup_entered_with_the_flag_unset_still_cleans_up
- `_kill_group` keeps killpg but drops the reap (rerun of a claimed kill) → deleted scripts/red_freeze.py:157 → killed by scripts/test_red_freeze.py::case_sigterm_at_group_kill_start_still_cleans_up (second check, `GROUP-NOT-WAITED`)
- `exiting` set on the exception path [off-list] → `exiting = True` → `pass` at scripts/red_freeze.py:191 → killed by scripts/test_red_freeze.py::case_signal_in_cleanup_entered_with_the_flag_unset_still_cleans_up and ::case_a_sigterm_at_any_run_red_line_is_survived (decode lines 190–203)
- added: the sweep's non-vacuity guards → NOT PROBED. They are test-side structural checks with no production clause.

## Findings

| Sev | Location | Req/Concern | Problem → Fix |
|---|---|---|---|
| HIGH | scripts/test_red_freeze.py:812 (SWEEP_HARNESS `info["exc"] = …`), read at :905 | Decision 8 (Python floor 3.9; CI matrix 3.9–3.13). Full suite must be green. | On Python 3.9, `python3.9 scripts/test_red_freeze.py` gives `47 passed, 1 failed`: `a SIGTERM at any line of run_red (long command) … line 189 (exc TimeoutExpired): outcome 'EXIT 143', want one of ['TimeoutExpired']`. This reproduces 2/2. It passes on 3.11, 3.12 and 3.13. Production is correct: the run exits 143. The fault is in the test. On 3.9, the cleanup of `with contextlib.suppress(...)` emits a `line` event attributed to the body's last line (`break`, :189) while the suppressed `TimeoutExpired` is still in `sys.exc_info()`. A 6-line `settrace` repro shows `6 <class 'ValueError'>` on 3.9 and nothing on 3.11. The sweep therefore reads the swallowed exception as a propagating one. The CI 3.9 job will be red. This is the implementer's open question 1, and it fails today on the floor version rather than only after a future edit. → ADD one line in SWEEP_HARNESS immediately after :812: `if info["exc"] == "TimeoutExpired": info["exc"] = None`, with a comment saying the poll loop always suppresses it and that 3.9 reports the `with` cleanup as a line event. KEEP :812 and the `elif r["exc"]: want = {r["exc"]}` arm at :905 unchanged, so the decode shape still requires `UnicodeDecodeError` in `except`/`finally`. Re-run the full file on `/opt/homebrew/bin/python3.9` and on 3.12, and record both results. |

## Notes

- Decision 10 budget: the implementer reports that the sweep adds about 63 s against "~60 s". Most of that comes from the long shape running the full 4 s command once for each post-wait line, about 12 × 4 s, and the normal and decode shapes already cover those lines. Trimming would edit frozen lines, so it is left to the coordinator.
- A signal recorded during the initial `git checkout` still lets `Popen` start the RED command before the post-Popen check kills it. This is per Decision 1. A pre-Popen `_exit_if_signalled()` would avoid side effects from starting it, though it would not close the race.
- The sweep's hold bound is 1.0 s, so `POLL_SECONDS` values up to about 0.9 would survive. The constant itself is 0.1, which meets Decision 1.
- The test name `case_signal_in_cleanup_entered_with_the_flag_unset_still_cleans_up` names a flag that no longer exists. The name is pinned by Decision 4, so renaming it is optional.
- Python 3.10 was not exercised because no interpreter is installed here. CI covers it.

## Verification

per $RUN/verifier-r1.md: PASS. Head 9d121c5c and tree CLEAN were confirmed; the only change is the intentional ` M docs/deferred-work.md`.
- `/opt/homebrew/bin/python3.9 scripts/test_red_freeze.py` (probe clone at 9d121c5) → exit 1, `=== 47 passed, 1 failed`. The failure is quoted in the findings row.


===== review-r1-security.md =====
# Review r1 — security — WS-1

**Verdict:** APPROVED_WITH_NOTES

## Findings

| Sev | Location | Req/Concern | Problem → Fix |
|---|---|---|---|

## Notes

- `scripts/red_freeze.py:179-183`: a SIGINT/SIGTERM that lands during the initial `git checkout --detach` is now kept (Decision 3), but `Popen` still starts `cmd` before the first `_exit_if_signalled()` at the top of the loop (`:185`). The user-supplied command therefore runs for a moment after the interrupt and is then SIGKILLed with its group. Nothing is lost and the restore still happens. An `_exit_if_signalled()` before `Popen` would stop the command from starting at all. This is optional hardening and outside the accepted rows.
- Signal handling at the trust boundary (signals from outside, plus a hostile or non-UTF-8 `--run` command) is consistent with the code. `_record` never raises (`:142-145`). Exits are raised only at `:185` (`proc` is bound) and `:204` (after cleanup, only when `exiting` is false). An exception that is already propagating keeps its type. The group is SIGKILLed and reaped (`_kill_group`, `:152-156`). A syscall interrupted inside `communicate`, `proc.wait()` or the restore `git` is retried (PEP 475).
- `communicate(timeout=0.1)` is retried in a loop, so a command that never ends still waits indefinitely, which matches the code before this change. This is not a new DoS. Bounding it is ledger work under Decision 9.
- The new test harnesses quote paths with `shlex.quote` and use their own temp repos. Their `os.kill(pid, 0)` call is only a liveness probe, so the tests add no destructive surface.

## Verification

per $RUN/verifier-r1.md: PASS (head 9d121c5, matches the shared HEAD).


===== verifier-r1.md =====
# Verifier — round 1

OUTCOME: PASS

## Snapshot

head: 9d121c5c64342ff6c30303624eb84721cb44f6c5
tree: CLEAN
Observed HEAD equals expected before and after all commands. Status before and after was only ` M docs/deferred-work.md` (intentional, per coordinator; not staged, stashed or reverted). Implementer commits d67b318 673134e 9d121c5 are the three most recent commits on this HEAD.

## Commands

python3 scripts/test_red_freeze.py → exit 0 (=== 48 passed, 0 failed)
python3 /private/tmp/review-red-freeze-checks.py . kill → exit 0 (mutant result second element False)
python3 /private/tmp/review-red-freeze-checks.py . ready → exit 0 (marker exists: False; mutant result second element False)
python3 /private/tmp/review-red-freeze-checks.py . entry → exit 0 (caught UnicodeDecodeError; elapsed 0.03; handler restored True; branch 'main'; HEAD still RED False; status empty)
python3 /private/tmp/review-red-freeze-checks.py . startup → exit 0 (elapsed 2.05; handler restored True; branch 'main'; HEAD still RED False; status empty)
sed -n '190p;197p' scripts/red_freeze.py → exit 0 (line 190: `    except BaseException:`; line 197: `            # -f drops edits the command made to tracked files; the tree was clean.`) — the entry/startup traces no longer fire at these lines (Decision 6)
python3 /private/tmp/review-followup-probes.py . cleanup → exit 0 (exit: 143, branch 'main', HEAD still RED False, status empty)
python3 /private/tmp/review-followup-probes.py . signal-test → exit 0 (8 tuples, second element False each)
ruff check . → exit 0 (no output)
pyright scripts/red_freeze.py scripts/test_red_freeze.py → exit 1 (advisory, not in CI): 1 error, `red_freeze.py:210:17 "returncode" is not a known attribute of "None" (reportOptionalMemberAccess)` — same as the brief's baseline (was :215), no new errors
for suite in scripts/test_*.py ... → exit 0, no `FAILED` lines; all 21 suites passed (test_red_freeze 48 passed)

## Pre-existing analysis

No FAIL. The pyright error is the brief's stated baseline, advisory, not counted.

## Flaky

none
