===== plan.md (excerpt) =====
# Plan

## Goal

Implement the eleven retro decisions in the teamlead plugin as one PR, so that more defects are caught inside the run and fewer reach human and Codex review: a mutation gate, an in-loop Codex final gate, new review lenses, triage on Opus with NEEDS_DECISION, docs-only rounds, stricter plan checks, batched questions, `when-needed` specialists, a `next.py` router, friction fixes, and hash-positioned ledger rows. Every script, default, role file and README must agree, and the plugin must stay generic.

Spec source for every excerpt: `/Users/g.evdokimov/teamlead-evals/task-retro-2026-10-14.md` (user-provided document). Repo: `/Users/g.evdokimov/teamlead-retro`, branch `analysis/run-retro-2026-10-14`, base `e7c5dcf`. Python stdlib only. CI runs `ruff==0.0.292` and every `scripts/test_*.py` on Python 3.9–3.13 (`.github/workflows/ci.yml`).

## Workstreams

| id | name | complexity | depends on | files/scopes | attacker-controlled input | hot path | public surface |
|---|---|---|---|---|---|---|---|
| WS-1 | Mutation gate script | M | none | `scripts/mutate.py` NEW, `scripts/test_mutate.py` NEW | yes | no | yes |
| WS-2 | next.py router | L | none | `scripts/next.py` NEW, `scripts/test_next.py` NEW, `scripts/run_state.py`, `scripts/test_run_state.py`, `scripts/wait_for.py`, `scripts/test_wait_for.py`, `scripts/review_briefs.py`, `scripts/test_review_briefs.py`, `scripts/test_gate_agent_spawns.py`, `hooks/gate-agent-spawns.py` (docstring) | yes | no | yes |
| WS-3 | Config defaults and fifth plan axis | M | none | `scripts/paths.py`, `scripts/run_config.py`, `scripts/test_run_config.py`, `config.example.json`, `scripts/plan_review_package.py`, `scripts/test_plan_review_package.py` | yes | no | yes |
| WS-4 | Codex final-gate package | M | none | `scripts/review_package.py`, `scripts/test_review_package.py` | yes | no | yes |
| WS-5 | red_freeze in place | S | none | `scripts/red_freeze.py`, `scripts/test_red_freeze.py` | yes | no | yes |
| WS-6 | Ledger insert script | S | none | `scripts/ledger.py` NEW, `scripts/test_ledger.py` NEW | yes | no | yes |
| WS-7 | Role and agent docs | M | WS-1, WS-2, WS-3, WS-4, WS-5, WS-6 | `references/roles/*.md`, `references/deferred-work-ledger.md`, `references/run-directory.md`, `references/review-standard.md`, `agents/*.md` | no | no | yes |
| WS-8 | Skills and README | M | WS-1, WS-2, WS-3, WS-4, WS-5, WS-6 | `skills/delegate/SKILL.md`, `skills/codex-review/SKILL.md`, `skills/cycle/SKILL.md`, `README.md`, `scripts/test_skill_spec.py` | no | no | yes |

## WS-1 — Mutation gate script

Definition: Build `scripts/mutate.py` (NEW) and its stdlib-only sibling `scripts/test_mutate.py` (NEW): the in-place, one-mutant-at-a-time mutation gate the verifier runs after its commands pass, following contract D3–D5 below.

```scope
scripts/mutate.py
scripts/test_mutate.py
```

### Spec excerpt

`/Users/g.evdokimov/teamlead-evals/task-retro-2026-10-14.md`, `## Decisions`, item 1:

