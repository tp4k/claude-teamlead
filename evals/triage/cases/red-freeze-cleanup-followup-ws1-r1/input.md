===== plan.md (excerpt) =====
# Plan

## Goal

Make `red_freeze.py --run`'s cleanup (group kill, then checkout restore) impossible to skip by a signal that lands inside it, and fix two weak tests Codex found: the compound-command SIGTERM test must wait for a child-written readiness marker, and `test_next.py`'s vacuous "no verifier file" assertion must go.

Spec source: the user-supplied review-followup file `/Users/g.evdokimov/.teamlead/runs/teamlead-retro/2026-10-15-0946-codex-followup-fixes/review-followup.md` (reviewed head `a29bb9f`, = current HEAD of `analysis/run-retro-2026-10-14`). No project CLAUDE.md, no PLAN.md, no ADR store.

## Reviewer items

1. "SIGTERM during cleanup raises out of the `finally` block, skipping group termination and checkout restoration." (`scripts/red_freeze.py:185`) — **accepted** → WS-1. Confirmed at `scripts/red_freeze.py:183-190`: the `finally` runs `_kill_group(proc)` then `git(repo, *back)` while `_raise_exit` (`:133-139`) is still installed and `_starting` is false.
2. "Interrupting a compound RED command kills its shell but leaves descendants able to modify the restored checkout." (PARTIAL, `:177`, `:185`) — **accepted** → WS-1, closed by row 1's fix; acceptance line "no single signal or second signal, at any point in cleanup, may skip the group kill or the checkout restore" is WS-1's acceptance.
3. "The compound-command signal test can pass without starting a descendant because it waits only for detached HEAD." (`scripts/test_red_freeze.py:440`) — **accepted** → WS-1. Confirmed: `scripts/test_red_freeze.py:441-445` polls `branch --show-current` only; `run_red` detaches at `red_freeze.py:170` before `Popen` at `:174`.
4. "The new 'no verifier file' assertion is vacuous because the router prints dispatches and never writes verifier reports." (`scripts/test_next.py:924`) — **accepted** → WS-2 (mechanism: remove; see Decisions). `halted_on` (`scripts/test_next.py:322-326`) already requires `not r.kinds()`.

accepted 4 · corrected 0 · declined 0

Not-in-scope items in the followup file (4 earlier findings FIXED, WS-3 open notes on docstring "session" wording / unbounded `proc.wait()` / PGID reuse, `docs/deferred-work.md`) stay excluded — see Anti-scope.

## Workstreams

| id | name | complexity | depends on | files/scopes | attacker-controlled input | hot path | public surface |
|---|---|---|---|---|---|---|---|
| WS-1 | red_freeze cleanup signal protection + readiness marker | M | none | `scripts/red_freeze.py`, `scripts/test_red_freeze.py` | yes | no | yes |
| WS-2 | test_next vacuous no-verifier-file assertion | S | none | `scripts/test_next.py` | no | no | no |

Rows 1–3 share `scripts/test_red_freeze.py`, so they are one stream.

## WS-1 — red_freeze cleanup signal protection + readiness marker

Workstream definition: Implement review-followup rows 1, 2 and 3: "red_freeze.py cleanup signal protection, row 2 closed by row 1, test_red_freeze readiness marker" (task.md). Files: `scripts/red_freeze.py`, `scripts/test_red_freeze.py`.

### S
…[truncated]

===== review-ws1-r1-code.md =====
# Review — WS-1 — round 1 — code

**Verdict:** NEEDS_REWORK

**Coverage:** I checked rows 1–3, the 7 `new:` and 6 `existing:` tests, both extras, settled decisions 1–10, file scope (only `scripts/red_freeze.py` and `scripts/test_red_freeze.py`), `git()`'s unchanged signature (mutate.py:75), the module-level `_kill_group` call, the out-of-repo marker and TDD. Both of Codex's probes pass in a clone at 7843f84: `cleanup` gives exit 143, `'main'`, False and an empty status, and `signal-test` gives 8/8 False. There are 2 test gaps, listed under Findings.

## Probes

list: 12 brief + 2 added; off-list clauses: 4; LIST_GAP: 2

All probes ran in the clone `$RUN/probe-ws1-r1-code`, detached at 7843f84, with `python3 scripts/test_red_freeze.py` and `PYTHONDONTWRITEBYTECODE=1`. The baseline was 42 passed. Each file was restored and byte-compared after every probe.

