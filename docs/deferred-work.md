# Deferred work

`/teamlead` runs append here when triage demotes a request or the coordinator defers a refactor.

| Date | Run | Item | Why deferred | Source |
|---|---|---|---|---|
| 2026-10-15 | 2026-10-15-0946-codex-followup-fixes | Catch `RuntimeError` from `Path.resolve()` on a symlink-loop cwd and emit a `halt:` line instead of a traceback (scripts/next.py:325, 661-662) | hardening beyond the spec, needs a planner brief plus a looping symlink in the repo | triage-ws1-r1 |
| 2026-10-15 | 2026-10-15-0946-codex-followup-fixes | `~`-expansion of `cwd:` text (scripts/next.py:325) | fails closed (halts), unspecified input form | triage-ws1-r1 |
| 2026-10-15 | 2026-10-15-1541-red-freeze-cleanup-followup | Move the handler install at red_freeze.py:176-180 inside the `try` (or add an outer guard) so a signal between install and `try:` cannot leave `_raise_exit` installed with `_deferring` True (scripts/red_freeze.py:176-180) | in-process callers only; main exits anyway; changes production code beyond the spec | triage-ws1-r1 |
| 2026-10-15 | 2026-10-15-1541-red-freeze-cleanup-followup | Preserve a deferred signal / avoid exit 2 when the restore raises GitError, and handle non-UTF-8 command output in run_red instead of crashing (scripts/red_freeze.py:191, :236-238) | predates this round, not in spec | triage-ws1-r1 |
| 2026-10-15 | 2026-10-15-1541-red-freeze-cleanup-followup | Make a hanging restore interruptible (bounded wait or SIGKILL escalation) (scripts/red_freeze.py:197-206) | direct consequence of settled decision 2 and row 2; unbounded `proc.wait()` is out of scope, settled 8 | triage-ws1-r1 |
| 2026-10-15 | 2026-10-15-1541-red-freeze-cleanup-followup | Defer SIGHUP in cleanup (scripts/red_freeze.py) | spec covers SIGINT/SIGTERM only | triage-ws1-r1 |
| 2026-10-15 | 2026-10-15-1541-red-freeze-cleanup-followup | Delete redundant `_deferring = False` at :175 or keep as defensive reset (scripts/red_freeze.py:175) | equivalent mutant, no behavior change | triage-ws1-r1 |
| 2026-10-15 | 2026-10-15-1722-red-freeze-signal-windows | Add `_exit_if_signalled()` before `Popen` so a signal during the initial `git checkout --detach` never starts the RED command — Decision 1 accepts the post-Popen check and the spec does not require it; optional hardening that would not close the race (scripts/red_freeze.py:179-185) | Decision 1 accepts the post-Popen check; spec does not require it; would not close the race | triage-r1, triage-r2 |
| 2026-10-15 | 2026-10-15-1722-red-freeze-signal-windows | Bound `proc.communicate` polling so a never-ending command cannot wait indefinitely (scripts/red_freeze.py poll loop) | behaviour unchanged from before this change, deferred under Decision 9; distinct from the restore `proc.wait()` row above | triage-r1, triage-r2 |
