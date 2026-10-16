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

### Spec excerpt

From `/Users/g.evdokimov/.teamlead/runs/teamlead-retro/2026-10-15-0946-codex-followup-fixes/review-followup.md`, `## Findings to fix`:

> ### 1. HIGH `scripts/red_freeze.py:185` (verdict PRE-EXISTING-SUBSYSTEM-REWRITTEN; the user chose to fix it)
>
> > SIGTERM during cleanup raises out of the `finally` block, skipping group termination and checkout restoration.
>
> Codex falsify step: `python3 /private/tmp/review-followup-probes.py . cleanup` injects SIGTERM at `_kill_group` entry. Result: exit 143, HEAD stays detached at RED, and `src/limit.py` stays dirty. "Cleanup needs signal protection."
>
> What the coordinator read:
> - In `run_red`, SIGINT/SIGTERM are set to `_raise_exit` before the `try`. `_raise_exit` defers only while `_starting` is true; otherwise it does `raise SystemExit(128 + signum)`.
> - `finally:` runs `if proc is not None: _kill_group(proc)` (`os.killpg(proc.pid, signal.SIGKILL)` then `proc.wait()`), then `git(repo, *back)` (`checkout -q -f <origin>`). Only after both are the old handlers restored. A signal arriving anywhere in the `finally` therefore raises out of it and skips whatever is left.
> - Base `48afe46:scripts/red_freeze.py` had the same weakness: its `finally` ran `git checkout -q -f …` with `_raise_exit` still installed. This run rebuilt the cleanup (Popen with `start_new_session=True`, `_kill_group`, deferred signals), so the user chose to fix it here.
>
> ### 2. earlier: "Interrupting a compound RED command kills its shell but leaves descendants able to modify the restored checkout." — Codex: PARTIAL (`scripts/red_freeze.py:177`, `scripts/red_freeze.py:185`) (verdict CONFIRMED)
>
> This is the remaining gap from row 1. The group kill works on the normal path and when a signal arrives during Popen (`72c97c4`). A signal during the `finally` still skips `_kill_group`, so descendants survive. Fixing row 1 closes this row. Acceptance: no single signal or second signal, at any point in cleanup, may skip the group kill or the checkout restore.
>
> ### 3. MEDIUM `scripts/test_red_freeze.py:440` (verdict CONFIRMED)
>
> > The compound-command signal test can pass without starting a descendant because it waits only for detached HEAD.
>
> Codex falsify step: `python3 /private/tmp/review-followup-probes.py . signal-test` runs this head test against the base implementation, and 1 of 8 runs passes when it should fail. "Wait for a child-written readiness marker before signalling."
>
> What the coordinator read: in `case_sigterm_kills_compound_command_descendants`, the loop `while (repo.git("branch", "--show-current") != "" …): time.sleep(0.05)` is followed by `proc.terminate()`. `run_red` detaches HEAD at `checkout --detach <sha>`, before `subprocess.Popen(…)` spawns the command. So the test can send SIGTERM before any descendant exists.

Also from the same file, `# Task`: "Codex's probe script is `/private/tmp/review-followup-probes.py` … It is evidence only; do not commit it." And `## Not in scope`: "WS-3 open notes not raised by Codex: the "session" wording in the docstrings at red_freeze.py:39/:134, the unbounded `proc.wait()`, and the PGID-reuse race on normal exit. Not selected; leave them unless the cleanup fix touches those exact lines anyway."

Interpretation (identical in brief): "cleanup" is everything from the first statement of `run_red`'s outer `finally` through the checkout restore. A signal landing there is recorded, the group kill and restore complete, the caller's SIGINT/SIGTERM handlers are put back, and only then does `run_red` exit with `SystemExit(128 + <first signal's number>)`. If an exit was already propagating (a signal during `communicate()`), its code stands; a later signal in cleanup does not replace it.

### Observable acceptance

