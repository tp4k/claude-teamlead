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

## WS-1 — run_red signal windows + kill/readiness test strength

Goal: fix review-followup rows 1–4 — no single signal from cleanup entry (including a non-signal exception path) or in the Popen→communicate transition may skip the group kill, the checkout restore or the handler restore, or be held until the RED command finishes; and the group-kill and compound-command tests fail when descendant killing / the readiness marker is removed.

Files: `scripts/red_freeze.py`, `scripts/test_red_freeze.py`.

### Spec excerpt

From `/Users/g.evdokimov/.teamlead/runs/teamlead-retro/2026-10-15-1541-red-freeze-cleanup-followup/review-followup.md`, `## Findings to fix`:

> ### 1. HIGH `scripts/red_freeze.py:197` (CONFIRMED; also closes earlier rows "SIGTERM during cleanup raises out of the `finally` block…" and "Interrupting a compound RED command kills its shell but leaves descendants…", both judged PARTIAL)
>
> > After a non-signal exception, SIGTERM before the first cleanup assignment still skips group termination, checkout restoration, and handler restoration.
>
> Codex falsify step: `python3 /private/tmp/review-red-freeze-checks.py . entry` injects SIGTERM before line 197 following a decode error.
>
> Coordinator ran it: `caught: SystemExit 143`, `handler restored: False`, `branch: ''`, `HEAD still RED: True`, `status: M src/limit.py`.
>
> What the coordinator read: `:190 _deferring = False` precedes `:191 output, _ = proc.communicate()`. If `communicate()` raises a non-signal exception (e.g. UnicodeDecodeError on non-UTF-8 output), control goes through `except BaseException: exiting = True; raise` into `finally:`, whose first statement is `:197 _deferring = True`. A signal arriving before :197 runs finds `_deferring` False, so `_raise_exit` raises `SystemExit` out of the outer `finally`, skipping `_kill_group`, the restore `_git(...)` and the handler restore.
>
> ### 2. HIGH `scripts/red_freeze.py:190` (CONFIRMED, NEW in this run)
>
> > A signal between the deferred-signal check and disabling deferral is recorded but cannot interrupt `communicate()`, potentially leaving RED checked out indefinitely.
>
> Codex falsify step: `python3 /private/tmp/review-red-freeze-checks.py . startup` — SIGTERM before line 190 waits for the entire `sleep 2` command.
>
> Coordinator ran it: `caught: SystemExit 143`, `elapsed: 2.06`, `handler restored: True`, `branch: 'main'`. The signal was delayed until the command finished.
>
> What the coordinator read: head `:188 if _deferred: raise …` then `:190 _deferring = False`. A signal landing between them is appended to `_deferred` and nothing acts on it until `communicate()` returns. Base `a29bb9f:scripts/red_freeze.py:178-181` cleared the flag first (`_starting = False`) and checked `_deferred` after, so a signal in that window raised immediately; the reordering here introduced the window.
>
> Acceptance for rows 1–2 together: no single signal, at any point from cleanup entry (including a non-signal exception path) or in the Popen→communicate transition, may skip the group kill, the checkout restore or the handler restore, or be held until the RED command finishes on its own.
>
> ### 3. MEDIUM `scripts/test_red_freeze.py:593` (CONFIRMED)
>
> > The new group-kill test reaches cleanup after its foreground writer has finished, so its claimed descendant-killing coverage proves nothing.
> > Additionally, `"REAPED" in out` also matches `"CHILD-NOT-REAPED"`.
>
> Codex falsify step: `python3 /private/tmp/review-red-freeze-checks.py . kill` — replacing `_kill_group` with `pass` still passes the assertion at line 613.
>
> Coordinator ran it: `mutant result: (…, True, "EXIT 143\nHANDLERS True True\nREAPED\nstatus=''")`. Line 613: `out.split()[:2] == ["EXIT", "143"] and "REAPED" in out and restored`.
>
> ### 4. MEDIUM `scripts/test_red_freeze.py:444` (CONFIRMED; also closes earlier row "The compound-command signal test can pass without starting a descendant…", judged PARTIAL)
>
> > The readiness timeout proceeds without asserting that the descendant wrote its marker, retaining a path that passes without exercising descendant termination.
>
> Codex falsify step: `python3 /private/tmp/review-red-freeze-checks.py . ready` — replacing the production command with `exit 1` produces no marker, yet the test passes after its timeout.
>
> Coordinator ran it: `marker exists: False`, `mutant result: (…, True, '')`. Lines 443–447 loop until the deadline and then `proc.terminate()` unconditionally; no assertion requires the marker.

