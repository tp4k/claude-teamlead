# Deferred work

`/teamlead` runs append here when triage demotes a request or the coordinator defers a refactor.

| Date | Run | Item | Why deferred | Source |
|---|---|---|---|---|
| 2026-10-15 | 2026-10-15-0946-codex-followup-fixes | Catch `RuntimeError` from `Path.resolve()` on a symlink-loop cwd and emit a `halt:` line instead of a traceback (scripts/next.py:325, 661-662) | hardening beyond the spec, needs a planner brief plus a looping symlink in the repo | triage-ws1-r1 |
| 2026-10-15 | 2026-10-15-0946-codex-followup-fixes | `~`-expansion of `cwd:` text (scripts/next.py:325) | fails closed (halts), unspecified input form | triage-ws1-r1 |