- Codex's probe, which fails at `a29bb9f` (`exit: 143`, HEAD still RED: True, status ` M src/limit.py`), now prints `exit: 143`, `branch: 'main'`, `HEAD still RED: False`, `status: ` (empty): `python3 /private/tmp/review-followup-probes.py . cleanup` from the repo root.
- New cases in `scripts/test_red_freeze.py` fail at `a29bb9f` and pass after: SIGTERM at the start of the group kill, SIGTERM during the restore checkout, and a second signal in cleanup each leave branch `main`, HEAD = the pre-run commit, `git status --porcelain` empty, the late-writing descendant dead (no `AFTER RESTORE` in `src/limit.py` after its delay), and exit code 143.
- The strengthened `case_sigterm_kills_compound_command_descendants`, run against base `48afe46:scripts/red_freeze.py`, fails in 8 of 8 runs: `python3 /private/tmp/review-followup-probes.py . signal-test` prints 8 result tuples whose second element is `False`. Against the new `red_freeze.py` it passes in `python3 scripts/test_red_freeze.py`.
- Full suite and `ruff check .` green.

### Test plan

existing:
- `scripts/test_red_freeze.py::case_run_restores_on_sigterm` — SIGTERM during the command restores branch/HEAD.
- `scripts/test_red_freeze.py::case_sigterm_while_popen_starts_kills_the_child` — deferral while Popen starts (prints `EXIT 143 REAPED`).
- `scripts/test_red_freeze.py::case_background_descendant_killed_after_normal_exit`, `::case_descendant_is_dead_before_the_restore`, `::case_run_restores_a_detached_head`, `::case_run_restores_branch_and_head` — normal-path cleanup.
- `scripts/test_mutate.py` (whole suite) — `mutate.py:75` imports `TEST_PATH, GitError, git` from `red_freeze`.

new:
- `scripts/test_red_freeze.py::<new case> — a SIGTERM landing as the group kill starts still kills and reaps the group and restores branch, HEAD and a clean tree; exit 143.`
- `scripts/test_red_freeze.py::<new case> — a SIGTERM landing while the restore checkout runs does not abort it: branch, HEAD and clean tree restored; exit 143.`
- `scripts/test_red_freeze.py::<new case> — a second signal (e.g. SIGINT after SIGTERM, or SIGTERM twice) landing during cleanup still leaves the group dead and the checkout restored; the exit code is the first signal's.`
- `scripts/test_red_freeze.py::<new case> — a signal landing during cleanup after the command exited normally is not swallowed: run_red exits 128+signum, after the restore.`
- `scripts/test_red_freeze.py::<new case> — after run_red returns and after it raises, SIGINT and SIGTERM carry the caller's handlers again (a recording handler left installed would make the process ignore SIGTERM).`
- `scripts/test_red_freeze.py::<new case> — a SIGINT delivered to red_freeze's whole process group (terminal Ctrl-C) during the restore checkout does not leave HEAD detached or the tree dirty.`
- `scripts/test_red_freeze.py::case_sigterm_kills_compound_command_descendants` (strengthened, same name and `(tmp: Path)` signature — the probe script calls it) — SIGTERM is sent only after the descendant has written a readiness marker, so the case fails against an implementation that does not kill the group.

