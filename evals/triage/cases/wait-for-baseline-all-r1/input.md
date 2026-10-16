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

> Fix scripts/wait_for.py in this repo (/Users/g.evdokimov/.claude/skills/teamlead): the `--rewritten` mtime baseline is snapshotted when the script STARTS, so a follow-up call (the docstring's own "wait one more chunk" advice for exit 2) re-snapshots it after the agent already finished and can never succeed. Observed 2026-10-05 in run ~/.teamlead/runs/<other-project-run> wait #1 started 08:50:07Z, planner wrote plan.md (routing line `PLAN_FIXED fixed=3 new_paths=yes`) at 08:54:06Z, wait #1 timed out 08:54:08Z (missed by ~2s: size stability needs two polls); wait #2 started 08:54:12Z with baseline = finished file's mtime and timed out at 08:58:13Z with the false message `missing: plan.md (still the pre-dispatch copy)` although the token was present.
> Requirements: (1) a follow-up call for the same rewrite keeps the first call's baseline, so a file finished between calls is ready on the next call; (2) a NEW dispatch of the same phase (e.g. a second Fix round, where plan.md already ends in round 1's PLAN_FIXED) must not inherit a stale baseline and accept the previous round's file — design must say how one dispatch's baseline ends (e.g. a sidecar baseline persisted on timeout and cleared on exit 0/1, or an explicit dispatch-time flag; planner picks and justifies; never invent flags the coordinator docs don't teach — update SKILL.md/references where wait_for usage is documented); (3) the timeout line distinguishes "token present but mtime not newer than baseline" from "pre-dispatch copy"; (4) regression tests reproducing both observed timelines plus the second-round case, runnable with the repo's existing test setup. Keep stdlib-only.

Current contract being changed, `scripts/wait_for.py` module docstring, "Exit codes":

> 2  timeout: the files not yet ready are listed, and one already present but unchanged is marked as still the pre-dispatch copy; wait one more chunk, then check the child's task output

and `scripts/wait_for.py` docstring, `--rewritten` paragraph:

> A `--rewritten` file must additionally show an mtime newer than the moment waiting began.

Coordinator doc, `skills/delegate/SKILL.md` rule 11:

> **Exit 2** = timeout: call it once more; two empty chunks → read the child's task-output path from the `Agent` result and report a stall to the user.

`skills/delegate/SKILL.md` step 6b:

> Wait: `wait_for.py --timeout 240 --rewritten $RUN/plan.md --expect $RUN/plan.md PLAN_FIXED $RUN/plan.md` — both flags are required.

**Planner's design (binding; see Decisions taken D1):**
- **Follow-up = the printed `RETRY:` line.** On exit 2 the script prints one extra line, `RETRY: <command>`. The command is the same invocation (`python3 <absolute path of wait_for.py>` plus the original arguments, shell-quoted), with one `--baseline FILE NS` pair added for every `--rewritten` file that had a baseline. NS is that file's effective baseline in integer nanoseconds. When the call already carried a `--baseline` for a file, that same value is carried forward rather than a new snapshot, so chained timeouts keep the first call's baseline.
- **New flag `--baseline FILE NS`** (repeatable, `nargs=2`). For FILE, it replaces the start-time mtime snapshot with NS. FILE must also be named by `--rewritten`; otherwise the script exits 2 at once with a line containing `nothing waits on it`, the same way the existing `--rewritten` and `--expect` guards do. A non-integer NS is an argparse error.
- **Nothing is persisted to disk.** A dispatch's baseline lives only in the command line. A new dispatch builds its wait from SKILL.md, which never carries `--baseline`, so it snapshots fresh (requirement 2 by construction).
- **Timeout reasons.** Each pending file gets exactly one reason, checked in this order:
  1. the file is missing → just its name (unchanged);
  2. the file exists, is an `--expect` file and its routing line lacks the token → `(exists, no <TOKEN> in its routing line yet)` (unchanged);
  3. the file is a `--rewritten` target with mtime ≤ baseline, and it is an `--expect` file whose token is present → new text containing `has <TOKEN> but its mtime is not newer than the baseline`;
  4. the file is a `--rewritten` target with mtime ≤ baseline → `(still the pre-dispatch copy)` (unchanged);
  5. otherwise (fresh but not yet size-stable across two polls) → new text containing `not yet size-stable`.

  Reason 1 must keep its current text, and reasons 2 and 4 must keep their current wording, because the existing tests assert them.
- **Docs.**
  - Update the `wait_for.py` docstring: the `--rewritten` paragraph and the exit-2 entry.
  - In `skills/delegate/SKILL.md` rule 11, "**Exit 2** = timeout: call it once more" becomes "run the `RETRY:` line it prints, verbatim". The "two empty chunks → stall" text stays unchanged.
  - Step 6b's wait gains one clause: a follow-up after exit 2 is the printed `RETRY:` line, which carries the dispatch's `--baseline`, while a new dispatch never passes `--baseline`.
  - Extend the bug list in the `test_wait_for.py` module docstring.
- Exit codes 0/1/2 and the routing-line rules (`ROUTING`, `EARLY`, `routing_line`, `token_present`) do not change. `scripts/run_state.py` imports `ROUTING` and `routing_line`.

### Observable acceptance
- **Timeline 1 (wait #1 misses by ~2 s):** `plan.md` holds a pre-fix plan. A writer lands `…PLAN_FIXED fixed=3 new_paths=yes` about 0.5 s before the deadline (under one poll interval, so after the last pre-deadline poll; a write 1 s or more early is seen on two polls and exits 0, because `scripts/wait_for.py` checks readiness at line 154 before the deadline at line 158) of `wait_for.py --poll 1 --timeout <t> --rewritten plan.md --expect plan.md PLAN_FIXED plan.md`. The call exits 2. Its timeout line does NOT say `still the pre-dispatch copy`, and it does say `not yet size-stable`. Its output carries a `RETRY:` line containing `--baseline <plan.md> <ns>`.
- **Timeline 2 (wait #2 follow-up):** running that `RETRY:` command verbatim (`shlex.split`) on the now-finished file exits 0 and prints `plan.md: PLAN_FIXED fixed=3 new_paths=yes` within a few polls. Today the same follow-up times out after the full chunk.
- **Requirement 3:** re-running the ORIGINAL command (no `--baseline`) on that finished file exits 2. The line says `has PLAN_FIXED but its mtime is not newer than the baseline` and not `still the pre-dispatch copy`. Today it prints the false `still the pre-dispatch copy` that was observed at 08:58:13Z.
- **Second round:** `plan.md` already ends in round 1's `PLAN_FIXED fixed=1` and round 1's wait ended with exit 0 after a timeout+RETRY. Round 2's fresh SKILL.md command does not exit 0 on round 1's file. Once round 2 writes `PLAN_FIXED fixed=2`, the same call exits 0 and prints `fixed=2`.
- **Abandoned wait:** a wait times out and is never retried, and the old agent then finishes the file. A re-dispatch's fresh command does not exit 0 on that late file.
- `--baseline` naming a file not in `--rewritten` exits 2 at once with `nothing waits on it`.
- `python3 scripts/test_wait_for.py` → `=== N passed, 0 failed`, where N = 16 + the new cases.

### Test plan
existing:
- `scripts/test_wait_for.py` — all 16 cases. These include `case_stale_rewrite_times_out`, which asserts `still the pre-dispatch copy`, and `case_expect_times_out_rather_than_routing_early`, which asserts `no PLAN_FIXED in its routing line yet`.
- `scripts/test_run_state.py`, because `run_state.py` imports `ROUTING` and `routing_line` from `wait_for`.
- `scripts/test_skill_spec.py`, because it checks that SKILL.md stays under 500 lines (currently 466).
- `scripts/test_python_floor.py`, because 3.9 is the floor and CI runs 3.9–3.13.

new:
- `scripts/test_wait_for.py::case_observed_wait1_finish_just_before_deadline` — a rewrite that lands about 0.5 s before the deadline with `--poll 1` (under one poll interval, after the last pre-deadline poll) exits 2 and is reported as `not yet size-stable`, not as the pre-dispatch copy. The output carries a `RETRY:` line with `--baseline`.
- `scripts/test_wait_for.py::case_observed_wait2_retry_keeps_first_baseline` — running the printed `RETRY:` command on the file finished between calls exits 0 with `PLAN_FIXED fixed=3`. This fails before the change.
- `scripts/test_wait_for.py::case_followup_without_baseline_names_token_present` — the original command re-run on the finished file exits 2 with `has PLAN_FIXED but its mtime is not newer than the baseline` and without `still the pre-dispatch copy`. This fails before the change.
- `scripts/test_wait_for.py::case_retry_chain_keeps_first_baseline` — a second timeout from a RETRY run (its write, where one is made, lands about 0.5 s before that call's deadline with `--poll 1`, as in Timeline 1) prints a RETRY line whose `--baseline` NS equals the first call's, not the file's current mtime.
- `scripts/test_wait_for.py::case_second_round_does_not_accept_round_one_file` — round 1 goes through timeout (its write landing about 0.5 s before the deadline with `--poll 1`, as in Timeline 1), RETRY, then exit 0. Round 2's fresh command does not exit 0 on round 1's `PLAN_FIXED fixed=1`, and it does exit 0 on round 2's `fixed=2` once that is written.
- `scripts/test_wait_for.py::case_abandoned_wait_redispatch_does_not_accept_late_file` — a timeout that is never retried, followed by a late write, is not accepted by a re-dispatch's fresh command.
- `scripts/test_wait_for.py::case_baseline_not_in_rewritten_exits_2` — `--baseline` for a file that is not `--rewritten` exits 2 immediately with `nothing waits on it`.

### Reuse and scope
reuse: `scripts/wait_for.py:main` (extend the `start_mtime_ns` dict and the inner `why()` reason function), `scripts/wait_for.py:token_present` (reasons 2 and 3), the existing `--rewritten`/`--expect` "not in the wait list" guard pattern for `--baseline`, and the test helpers `run`, `delayed_write`, `delayed_writes`, `MID_EDIT`, `FINISHED_EDIT`, `check` in `scripts/test_wait_for.py`; stdlib `shlex` (`quote` to print, `split` in tests) for the RETRY command.
do not reuse: `start_mtime_ns` as "the file's mtime when this call started" once `--baseline` exists. It becomes "the baseline this dispatch measures against". On a RETRY call the two differ, and the RETRY line must print the baseline, never re-stat the file. Also do not reuse the `still the pre-dispatch copy` reason for a file whose `--expect` token is present: that is exactly the false message from 08:58:13Z.
keep because: the user's task names all three files ("Fix scripts/wait_for.py", "regression tests … runnable with the repo's existing test setup", "update SKILL.md/references where wait_for usage is documented").

### Review axes
- attacker-controlled input: yes — the CLI args and the watched files' contents come from outside the process (an agent writes the files), and the RETRY line echoes args back as a shell command, so quoting matters.
- hot path: no — one blocking call per phase that polls every 5 s; no spec, benchmark or perf test calls it high-volume.
- public surface: yes — it adds a CLI flag (`--baseline`) and a new output line (`RETRY:`) that the coordinator acts on, and it changes the documented exit-2 contract in SKILL.md.

### Verification commands
cwd: `/Users/g.evdokimov/.claude/skills/teamlead`
- `python3 scripts/test_wait_for.py`
- `python3 scripts/test_run_state.py`
- `python3 scripts/test_skill_spec.py`
- `python3 scripts/test_python_floor.py`
- `ruff check .`
- `pyright scripts/wait_for.py scripts/test_wait_for.py`

## Dependency DAG / waves
WS-1 has no dependencies.
- Wave 1: WS-1.

## Decisions taken
- **D1 — the follow-up carries its baseline on the command line (a printed `RETRY:` line plus `--baseline FILE NS`); no sidecar.**
  - Evidence: the task allows "a sidecar … or an explicit dispatch-time flag; planner picks and justifies".
  - Why not a sidecar: a sidecar is cleared only on exit 0/1, and the documented stall path never reaches either. SKILL.md rule 11 reads "two empty chunks → … report a stall to the user". A killed agent or a compaction can also abandon a wait. Each of these leaves the sidecar on disk, so the next dispatch inherits a pre-dispatch baseline and accepts the abandoned agent's late file, which is requirement 2's failure.
  - The command-line baseline cannot outlive the dispatch, because nothing is written.
  - If the coordinator forgets the RETRY line, the result is the old false timeout, now with the requirement-3 message that names the cause. A forgotten retry can never become a stale exit 0.
  - The flag is taught in SKILL.md (rule 11 and 6b), which satisfies "never invent flags the coordinator docs don't teach".
- **D2 — the RETRY line is printed on every exit 2, not only when a baseline exists.** "Run the RETRY line" then becomes the single follow-up rule in SKILL.md. Evidence: SKILL.md rule 11's "call it once more" is the instruction being replaced.
- **D3 — `--baseline` requires the file to be `--rewritten`.** It mirrors the existing guards (`scripts/wait_for.py`, the "is not in the wait list; nothing waits on it" checks for `--rewritten` and `--expect`).
- **D4 — no change to `scripts/run_state.py`.** Its "wait with --rewritten …" messages (`scripts/run_state.py:518`, `:536`, `:555`) describe a dispatch's first call, which stays as it is.
- **D5 — `references/run-directory.md:11` needs no edit.** It only says the coordinator "waits for each phase's files with `scripts/wait_for.py --timeout <s> <files>`" and teaches no exit-2 handling. Exit 2 is documented only in SKILL.md rule 11 and the script docstring (grep for `wait_for` across `references/` and `skills/`).
- **D6 — verification uses the repo's own runner.** CI (`.github/workflows/*.yml`) runs `python3 scripts/test_*.py` and `ruff check .` with ruff 0.0.292. Locally `ruff 0.0.292` and `pyright 1.1.408` are installed, and all four suites plus ruff and pyright are green on HEAD (checked).

## Project forbiddens
From `/Users/g.evdokimov/.claude/CLAUDE.md`:
- "Never weaken linters (no ignore/disable for prettier/eslint/ruff/checkstyle)."
- "Don't touch env vars, tool installs, or configs I've set up. Ask before changing JAVA_HOME, PATH, or any system-level config."
- "Never invent CLI flags — confirm via `--help` first."

From `/Users/g.evdokimov/.claude/rules/python.md` (paths `**/*.py`):
- "**Never use `Any`** — it violates ANN401. Use specific types: `dict[str, str]`, `list[int]`, `Sequence[Path]`, or a concrete class. If a type is genuinely open, model it (`TypeVar`, `Protocol`, a union) rather than erasing it."
- "Never weaken the linter to make types pass: no `# noqa`, no `ruff` ignore sections, no loosening `pyproject.toml`. Fix the annotation instead."

From the repo (`scripts/test_wait_for.py` docstring, `.github/workflows` CI comment): "No pytest dependency — the skill's scripts run with bare python3". Stdlib only (task: "Keep stdlib-only"). The Python floor is 3.9 (`scripts/test_python_floor.py`), so modules keep `from __future__ import annotations`.

## Anti-scope
- No sidecar or state file anywhere (D1).
- No change to exit-code meanings, `ROUTING`, `EARLY`, `routing_line` or `token_present`.
- No change to `scripts/run_state.py`, `references/`, or other skills.
- Do not shorten the size-stability rule (two polls) or add a deadline grace poll. The RETRY line covers the ~2 s miss.
- No pytest, no new dependencies, no CI or lint config edits.
- No push and no PR from the implementer; the coordinator opens the PR.

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
