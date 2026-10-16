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

===== review-r2-code.md =====
**Verdict:** APPROVED

**Coverage:** triage-r1 row 1 (3.9 sweep TimeoutExpired, scripts/test_red_freeze.py:812-816) re-checked against 4917f89; no failures.

**Probes:** none — test-only rework (production unchanged); assertion-removal review instead: 4917f89 is +4/-0, no assertion removed; :812 and the `elif r["exc"]: want = {r["exc"]}` arm (:906-907) are intact as the row required.

**Findings:**

| Sev | Location | Req/Concern | Problem → Fix |
|---|---|---|---|

**Notes:**
- The reset cannot hide a production regression that lets TimeoutExpired escape `run_red`: that run's outcome would be `TimeoutExpired`, not in `want = {"EXIT 143"}`, so the sweep still fails.
- Verifier ran `python3` = 3.12.4 only; the row's 3.9 acceptance was re-run here: `/opt/homebrew/bin/python3.9 scripts/test_red_freeze.py` → 48 passed, 0 failed at 4917f89, tree unchanged afterwards.

**Verification:** per $RUN/verifier-r2.md: PASS (head 4917f89, tree CLEAN apart from the user's intentional `docs/deferred-work.md`; shared HEAD matches).


===== verifier-r2.md =====
# Verifier — round 2

OUTCOME: PASS

## Snapshot

head: 4917f89a78e9bfcddacdf71e9bf2d0cdfadde3d6
tree: CLEAN
Status before, between and after commands: only ` M docs/deferred-work.md`, which the prompt marks as intentional (user's uncommitted ledger rows) and not a blocker. HEAD unchanged throughout. The implementer's only commit, 4917f89, is HEAD. Verification commands taken from impl-ws1-r1.md (r2 brief says they are unchanged).

## Commands

python3 scripts/test_red_freeze.py → exit 0 (=== 48 passed, 0 failed)
python3 /private/tmp/review-red-freeze-checks.py . kill → exit 0; mutant result second element False (as expected)
python3 /private/tmp/review-red-freeze-checks.py . ready → exit 0; marker exists: False; tuple second element False (as expected)
python3 /private/tmp/review-red-freeze-checks.py . entry → exit 0; caught: UnicodeDecodeError ...; handler restored: True; branch: 'main'; HEAD still RED: False; status: (empty)
python3 /private/tmp/review-red-freeze-checks.py . startup → exit 0; elapsed: 2.08; handler restored: True; branch: 'main'; HEAD still RED: False; status: (empty)
sed -n '190p;197p' scripts/red_freeze.py → exit 0
    190: `    except BaseException:`
    197: `            # -f drops edits the command made to tracked files; the tree was clean.`
python3 /private/tmp/review-followup-probes.py . cleanup → exit 0; exit: 143, branch: 'main', HEAD still RED: False, status: (empty) (as expected)
python3 /private/tmp/review-followup-probes.py . signal-test → exit 0; 8 lines, each tuple second element False (as expected)
ruff check . → exit 0 (no output)
pyright scripts/red_freeze.py scripts/test_red_freeze.py → exit 1 (advisory, not in CI). Output:
    /Users/g.evdokimov/teamlead-retro/scripts/red_freeze.py:210:17 - error: "returncode" is not a known attribute of "None" (reportOptionalMemberAccess)
    1 error, 0 warnings, 0 informations
  This is the baseline error named in the brief (previously at :215:17, line shifted). No new errors. Counted as matching baseline, not a failure.
for suite in scripts/test_*.py; do python3 "$suite" || echo "FAILED $suite"; done (run via a one-line script file because the worktree sandbox refused the inline loop; same loop, output redirected per suite) → exit 0; no "FAILED" lines across 21 suites

## Pre-existing analysis

No FAILs. (pyright's single error is the brief's stated baseline.)

## Flaky

none


===== triage-r1.md =====
# Triage — round 1

Verdict: NEEDS_REWORK

## Rows
| Sev | Location | Req/Concern (reviewers) | Problem → Fix |
|---|---|---|---|
| HIGH | scripts/test_red_freeze.py:812 (SWEEP_HARNESS `info["exc"] = …`), read at :905 | Decision 8 (Python floor 3.9, CI 3.9–3.13); full suite green (code) | On Python 3.9 the long-command sweep fails (`47 passed, 1 failed`, line 189 `exc TimeoutExpired`, outcome 'EXIT 143'): 3.9 emits a `line` event for the `contextlib.suppress` cleanup while the suppressed TimeoutExpired is in `sys.exc_info()`. Production is correct. → add `if info["exc"] == "TimeoutExpired": info["exc"] = None` right after :812 with a comment; keep :812 and the :905 `elif r["exc"]` arm; re-run the full file on python3.9 and 3.12 and record both. |

## Demoted to Notes
- Add `_exit_if_signalled()` before `Popen` so a signal during the initial `git checkout --detach` never starts the RED command — Decision 1 accepts the post-Popen check and the spec does not require it; optional hardening that would not close the race (scripts/red_freeze.py:179-185) (code, security)
- Bound `proc.communicate` polling so a never-ending command cannot wait indefinitely — behaviour unchanged from before this change, deferred under Decision 9 (scripts/red_freeze.py poll loop) (security)

## Notes for the user
- Sweep runtime adds about 63 s against the ~60 s budget of Decision 10, mostly the long shape running the 4 s command once per post-wait line (~12 x 4 s) that the normal and decode shapes already cover; trimming edits frozen lines, left to the coordinator.
- Sweep hold bound is 1.0 s, so a `POLL_SECONDS` up to about 0.9 would still pass; the constant is 0.1 which meets Decision 1.
- Test name `case_signal_in_cleanup_entered_with_the_flag_unset_still_cleans_up` names a flag that no longer exists; the name is pinned by Decision 4, rename optional.
- Python 3.10 was not exercised locally (no interpreter); CI covers it.
- Security: handler never raises, exits only at fixed points, group SIGKILLed and reaped, test harnesses quote paths; no new attack surface.

## Re-review set
code: re-run — always
security: carried — fix is test-only, production code unchanged (APPROVED_WITH_NOTES from /Users/g.evdokimov/.teamlead/runs/teamlead-retro/2026-10-15-1722-red-freeze-signal-windows/review-r1-security.md, round 1)
perf: carried — not dispatched in round 1 (hot path: no), test-only fix (skipped per /Users/g.evdokimov/.teamlead/runs/teamlead-retro/2026-10-15-1722-red-freeze-signal-windows/briefs/review-r1-perf.skip)

## Rework count
1