probe:
- probe: signal at `_kill_group` entry — cleanup lets `SystemExit` escape before `os.killpg` (the a29bb9f behaviour).
- probe: signal during `proc.wait()` inside the group kill — handler raises there; the group is SIGKILLed but the restore is skipped.
- probe: signal between group kill and restore — protection covers the kill only, not the `git checkout -f`.
- probe: signal during the restore `git checkout` — `subprocess.run` is interrupted by the raising handler and kills the git child mid-checkout.
- probe: second signal during cleanup — the first is deferred, the second raises (e.g. handler defers once, then falls back to raising, as `mutate.py:on_signal` style re-arming would).
- probe: SIGINT and SIGTERM both — only SIGTERM protected; SIGINT in cleanup still raises.
- probe: signal in cleanup on the normal path — recorded and dropped; run_red returns the command's code as if nothing happened.
- probe: exit code — a deferred signal exits 1 or 0 instead of `128 + signum`; with two signals, the second's code wins.
- probe: handlers after run_red — the deferring handler stays installed after return/raise, or the restore order raises out of the handler-restore loop leaving one signal deferring.
- probe: `_deferred` state across RED commits — `main` loops `run_red` over several REDs; a signal recorded in one call leaks into the next call's decision.
- probe: group-wide SIGINT during the restore — the git child, in red_freeze's process group, dies on the Ctrl-C and the restore silently fails or raises `GitError`.
- probe: strengthened test — the marker is written inside the repo (shows as `??` in `git status --porcelain`, failing the case for the wrong reason) or the test signals on marker existence before its content is complete.

### Reuse and scope

reuse: `scripts/red_freeze.py:_raise_exit` with `_starting` / `_deferred` (the existing record-then-raise deferral, `red_freeze.py:129-139`, `:171-181`) — extend it to cover cleanup rather than adding a second mechanism; `scripts/red_freeze.py:_kill_group` for the group kill; `scripts/test_red_freeze.py:late_writer` (its `pidfile` argument already writes a child-side file before sleeping) and `POPEN_HARNESS` (an in-process monkeypatching harness that prints the outcome) for the new cases; `scripts/test_red_freeze.py:case_background_descendant_killed_after_normal_exit` for the pattern of a child-written file kept outside the repo (`tmp.parent / f"{tmp.name}.pid"`).
do not reuse: `scripts/mutate.py:on_signal` as "the signal-protection pattern" — it sets SIG_IGN and raises on the first signal, so a first signal inside cleanup would still escape; it is also out of this stream's scope.
do not reuse: `red_freeze.git` changes that alter its signature or default behaviour — `mutate.py:75` imports it; any restore-specific behaviour (e.g. shielding the git child from a group SIGINT) must not change what `mutate.py` gets.
keep because: review-followup.md rows 1–3, selected by the user (task.md).

### Review axes

- attacker-controlled input: yes — `--run "<cmd>"` is a CLI argument executed via the shell, and signals arrive from outside the process.
- hot path: no — a one-shot verifier tool; no benchmark or performance test names it.
- public surface: yes — the `--run` exit codes and "puts the branch and HEAD back, also on SIGINT/SIGTERM" contract are relied on by `references/roles/verifier.md` and `next.py`-generated verifier prompts.

### Verification commands

cwd: `/Users/g.evdokimov/teamlead-retro`
- `python3 scripts/test_red_freeze.py`
- `python3 scripts/test_mutate.py`
- `python3 scripts/test_python_floor.py`
- `python3 /private/tmp/review-followup-probes.py . cleanup` — expect `exit: 143`, `branch: 'main'`, `HEAD still RED: False`, empty `status:`.
- `python3 /private/tmp/review-followup-probes.py . signal-test` — expect 8 lines, each tuple's second element `False`.
- `ruff check .`
- `pyright scripts/red_freeze.py scripts/test_red_freeze.py` — advisory, not in CI: baseline at a29bb9f is 1 error (`red_freeze.py:195` `returncode` on optional); no new errors.
- `for suite in scripts/test_*.py; do python3 "$suite" || echo "FAILED $suite"; done` — once, before reporting done.

## Dependency DAG / waves

WS-1 and WS-2: no edges (disjoint files; no manifest or lockfile).
Wave 1: WS-1, WS-2.

## Decisions taken