> 1. **Mutation gate script (Python 
…[truncated]

===== review-ws1-r3-code.md =====
# Code review — WS-1 — round 3

Verdict: NEEDS_REWORK

Coverage: round-2 rows re-checked. Row 1 (literal pathspec, one entry, path == rel), row 2 (docstring) and row 3 (`.rst`/`.markdown` fixtures) are fixed as specified. Changed production lines `scripts/mutate.py:174-181` were probed: two of the three guard clauses survive, and they are not equivalent (see rows).

## Probes
list: 5 brief + 2 added; off-list clauses: 0; LIST_GAP: 0
Clone `probe-ws1-r3-code` at efd3fa3, baseline `=== 53 passed, 0 failed`. Ad-hoc scenarios are in `probe-ws1-r3-code-tools/probe.py`. Each mutant was restored, and the clone's status is empty.
- literal pathspec alone → drop `"--literal-pathspecs", ` at scripts/mutate.py:174 → SURVIVED (53/53). This is NOT equivalent. Setup: a tracked regular `a*.py` (stream commit) beside a tracked `a!x.py`. The probe on `a*.py` exits 2 instead of applying (exit 1, `SURVIVED a*.py:1 probe=p`). The generic run silently skips the file and reports `MUTATION: PASS killed=0 survived=0` instead of `FAIL survived=2`.
- exactly one entry alone → `if len(entries) != 1:` → `if not entries:` at scripts/mutate.py:178 → SURVIVED (53/53). Equivalent: with literal pathspecs, more than one entry needs a directory (refused by `path != rel`) or unmerged stages (dirty tree, exit 3 first). No row.
- path == rel alone → `if path != rel or info…` → `if info…` at scripts/mutate.py:181 → SURVIVED (53/53). This is NOT equivalent. A probe `file: "sub"`, naming a directory that holds one tracked `sub/a.py`, should be a usage error (exit 2). Under the mutant it is accepted and reported `NOT APPLIED sub` (exit 1). That contradicts the docstring's exit-2 contract added at scripts/mutate.py:46-47.

## Findings
| Sev | Location | Req/Concern | Problem → Fix |
|---|---|---|---|
| LOW | scripts/mutate.py:174 / scripts/test_mutate.py (new case) | Row 1: literal pathspecs in `tracked_regular_file` | Dropping `--literal-pathspecs` survives 53/53. The implementer called it equivalent, which is false: a legitimately tracked regular `a*.py` beside a tracked `a!x.py` gets glob-matched to 2 entries and refused. The probe exits 2, and the generic run silently skips the file and PASSes with 0 mutants. → ADD a case: base tracks `a!x.py`; the stream commit adds a regular `a*.py` with `secret = 1 < 2`. Assert that a probe `{"file": "a*.py", "old": "secret", "new": "public"}` with `--cmd true --max-generic 0` exits 1 with `SURVIVED  a*.py:1` in stdout. Assert that a generic run with `--max-generic 1000` reports `a*.py:1` in stdout. KEEP `case_glob_named_symlink_refused` and `case_glob_named_ignored_file_refused` unchanged. |
| LOW | scripts/mutate.py:181 / scripts/test_mutate.py (new case or `case_untracked_or_linked_targets_refused`) | Row 1: path field must equal `rel`; docstring exit-2 clause | Deleting `path != rel or` survives 53/53. It is not equivalent: a probe whose `file` is a directory holding exactly one tracked file (`sub` containing `sub/a.py`) is accepted and then reported `NOT APPLIED` (exit 1) instead of the documented usage error (exit 2). → ADD a check: base tracks one file; the stream commit adds `sub/a.py` with `secret = 1`. Assert that a probe with `"file": "sub"` exits 2 and `sub/a.py` is unchanged. KEEP every existing assertion in `case_untracked_or_linked_targets_refused`. |

## Notes
- `red_freeze.py --repo … d2237b3` gives `RED_CHANGED — 1 of 21`. The changed line is only the `check(...)` label, shortened for E501 in 618280d, and the assertions are unchanged. This is a Note, not a row. The RED commit itself was not ruff-clean.
- `verifier-ws1-r3.md` again has no RED run block. Per-test RED failures rest on the implementer's `=== 50 passed, 2 failed`.
- `path != rel` now refuses a probe `file` written as `./real.py`, which the glob version used to accept. The brief prescribed this, but `load_probes` could normalise with `PurePosixPath` if implementers write `./` paths.
- Removed test lines in 618280d (the `hit` regex and the label) are superseded by a wider regex and an identical assertion. No coverage was lost.

## Verification
per $RUN/verifier-ws1-r3.md: PASS


===== review-ws1-r3-security.md =====
# Review — WS-1 — round 3 — security

**Verdict:** APPROVED_WITH_NOTES

Tag: `attacker-controlled input: yes — runs a shell command and applies patches read from CLI args and an agent-written JSON file` (validator's final tag). Re-review of the round-2 security row (glob pathspec in `tracked_regular_file`) against d2237b3 18d0c0d 618280d e667106.

## Findings

| Sev | Location | Req/Concern | Problem → Fix |
|---|---|---|---|

## Notes

- Round-2 row closed: scripts/mutate.py:174-182 runs `git -C <repo> --literal-pathspecs ls-files -s -z -- rel`, requires exactly one NUL-separated entry and `path == rel` before the mode check. The `a*.py -> real.py` symlink (beside tracked `a!x.py`) and an ignored `a*.py` are both refused; `case_glob_named_symlink_refused` and `case_glob_named_ignored_file_refused` assert exit 2 / untouched bytes / clean tree.
- Non-canonical spellings (`./real.py`, a directory prefix such as `sub` matching only `sub/x.py`, quoted or non-ASCII names) now fail `path == rel` and are refused: fail-safe, a usage error rather than a mutation.
- Test-only lines: 618280d removes no assertion (the `hit` regex is widened, the `notes.md` clause is kept, one check label is shortened for E501).

## Verification

per $RUN/verifier-ws1-r3.md: PASS (head efd3fa302be61d11acf92e059721d3ea931d2722, tree CLEAN; shared HEAD and empty porcelain status re-checked). No repository edits made.


===== verifier-ws1-r3.md =====
# Verifier — round 3

OUTCOME: PASS

## Snapshot

head: efd3fa302be61d11acf92e059721d3ea931d2722
tree: CLEAN
HEAD and `git status --porcelain=v1 --untracked-files=all` (empty) checked before and after each command. Commits d2237b3 18d0c0d 618280d e667106 are the four commits below HEAD efd3fa3 in `git log`.

## Commands

(Commands taken from impl-ws1-r1.md via the r2/r3 "unchanged" chain; cwd /Users/g.evdokimov/teamlead-retro)
python3 scripts/test_mutate.py → exit 0 (=== 53 passed, 0 failed)
ruff check . → exit 0
bash -c 'f=0; for s in scripts/test_*.py; do python3 "$s" || f=1; done; exit $f' → exit 0 (all suites 0 failed; e.g. 32, 115, 13, 8, 27, 50, 57, 27, 100, 37, 71 passed)

## Pre-existing analysis

none (no failures)

## Flaky

none


===== triage-ws1-r2.md =====
# Triage — round 2

Verdict: NEEDS_REWORK

## Rows
| Sev | Location | Req/Concern (reviewers) | Problem → Fix |
|---|---|---|---|
| MEDIUM | scripts/mutate.py:168, 171 (`tracked_regular_file`) | Round-1 row: accept only tracked mode 100644/100755 targets (security) | Glob pathspec in `git ls-files -s --`, first-entry mode only; committed symlink `a*.py` passes beside tracked `a!x.py`, so `real.py` is modified and left dirty (reproduced). → Literal pathspecs, require exactly one entry whose path equals `rel`; ADD test (probe exits 2, generic run mutates nothing, tree clean). |
| MEDIUM | scripts/mutate.py:16-25, 40-44 (module docstring) | 3a item 4 public surface (code) | Docstring omits new skips (docstring lines, `.md`/`.markdown`/`.rst`, non-tracked paths) and the probe-file usage error. → Edit generic bullet, probes bullet and exit-2 clause; keep rest. |
| LOW | scripts/mutate.py:73 / scripts/test_mutate.py:567-578 | Round-1 row 1 `.markdown`/`.rst` (code) | No fixture exercises `.rst`/`.markdown`; dropping either suffix survives. → Add `guide.rst`, `intro.markdown` to `case_prose_lines_not_mutated` with widened regex and not-hit assertion. |

Full row text is in `briefs/impl-ws1-r3.md`.

## Demoted to Notes
- Skip `.txt` files in generic ops — frozen round-1 fixtures use `.txt` as the non-`.py` extension, so it needs a coordinator ruling plus a RED_CHANGED fixture rename; no WS-2..WS-8 scope names a `.txt` file (scripts/mutate.py `PROSE_SUFFIXES`)
- Make `PROSE_SUFFIXES` case-insensitive (`CHANGELOG.MD`, `README.RST`) — unspecified input variant (scripts/mutate.py:73)
- Use literal pathspecs in `restore()` as well — harmless with a clean pre-run tree; consistency only, and the row-1 fix already closes the reachable hole (scripts/mutate.py:322)

## Notes for the user
- `.txt` is not skipped as prose (frozen round-1 fixtures depend on it); skipping it needs a ruling and a fixture rename.
- `PROSE_SUFFIXES` is case-sensitive.
- `restore()` passes the path as a glob pathspec; harmless on a clean tree.
- `verifier-ws1-r2.md` has no RED run block; per-test RED failures rest on the implementer's `=== 42 passed, 6 failed`.
- Code reviewer's mutation probes were all NOT PROBED (permission system refused edits in the clone `probe-ws1-r2-code`); the docstring-detection, SIG_IGN rerun, `one_line(m.label)` and `report_leftover` clauses rest on reading, not executed mutants.
- Self-gate's remaining survivor (`--base required=True` -> `False`, scripts/mutate.py:448) looks equivalent (a `None` base fails `resolve_commit` with exit 2); the verifier needs a ruling before the gate runs on WS-1 itself.
- Carried from round 1: fail-open shapes (hanging test command, zero mutants), `===`/`!==` not flipped, uncaught `GitError` from `status_porcelain`, double-quoted `{file}`, SIGHUP/restore signal gap (see triage-ws1-r1.md).

## Re-review set
code: re-run — always
security: re-run — it raised a finding and the fix changes production behavior on its axis (path validation)
perf: carried — not dispatched in rounds 1 and 2 (hot path: no, see /Users/g.evdokimov/.teamlead/runs/teamlead-retro/2026-10-14-1103-retro-fixes/briefs/review-ws1-r2-perf.skip); no verdict on record to carry

## Rework count
2