Also from the same file, `# Task`: "The earlier probe script `/private/tmp/review-followup-probes.py` (modes `cleanup`, `signal-test`) must keep passing." and "It is evidence only; do not commit it."

Interpretation (identical in brief): "any point" is read at statement granularity of `run_red`'s own frame — Codex's probes inject at a `run_red` line via `sys.settrace`, so the in-suite test does the same for every line `run_red` executes, not only lines 190 and 197. For a signal that lands while `run_red`'s handler is installed, the outcome is: group killed and reaped, checkout restored (branch and HEAD as before, tracked tree clean), caller's SIGINT/SIGTERM handlers back, then `SystemExit(128 + first signum)` — unless an exception was already propagating, whose type/code stands (current behaviour, pinned by `case_signal_in_cleanup_does_not_replace_an_exit_already_raised` and `case_signal_in_cleanup_entered_with_the_flag_unset_still_cleans_up`). "Not held until the RED command finishes" means the exit begins within a bounded poll interval, not when the command ends. A signal landing while the caller's handler is installed (before install, after restore) goes to the caller's handler and `run_red` returns normally.

### Observable acceptance

- New line-sweep case(s) in `scripts/test_red_freeze.py` fail at `8e8bb3b` and pass after: for each line `run_red` executes, one SIGTERM injected at that line's first execution leaves branch `main`, HEAD = the pre-run commit, `git status --porcelain` empty, the late-writing descendant dead (no `AFTER RESTORE` in `src/limit.py` after its delay), the caller's handlers back, and either exit 143 / the already-propagating exception, or (outside the handler window) a normal return with the caller's handler having received the signal. On the long-running-command path, each injected run ends in well under the command's duration. At `8e8bb3b` the decode-error path fails at the outer `finally`'s first line (row 1) and the long-command path fails the elapsed bound at the `_deferring = False` line (row 2).
- `python3 /private/tmp/review-red-freeze-checks.py . kill` prints `mutant result: (…, False, …)` (was `True`).
- `python3 /private/tmp/review-red-freeze-checks.py . ready` prints `marker exists: False` and `mutant result: (…, False, …)` (was `True`).
- `python3 /private/tmp/review-red-freeze-checks.py . entry` and `. startup` are run and their output recorded together with the statement now at lines 197 / 190 (Decision 6); where the trace fires, expect `handler restored: True`, `branch: 'main'`, `HEAD still RED: False`, empty `status:`, and for `startup` `elapsed` well under 2.
- `python3 /private/tmp/review-followup-probes.py . cleanup` still prints `exit: 143`, `branch: 'main'`, `HEAD still RED: False`, empty `status:`; `… . signal-test` still prints 8 tuples whose second element is `False`.
- Full suite and `ruff check .` green.

### Test plan

existing (must keep passing; they pin current semantics):
- `case_run_restores_on_sigterm`, `case_sigterm_kills_compound_command_descendants`, `case_sigterm_while_popen_starts_kills_the_child`, `case_sigterm_at_group_kill_start_still_cleans_up`, `case_sigterm_during_restore_checkout_does_not_abort_it`, `case_second_signal_in_cleanup_keeps_the_first_exit_code`, `case_signal_in_cleanup_after_a_normal_exit_is_not_swallowed`, `case_handlers_are_the_callers_after_run_red`, `case_signal_in_cleanup_does_not_replace_an_exit_already_raised`, `case_a_signal_in_one_run_does_not_leak_into_the_next`, `case_group_sigint_during_restore_does_not_break_it`, `case_signal_in_cleanup_entered_with_the_flag_unset_still_cleans_up`, `case_failed_restore_leaves_the_callers_handlers`, `case_background_descendant_killed_after_normal_exit`, `case_descendant_is_dead_before_the_restore` (all in `scripts/test_red_freeze.py`).