1. Rows 1–3 form one stream — rows 1 and 3 both edit `scripts/test_red_freeze.py`; parallel streams need disjoint scopes (planner method 5).
2. Signal in cleanup: record, finish the group kill and restore, put back the caller's handlers, then `SystemExit(128 + first signum)`; an exit already propagating keeps its code. Evidence: existing convention `red_freeze.py:181` (`raise SystemExit(128 + _deferred[0])`) and `case_sigterm_while_popen_starts_kills_the_child` expecting `EXIT 143`; row 2 acceptance "no single signal or second signal, at any point in cleanup, may skip the group kill or the checkout restore".
3. A group-wide SIGINT (terminal Ctrl-C) reaching the restore's git child is inside row 2's acceptance — "no single signal … at any point in cleanup may skip … the checkout restore"; the restore `git` runs in red_freeze's own process group (`red_freeze.py:64-65`, `subprocess.run` without a new session). Mechanism is the implementer's, under the `do not reuse` constraint on `red_freeze.git`.
4. WS-2 removes the assertion instead of replacing it — `halted_on` at `scripts/test_next.py:322-326` already asserts `not r.kinds()`.
5. Keep the name and `(tmp: Path)` signature of `case_sigterm_kills_compound_command_descendants`, and keep `red_freeze._kill_group` as a module-level function called from `run_red`'s cleanup — Codex's probe script (`/private/tmp/review-followup-probes.py`, modes `signal-test` and `cleanup`) calls/patches both and is the acceptance evidence.
6. The readiness marker lives outside the repo — `case_sigterm_kills_compound_command_descendants` asserts `git status --porcelain == ""` (`scripts/test_red_freeze.py:447-450`), which lists untracked files; precedent `tmp.parent / f"{tmp.name}.pid"` at `scripts/test_red_freeze.py:504`.
7. Python floor 3.9 — CI matrix `.github/workflows/ci.yml` runs 3.9–3.13; `scripts/test_python_floor.py` enforces it.
8. Docstring "session" wording (`red_freeze.py:39`, `:154-157`) may be touched only if the cleanup fix rewrites those exact lines — review-followup.md `## Not in scope`.

## Project forbiddens

No project `CLAUDE.md` exists in `/Users/g.evdokimov/teamlead-retro`.

From `~/.claude/rules/python.md` (paths `**/*.py`):
- "**Never use `Any`** — it violates ANN401. Use specific types: `dict[str, str]`, `list[int]`, `Sequence[Path]`, or a concrete class. If a type is genuinely open, model it (`TypeVar`, `Protocol`, a union) rather than erasing it."
- "Never weaken the linter to make types pass: no `# noqa`, no `ruff` ignore sections, no loosening `pyproject.toml`. Fix the annotation instead."

From `~/.claude/CLAUDE.md`:
- "Never weaken linters (no ignore/disable for prettier/eslint/ruff/checkstyle)."
- "Targeted tests while iterating; full suite once before calling a multi-file change done. Fix until green — never report partial progress as complete."
- "Don't touch env vars, tool installs, or configs I've set up."

From review-followup.md `# Task`: "Codex's probe script is `/private/tmp/review-followup-probes.py` … It is evidence only; do not commit it."

From `.github/workflows/ci.yml`: ruff is pinned to `0.0.292` ("Pinned on purpose"); suites are plain scripts, "no pytest and no dependencies".

## Anti-scope

- `docs/deferred-work.md` (untracked): do not stage or edit (review-followup.md `## Not in scope`).
- `/private/tmp/review-followup-probes.py`: run it, never copy or commit it.
- The four earlier findings marked FIXED (cwd in generated commands, gate docs fix, `NEEDS_REWORK` recommendations, test_ledger wording).
- WS-3 open notes not selected: unbounded `proc.wait()`, PGID-reuse race on normal exit, "session" docstring wording — unless the cleanup fix rewrites those exact lines.
- `scripts/mutate.py` and its signal handling (`on_signal`), `scripts/next.py`, `references/**`, `agents/**`, `skills/**`, `README.md`.
- The initial `checkout --detach` and the Popen deferral (`red_freeze.py:170-181`) beyond what sharing one deferral mechanism requires.

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
