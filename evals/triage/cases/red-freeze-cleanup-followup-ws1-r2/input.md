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

===== review-ws1-r2-code.md =====
# Code review — WS-1 — round 2

**Verdict:** APPROVED

**Coverage:** I re-checked the two triage-ws1-r1 rows against rework commit 8e8bb3b only (24 `+` lines, 0 removed, test file only, red_freeze.py untouched). Row 1 (MEDIUM, decode entry): DECODE_CMD is at scripts/test_red_freeze.py:574. The mode line is at :595, and frozen lines :593-594 are byte-identical. The case is at :670-675 and asserts `restored` and `UnicodeDecodeError`, and it is registered in CASES at :778. Row 2 (LOW, restorefail): the harness arm is at :532-533 and the `except red_freeze.GitError` is at :542-543. The case is at :678-681 and asserts `GITERROR` and `HANDLERS True True`, and it is registered at :779. No findings.

**Probes:** list: 0 brief + 0 added; off-list clauses: 0; LIST_GAP: 0. The rework is test-only, so I did an assertion-removal review in place of mutation probes. `git show 8e8bb3b` has no removed lines, so no existing assertion was weakened. The implementer's observed kills on red_freeze.py:197 (deletion) and :205 (inner `finally` → `except BaseException: raise`/`else:`) agree with the mechanism. With :197 deleted, a SIGTERM at `_kill_group` raises before `killpg`, so `restored` is False. With :205 mutated, a GitError from the mocked `-f` restore skips the handler reinstall, so the output is `HANDLERS False False`.

## Findings
| Sev | Location | Req/Concern | Problem → Fix |
|---|---|---|---|

## Notes
- The freeze check `red_freeze.py --repo . be9ee95` returned RED_FROZEN: 129 frozen lines, all present at HEAD.

## Verification
per $RUN/verifier-ws1-r2.md: PASS (head 8e8bb3b equals the shared HEAD; `git status --porcelain=v1 --untracked-files=all` is empty)


===== verifier-ws1-r2.md =====
# Verifier — round 2

OUTCOME: PASS

## Snapshot

head: 8e8bb3bcd4fd1cd6e252d5a65119fffff0d3f900
tree: CLEAN
Commit under test 8e8bb3b equals HEAD. HEAD and `git status --porcelain=v1 --untracked-files=all` checked before and after the commands: unchanged, empty.

## Commands

(Commands taken from briefs/impl-ws1-r1.md, which the r2 brief says are unchanged. cwd /Users/g.evdokimov/teamlead-retro.)
python3 scripts/test_red_freeze.py → exit 0 (44 passed, 0 failed)
python3 scripts/test_mutate.py → exit 0 (65 passed, 0 failed)
python3 scripts/test_python_floor.py → exit 0 (8 passed, 0 failed)
python3 /private/tmp/review-followup-probes.py . cleanup → exit 0; output `exit: 143`, `branch: 'main'`, `HEAD still RED: False`, `status: ` (empty), as expected
python3 /private/tmp/review-followup-probes.py . signal-test → exit 0; 8 lines, second tuple element `False` on each, as expected
ruff check . → exit 0
pyright scripts/red_freeze.py scripts/test_red_freeze.py → exit 1 (advisory, not in CI): 1 error, `red_freeze.py:215:17 "returncode" is not a known attribute of "None"`. Same error as the baseline (was :195, line shifted); no new errors.
for suite in scripts/test_*.py; do python3 "$suite" || echo "FAILED $suite"; done → exit 0; 17 suites, 0 FAILED lines, all "0 failed"

## Pre-existing analysis

No FAIL. The pyright exit 1 is the one baseline error the brief names (advisory); not counted as a failure.

## Flaky

none


===== triage-ws1-r1.md =====
# Triage — round 1

Verdict: NEEDS_REWORK

## Rows
| Sev | Location | Req/Concern (reviewers) | Problem → Fix |
|---|---|---|---|
| MEDIUM | scripts/red_freeze.py:197; scripts/test_red_freeze.py:570-597 | Row 2: no single signal in cleanup may skip group kill or restore (code) | LIST_GAP. Deleting `_deferring = True` at :197 survives 42/42; non-UTF-8 output enters cleanup with the flag unset. Fix: add DECODE_CMD, `mode == "decode"` line after :587, a case asserting restored and UnicodeDecodeError, register in CASES. |
| LOW | scripts/red_freeze.py:205; scripts/test_red_freeze.py CLEANUP_HARNESS | Test plan: handlers restored after cleanup raises (code) | LIST_GAP. Inner `finally:` at :205 replaced by `except BaseException: raise`/`else:` survives 42/42. Fix: add `restorefail` harness arm, `except red_freeze.GitError`, a case asserting GITERROR and `HANDLERS True True`, register in CASES. |

## Demoted to Notes
- Move the handler install at red_freeze.py:176-180 inside the `try` (or add an outer guard) so a signal between install and `try:` cannot leave `_raise_exit` installed with `_deferring` True — in-process callers only; main exits anyway; changes production code beyond the spec (scripts/red_freeze.py:176-180)
- Preserve a deferred signal / avoid exit 2 when the restore raises GitError, and handle non-UTF-8 command output in run_red instead of crashing — predates this round, not in spec (scripts/red_freeze.py:191, :236-238)
- Make a hanging restore interruptible (bounded wait or SIGKILL escalation) — direct consequence of settled decision 2 and row 2; unbounded `proc.wait()` is out of scope, settled 8 (scripts/red_freeze.py:197-206)
- Defer SIGHUP in cleanup — spec covers SIGINT/SIGTERM only (scripts/red_freeze.py)
- Delete redundant `_deferring = False` at :175 or keep as defensive reset — equivalent mutant, no behavior change (scripts/red_freeze.py:175)

## Notes for the user
- Handler's `_deferring = True` (:147) deletion only opens a few-bytecode race; no deterministic test possible (code).
- cleanup_run adds about 22 s to the suite (now about 43 s) (code).
- Hanging restore can only be stopped with SIGKILL; hooks lose their controlling terminal (code, security).
- Security: APPROVED_WITH_NOTES, no findings.

## Re-review set
code: re-run — always
security: carried — fixes are test-only, no production change on its axis (APPROVED_WITH_NOTES from /Users/g.evdokimov/.teamlead/runs/teamlead-retro/2026-10-15-1541-red-freeze-cleanup-followup/review-ws1-r1-security.md)
perf: carried — not dispatched in round 1, hot path: no, fixes test-only (skipped per /Users/g.evdokimov/.teamlead/runs/teamlead-retro/2026-10-15-1541-red-freeze-cleanup-followup/briefs/review-ws1-r1-perf.skip)

## Rework count
1