- signal at `_kill_group` entry (handler never defers) → `if _deferring:` → `if False:` at scripts/red_freeze.py:144 → killed by scripts/test_red_freeze.py::case_sigterm_at_group_kill_start_still_cleans_up (plus 7 other cases)
- exit code, first signal wins → `_deferred[0]` → `_deferred[-1]` at scripts/red_freeze.py:210 → killed by scripts/test_red_freeze.py::case_second_signal_in_cleanup_keeps_the_first_exit_code (re-run of a claimed kill)
- mid-run exit keeps its code → `if _deferred and not exiting:` → `if _deferred:` at scripts/red_freeze.py:209 → killed by scripts/test_red_freeze.py::case_signal_in_cleanup_does_not_replace_an_exit_already_raised (re-run of a claimed kill)
- `_deferred` state across RED commits → deleted `_deferred.clear()` at scripts/red_freeze.py:182 → killed by scripts/test_red_freeze.py::case_a_signal_in_one_run_does_not_leak_into_the_next
- group-wide SIGINT during the restore → `new_session=True` → `False` at scripts/red_freeze.py:204 → killed by scripts/test_red_freeze.py::case_group_sigint_during_restore_does_not_break_it
- signal between the group kill and the restore → moved the handler-restore loop and `_deferring = False` (red_freeze.py:206-208) above the restore `_git` at :204 → killed by scripts/test_red_freeze.py::case_sigterm_during_restore_checkout_does_not_abort_it and ::case_group_sigint_during_restore_does_not_break_it
- cleanup entered by a non-signal exception still defers [off-list] → deleted `_deferring = True` at scripts/red_freeze.py:197 (finally entry) → SURVIVED, 42/42 (row 1)
- handlers restored when the restore raises [off-list] → inner `finally:` at scripts/red_freeze.py:205 → `except BaseException: raise` / `else:` → SURVIVED, 42/42 (row 2)
- handler sets the flag before raising [off-list] → deleted `_deferring = True` at scripts/red_freeze.py:147 → SURVIVED. The kill and the restore are unaffected because `finally` sets the flag at :197. The only remaining effect is a few-bytecode race (see Notes), so no row was filed.
- reset at run_red entry [off-list] → deleted `_deferring = False` at scripts/red_freeze.py:175 → SURVIVED, an equivalent mutant. The inner finally at :208 already leaves the flag False on every exit. See Notes; no row was filed.
- strengthened marker test → Codex's `signal-test` against 48afe46 gave 8/8 False in the clone. The RED `--run` shows the 7 new-case FAILs exactly as reported (33 passed, 7 failed).

**How row 1 was confirmed with a real input.** In the clone, the harness ran a command that prints a non-UTF-8 byte and backgrounds `late_writer(DELAY_SLOW)` with its output sent to `/dev/null`:

    printf '\377'; <late_writer> >/dev/null 2>&1 &

TERM was fired at the group kill. `communicate()` raises UnicodeDecodeError while `_deferring` is False.
- Unmutated code: restored True; the UnicodeDecodeError propagates.
- With the :197 line deleted: `EXIT 143` and status `M src/limit.py`. The late writer survived and the checkout was not restored.

## Findings

| Sev | Location | Req/Concern | Problem → Fix |
|---|---|---|---|
| MEDIUM | scripts/red_freeze.py:197; scripts/test_red_freeze.py:570-597 | Row 2: "no single signal … at any point in cleanup may skip the group kill or the checkout restore" | **Problem:** Deleting `_deferring = True` at the `finally` entry (:197) survives 42/42. Every current case enters cleanup with the flag already set, either by the handler or by the try body. A real input enters it unset: non-UTF-8 command output makes `communicate()` raise UnicodeDecodeError at :191. With the line deleted, a SIGTERM at the group kill leaves the descendant alive and `src/limit.py` dirty. **Fix:** ADD a module constant next to `MIDRUN_CMD`: `DECODE_CMD = f"printf '\\377'; {late_writer(DELAY_SLOW)} >/dev/null 2>&1 &"`. ADD one new line after scripts/test_red_freeze.py:587: `cmd = DECODE_CMD if mode == "decode" else cmd`. ADD a case that calls `cleanup_run(tmp / "a", "TERM", "-", mode="decode")` and asserts `restored` and `"UnicodeDecodeError" in detail`, then register it in `CASES`. KEEP lines 586-587 byte-identical, because they are frozen. |
| LOW | scripts/red_freeze.py:205; scripts/test_red_freeze.py CLEANUP_HARNESS | Test plan: "after it raises, SIGINT and SIGTERM carry the caller's handlers again" | **Problem:** Turning the inner `finally:` at :205 into `except BaseException: raise` / `else:` survives 42/42. The only tested raise is the post-cleanup `SystemExit`. A restore that raises `GitError` (for example a rejecting hook or a stale `index.lock`) would leave `_raise_exit` installed with `_deferring` True, so later SIGTERMs are only recorded. **Fix:** ADD a `mode == "restorefail"` arm to the harness `run` wrapper. When `"-f" in args`, it returns `subprocess.CompletedProcess(args, 1, "", "forced")`. ADD `except red_freeze.GitError: print("GITERROR")` beside the existing `except SystemExit`. ADD a case asserting `"GITERROR" in out and "HANDLERS True True" in out`. KEEP every existing harness line unchanged. |

## Notes