new:
- Line sweep over `run_red`, run in a subprocess harness (a stray SIGTERM must not hit the test runner), with line numbers derived from the live source (`inspect`/`ast`), never hard-coded. Three command shapes: (a) long-running command with a live descendant — covers startup, the Popen→wait transition and the wait itself, with an elapsed bound; (b) command that exits normally while a backgrounded late-writer is still alive — covers normal-path cleanup lines; (c) non-UTF-8 output (`DECODE_CMD` shape) — covers the exception path through `except`/`finally`. Non-vacuity: the case fails if a path injected at zero lines, if (c) never injected inside the outer `finally` before the group kill, or if (a) never injected between Popen's return and the wait.
- `case_sigterm_at_group_kill_start_still_cleans_up` (row 3): the command must leave a descendant alive when cleanup starts (backgrounded late-writer, readiness confirmed by a child-written marker before `run_red` proceeds to cleanup), and the reap check matches the exact `REAPED` token (a line equal to `REAPED`, not a substring).
- `case_sigterm_kills_compound_command_descendants` (row 4): the final `check` requires the readiness marker to have been written (digit content) before SIGTERM; a deadline expiry is a FAIL, not a silent proceed.

probe:
- probe: row 1 "including a non-signal exception path" — a fix that sets the protection one statement earlier (e.g. at the top of `except`) still leaves a window at the `except`/`raise` lines.
- probe: row 2 "Popen→communicate transition" — restoring base order (`flag off` then check) but leaving a signal between the check and the wait recorded and unread until the command ends.
- probe: row 2 "not held until the RED command finishes" — a poll that only checks the recorded signal after the command exits (e.g. `proc.wait()` instead of a bounded-timeout wait).
- probe: a signal during the initial `git checkout --detach` — clearing the recorded-signal list after the checkout (as `:182` does today) drops it, and the RED command then runs to completion.
- probe: "the checkout restore" — a mutant `_kill_group` that keeps `os.killpg` but drops `proc.wait()`, and one that keeps `proc.wait()` but drops `os.killpg`; the row-3 case must fail both (Codex's `kill` probe only removes both together).
- probe: row 4 — a production command that never starts the descendant (`exit 1`) must make the compound case fail, not pass after the deadline.
- probe: row 3 `"REAPED" in out` — harness output `CHILD-NOT-REAPED` must fail the row-3 case.
- probe: exit-code precedence — a signal recorded while an exception (decode error or a mid-run SystemExit 143) already propagates must not replace it; the first recorded signal's code wins over a later one.
- probe: one run's recorded signal must not abort the next `run_red` call (existing `again` mode).

### Reuse and scope

reuse: `scripts/test_red_freeze.py:CLEANUP_HARNESS` + `cleanup_run` (subprocess harness, `mode` switch, `start_new_session=True`, restored-tree check) and `late_writer(delay, pidfile)` + the `tmp.parent / f"{tmp.name}.pid"` out-of-repo marker precedent (`case_background_descendant_killed_after_normal_exit`); `subprocess.Popen.communicate(timeout=…)` retried after `subprocess.TimeoutExpired` (stdlib; the docs state retrying loses no output); `scripts/red_freeze.py:_kill_group` and `_git(..., new_session=True)` unchanged.
do not reuse: `scripts/red_freeze.py:_deferring` as the protection switch — it is a flag toggled at statement boundaries, and every toggle point is a window (row 1 at the `finally` entry, row 2 between check and toggle); replaced by Decision 1 (the handler only records; `run_red` raises at fixed points). `/private/tmp/review-red-freeze-checks.py` hard-coded `at = 197 / 190` as the test's injection points — those are line numbers of `8e8bb3b`, not statements.
keep because: review-followup.md `## Findings to fix` rows 1–4, all chosen by the user ("The user chose all four confirmed rows below").

### Review axes

- attacker-controlled input: yes — `--run "<cmd>"` is a CLI argument executed via the shell, its output is decoded (row 1's trigger is non-UTF-8 output), and signals arrive from outside the process.
- hot path: no — a one-shot verifier tool; no benchmark or performance test names it.
- public surface: yes — the `--run` exit codes (128+signum) and "puts the branch and HEAD back, also on SIGINT/SIGTERM" contract (`red_freeze.py:35-40`) are relied on by `references/roles/verifier.md:44` and `scripts/next.py:688`-generated verifier prompts.

### Verification commands

cwd: `/Users/g.evdokimov/teamlead-retro`
- `python3 scripts/test_red_freeze.py` — baseline at `8e8bb3b`: `44 passed, 0 failed`, ~48 s.
- `python3 /private/tmp/review-red-freeze-checks.py . kill` — expect `mutant result:` tuple second element `False`.
- `python3 /private/tmp/review-red-freeze-checks.py . ready` — expect `marker exists: False` and tuple second element `False`.
- `python3 /private/tmp/review-red-freeze-checks.py . entry` and `python3 /private/tmp/review-red-freeze-checks.py . startup` — record output plus `sed -n '190p;197p' scripts/red_freeze.py` (Decision 6).
- `python3 /private/tmp/review-followup-probes.py . cleanup` — expect `exit: 143`, `branch: 'main'`, `HEAD still RED: False`, empty `status:`.
- `python3 /private/tmp/review-followup-probes.py . signal-test` — expect 8 lines, each tuple's second element `False`.
- `ruff check .` (ruff 0.0.292, as CI pins).
- `pyright scripts/red_freeze.py scripts/test_red_freeze.py` — advisory, not in CI; baseline at `8e8bb3b` is 1 error (`red_freeze.py:215:17` `"returncode" is not a known attribute of "None"`); no new errors.
- `for suite in scripts/test_*.py; do python3 "$suite" || echo "FAILED $suite"; done` — once, before reporting done. None of the suites needs a clean worktree: they build temp repos (`docs/deferred-work.md` stays dirty).

## Dependency DAG / waves

WS-1: no edges; no manifest or lockfile.
Wave 1: WS-1.

## Decisions taken

1. Mechanism: the SIGINT/SIGTERM handler `run_red` installs only records the signal and never raises; `run_red` itself raises `SystemExit(128 + first recorded)` at fixed points — right after Popen returns (proc bound), inside a bounded wait loop (`proc.communicate(timeout=<module constant, ≤ 0.1 s>)` retried on `subprocess.TimeoutExpired`), and after cleanup when no exception is propagating. The `_deferring` flag is removed with it. Evidence: rows 1–2 are both windows at `_deferring` toggle points (`red_freeze.py:190`, `:197`), and row 1 re-opens two rows the previous run already fixed by moving toggles (review-followup.md row 1 header: "also closes earlier rows … both judged PARTIAL"); a handler that never raises has no toggle point. Stdlib: `Popen.communicate` "If the process does not terminate after timeout seconds, a TimeoutExpired exception will be raised. Catching this exception and retrying communication will not lose any output."
2. Signals interrupting the bounded wait or `_kill_group`'s `proc.wait()` / the restore `git` do not break them: with a handler that returns normally, PEP 475 (Python ≥ 3.5) retries the interrupted syscall.
3. The recorded-signal list is cleared before the handler is installed, not after the initial checkout (today `:182`), so a signal during `git checkout --detach` is acted on and not dropped.
4. Exit-code precedence is unchanged: the first recorded signal's code; an exception already propagating keeps its type/code. Evidence: `case_signal_in_cleanup_does_not_replace_an_exit_already_raised` and `case_signal_in_cleanup_entered_with_the_flag_unset_still_cleans_up` (asserts `"UnicodeDecodeError" in detail`) in `scripts/test_red_freeze.py`.
5. Probe compatibility (the probes are the acceptance evidence): keep `_kill_group` module-level, its body starting `try:\n        os.killpg`, and `def run_red` the next top-level def after it (the `kill` mutant slices between those strings); keep the literal `subprocess.Popen(cmd, shell=True` (the `ready` mutant string-replaces it — if absent the mutant is a no-op and the probe passes vacuously); keep `run_red(repo, red, cmd)`, and the names and `(tmp: Path)` signatures of `case_sigterm_at_group_kill_start_still_cleans_up` and `case_sigterm_kills_compound_command_descendants`, plus `SCRIPT`, `results`, `Repo` in the test module. Evidence: `/private/tmp/review-red-freeze-checks.py`, `/private/tmp/review-followup-probes.py`.
6. `entry`/`startup` probes hard-code `at = 197 if mode == 'entry' else 190`; after the change those lines hold other statements, so the in-suite line sweep (every executed line, derived from live source) is the acceptance for rows 1–2, and the two probes are run and recorded for evidence with the statements now at those lines.
7. The row-3/row-4 strengthened cases pass at RED (production already kills the group); their failing-before evidence is the `kill`/`ready` mutant probes. The RED commit still fails as a whole because the sweep fails at `8e8bb3b`, and `red_freeze --run` reads only the command's exit code (`red_freeze.py:30-31`).
8. Python floor 3.9 — `.github/workflows/ci.yml` matrix 3.9–3.13; `scripts/test_python_floor.py` enforces it. `communicate(timeout=)` (3.3+) and `sys.settrace` line events exist on 3.9.
9. Deferred-ledger items stay untouched: handler install remains outside the `try`; no SIGHUP; no bound on `proc.wait()`/the restore; no PGID-reuse handling; docstring "session" wording unchanged; no GitError/non-UTF-8 handling beyond row 1. Removing `_deferring` (including the redundant `:175` reset) is a consequence of Decision 1, not work on that ledger row. Comments that describe the removed flag (`_raise_exit`'s comment, the `DECODE_CMD` comment "with the deferral flag still unset") are updated to stay true; the handler may be renamed (no reference outside `red_freeze.py`: `grep -rn -e _raise_exit -e _deferring scripts references agents skills hooks` finds only the ledger).
10. Runtime budget: the new cases add at most ~60 s to `python3 scripts/test_red_freeze.py` (baseline ~48 s); keep late-writer delays short and avoid one `time.sleep(delay)` per swept line where one wait per path suffices.

## Project forbiddens

No project `CLAUDE.md` exists in `/Users/g.evdokimov/teamlead-retro`.

From `~/.claude/rules/python.md` (paths `**/*.py`):
- "**Never use `Any`** — it violates ANN401. Use specific types: `dict[str, str]`, `list[int]`, `Sequence[Path]`, or a concrete class. If a type is genuinely open, model it (`TypeVar`, `Protocol`, a union) rather than erasing it."
- "Never weaken the linter to make types pass: no `# noqa`, no `ruff` ignore sections, no loosening `pyproject.toml`. Fix the annotation instead."

From `~/.claude/CLAUDE.md`:
- "Never weaken linters (no ignore/disable for prettier/eslint/ruff/checkstyle)."
- "Targeted tests while iterating; full suite once before calling a multi-file change done. Fix until green — never report partial progress as complete."
- "Don't touch env vars, tool installs, or configs I've set up."

From review-followup.md `# Task`: "Codex's probe script is `/private/tmp/review-red-freeze-checks.py` … It is evidence only; do not commit it."

From review-followup.md `## Not in scope`: "Do not stage, edit or revert `docs/deferred-work.md`."

From `.github/workflows/ci.yml`: ruff is pinned to `0.0.292` ("Pinned on purpose"); "The suites are plain scripts with no pytest and no dependencies".

## Anti-scope

- `docs/deferred-work.md`: has intentional uncommitted rows; never stage, edit or revert it.
- `/private/tmp/review-red-freeze-checks.py`, `/private/tmp/review-followup-probes.py`: run them, never copy, edit or commit them.
- Deferred-ledger items listed in Decision 9.
- The earlier FIXED test_next row and `scripts/test_next.py`; `scripts/mutate.py`, `scripts/next.py`, `references/**`, `agents/**`, `skills/**`, `hooks/**`, `README.md`, `.github/**`.
- `check()`, `added_lines()`, `lines_at()`, `main()` and the freeze-check half of `red_freeze.py`; the `TAIL` output format.

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