- Deleting the handler's `_deferring = True` (:147) only opens a race. A second signal landing between the handler's raise and the first statement of `finally` would raise inside `finally` and skip cleanup. No test can hit that deterministically, so I left the line as it is.
- The `_deferring = False` at :175 is redundant, because :208 already resets the flag on every exit. You can keep it as a defensive reset or delete it.
- The restore `git` now runs in its own session, and cleanup defers every SIGINT/SIGTERM. As a result, a hanging restore (for example a `post-checkout` hook that blocks) can only be stopped with SIGKILL. Hooks also lose their controlling terminal. This follows from settled decision 2 and row 2's acceptance.
- If the restore raises `GitError` while a signal is deferred, the signal is dropped and `main` exits 2 (the implementer raised this as an open question). Non-UTF-8 command output crashes `run_red` with UnicodeDecodeError instead of giving a RED run. Both predate this round.
- `cleanup_run` sleeps `DELAY_SLOW + 1.0` on each of its 11 calls, which adds about 22 s to the suite (now about 43 s).

## Verification

per $RUN/verifier-ws1-r1.md: PASS. Snapshot: shared HEAD 7843f84 matches `head:`, and `git status --porcelain=v1 --untracked-files=all` is empty. `red_freeze.py --repo . be9ee95` gives RED_FROZEN (129 lines). Running it with `--run "python3 scripts/test_red_freeze.py"` in the clone gives 7 FAILs, matching the reported `red:` lines. There were no failed commands.


===== review-ws1-r1-security.md =====
# Review — WS-1 — round 1 — security

**Verdict:** APPROVED_WITH_NOTES

## Findings

| Sev | Location | Req/Concern | Problem → Fix |
|---|---|---|---|

## Notes

- New interruptibility trade-off, `scripts/red_freeze.py:197-206`: during cleanup, SIGINT/SIGTERM are deferred and the restore `git` runs with `start_new_session=True`. If the restore hangs (for example a `.git/hooks/post-checkout` or a filter driver that the `--run` command itself wrote), neither Ctrl-C nor SIGTERM stops red_freeze or the git child. Only SIGKILL works, and the git/hook child outlives it. This is not a new trust boundary because `--run` is arbitrary code by design and could already `setsid` out of the group kill. It is the cost of row 2's "no signal may skip the restore". The same applies to the unbounded `proc.wait()` (out of scope, settled 8), which is now also uninterruptible.
- Narrow window, `scripts/red_freeze.py:176-180`: a signal after `signal.signal(..., _raise_exit)` but before `try:` raises SystemExit with `_deferring = True` and leaves `_raise_exit` installed, and no `finally` runs. Afterwards any SIGINT/SIGTERM is recorded and then dropped, so the process ignores them. The only caller, `main` (`:235`), does not catch SystemExit, so the process exits anyway. This matters only for an in-process caller that catches SystemExit. Moving the handler install inside the `try` (or resetting the flag in an outer guard) would close it.
- SIGHUP (terminal close) is not deferred. It still kills red_freeze mid-cleanup by default, but the restore git now sits in its own session and finishes on its own. The spec covers SIGINT/SIGTERM only.
- If the restore raises `GitError`, a deferred signal is dropped and `main` returns 2 (`:236-238`). The run still fails closed with a non-zero exit, as the implementer noted.
- `git()` keeps its signature and default behaviour (`:73-74` delegates to `_git` with `new_session=False`), so what `mutate.py:75` gets is unchanged. The test-side marker files (`.ready`, `.mark`) live under the per-case `TemporaryDirectory`.

## Verification

per $RUN/verifier-ws1-r1.md: PASS


===== verifier-ws1-r1.md =====
# Verifier — round 1

OUTCOME: PASS

## Snapshot

head: 7843f8427e2d0db694e691ada2b585780970c36e
tree: CLEAN
Checked before and after all commands: HEAD matched, `git status --porcelain=v1 --untracked-files=all` empty. Commits be9ee95 65ba58d 69769b8 0fcf5ac are all in the log below HEAD.

## Commands

python3 scripts/test_red_freeze.py → exit 0 (42 passed, 0 failed)
python3 scripts/test_mutate.py → exit 0 (65 passed)
python3 scripts/test_python_floor.py → exit 0 (8 passed)
python3 /private/tmp/review-followup-probes.py . cleanup → exit 0 (exit: 143, branch: 'main', HEAD still RED: False, status: empty) matches expectation
python3 /private/tmp/review-followup-probes.py . signal-test → exit 0 (8 tuples, second element False each; matches expectation)
ruff check . → exit 0
pyright scripts/red_freeze.py scripts/test_red_freeze.py → exit 1 (advisory per brief; matches stated baseline, no new errors):
  red_freeze.py:215:17 - error: "returncode" is not a known attribute of "None" (reportOptionalMemberAccess)
  1 error, 0 warnings, 0 informations
for suite in scripts/test_*.py; do python3 "$suite" || echo "FAILED $suite"; done → exit 0 (no FAILED line; 17 suites, all 0 failed)

## Pre-existing analysis

No test FAILs. The sole non-zero exit is the advisory pyright baseline error (the brief records it at a29bb9f as red_freeze.py:195; now line 215, same message).

## Flaky

none
