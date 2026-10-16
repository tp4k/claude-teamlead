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

> 1. **Mutation gate script (Python stdlib, language-agnostic, new `scripts/mutate.py` + test).**
>    - Runs in place in the implementer's worktree, one mutant at a time, after verifier PASS and before any reviewer starts.
>    - For each mutant: apply a text patch, run the brief's test command, then restore with `git checkout -- <file>`. Use a trap, and assert the tree is clean at the end.
>    - Every brief `probe:` must ship as a concrete patch: file plus exact old→new text. The planner writes the intent; the implementer writes the patch.
>    - Generic text ops on changed lines only: delete line; flip `==`/`!=`, `<`/`<=`, `&&`/`||`, `true`/`false`; drop `return`/`await`.
>    - Sampling: generic ops are sampled deterministically by hash(file:line), up to 20 per workstream. The whole gate is time-boxed to 10 min; anything left is reported NOT RUN, never counted as killed.
>    - A mutant that fails to compile or parse counts as `invalid`, not `killed`.
>    - Any survivor means verifier FAIL and a rework brief before any Opus review.

`## Acceptance`: "Each new script has a stdlib-only `test_*.py` sibling. The full plugin test suite is green. Don't weaken linters."

Contract (Decisions D3–D5): `python3 scripts/mutate.py --repo <worktree> --base <sha> --cmd "<test command>" (--commits <sha> [<sha> …] | --files <path> [<path> …]) [--probes <$RUN/probes-ws<N>-r<M>.json>] [--check-cmd "<cmd with {file}>"] [--max-generic 20] [--time-box 600] [--out <$RUN/mutation-ws<N>-r<M>.md>]`. Probes file: JSON list of `{"probe": "<clause>", "file": "<repo-relative>", "old": "<exact text>", "new": "<exact text>"}`. Last stdout line: `MUTATION: PASS|FAIL killed=<n> survived=<n> invalid=<n> unclassified=<n> not_run=<n> not_applied=<n>`. Exit 0 PASS, 1 FAIL, 2 usage error (including neither or both of `--commits` / `--files`), 3 cannot run (dirty tree at start, or restore failed). Stream scope: parallel implementers share one tree, so generic candidates are only the lines this stream changed — with `--commits` (the implementer report's `## Commits` hashes), the HEAD lines that `git blame --porcelain <base>..HEAD -- <file>` attributes to one of the listed commits; with `--files` (the entries of the brief's `scope` fence, a directory entry covering the files beneath it), the lines in `git diff -U0 <base> HEAD -- <paths>`.

### Observable acceptance

In a temp git repo with one source file and a weak test (asserts only that a function returns without error), changing a `<` on a line added since `--base` yields a SURVIVED row, `MUTATION: FAIL survived=1 …` and exit 1; with a test that asserts the boundary value the same run prints `MUTATION: PASS` and exits 0. In both cases `git status --porcelain` is empty afterwards. In the same repo, a second stream's commit that changes a line (in its own file or in a file both streams touched) yields no mutant when its SHA is not in `--commits`, and a file outside `--files` yields none either. `test_mutate.py` fails before the script exists and passes after.

### Test plan

existing: none relevant (`scripts/test_red_freeze.py` shows the temp-git-repo fixture pattern).
new (each new test follows its file's runner convention: a plain `case_*`/`check_*` function registered in that file's `main()`, run as `python3 scripts/test_<name>.py`, no pytest; a NEW test file copies that shape from an existing `scripts/test_*.py`; the `file::test_*` names below are labels, not collected names):
- `scripts/test_mutate.py::test_survivor_fails_gate` — an uncaught mutant is SURVIVED, the summary says FAIL, exit code 1.
- `scripts/test_mutate.py::test_all_killed_passes` — every mutant killed gives PASS and exit 0.
- `scripts/test_mutate.py::test_probe_patch_applied_exactly` — a probe's old→new text is applied verbatim and reported under its clause; an `old` text absent from the file is NOT APPLIED and fails the gate.
- `scripts/test_mutate.py::test_generic_ops_changed_lines_only` — lines unchanged since `--base`, blank lines, comment-only lines and test files (`red_freeze.TEST_PATH`) are never mutated.
- `scripts/test_mutate.py::test_stream_scope_only` — with two streams' commits on one branch, `--commits <stream A hashes>` never mutates a line from stream B's commits, even in a file both changed; `--files <stream A scope>` never mutates a file outside it; neither or both flags exit 2.
- `scripts/test_mutate.py::test_each_op_flips_both_ways` — each listed op is generated in both directions (`==`↔`!=`, `<`↔`<=`, `&&`↔`||`, `true`↔`false`), plus delete line, drop `return`, drop `await`, and no other op.
- `scripts/test_mutate.py::test_sampling_deterministic_and_capped` — two runs select the same mutants in the same order; generic mutants never exceed `--max-generic`, while brief probes are not counted against it.
- `scripts/test_mutate.py::test_time_box_reports_not_run` — mutants left when the time box expires are NOT RUN and are not counted as killed.
- `scripts/test_mutate.py::test_invalid_mutant` — a mutant that breaks parsing (stdlib `compile()` for `.py`, non-zero `--check-cmd` otherwise) is INVALID, neither killed nor survived; a failing mutant of a non-`.py` file run without `--check-cmd` is UNCLASSIFIED — never KILLED, counted in `unclassified=`, and not a gate failure by itself.
- `scripts/test_mutate.py::test_restore_on_signal` — SIGTERM delivered while the test command runs leaves the tree clean (`git status --porcelain` empty).
- `scripts/test_mutate.py::test_dirty_tree_refused` — a dirty tree at start exits 3 and changes no file.
- `scripts/test_mutate.py::test_out_report` — `--out` writes one row per mutant (file, line, op or probe clause, result).
probe: restore after each mutant — restore once at the end, so the second mutant stacks on the first
probe: NOT RUN never counted killed — time-boxed leftovers added to `killed`
probe: invalid not killed — a compile failure counted as `killed`
probe: unclassified not killed — a non-`.py` mutant that fails with no `--check-cmd` counted as `killed`
probe: changed lines only — every line of a changed file is a candidate
probe: this stream's lines only — candidates taken from the whole `<base>..HEAD` diff, so another stream's lines are mutated
probe: deterministic sampling — `random.sample` or set iteration order chooses the mutants
probe: up to 20 per workstream — cap is 21, or brief probes count against the 20
probe: flip `<`/`<=` — `<` matched inside `<=` or `<<`, or only one direction generated
probe: any survivor means FAIL — exit 0 when killed outnumber survived
probe: assert the tree is clean at the end — no final `git status` check
probe: trap — restore only in normal flow, not on SIGTERM/SIGINT

### Reuse and scope

reuse: `scripts/red_freeze.py:TEST_PATH` (test-file pattern) and `scripts/red_freeze.py:git` (git runner raising `GitError`); `scripts/test_red_freeze.py` temp-repo fixture style.
do not reuse: `scripts/red_freeze.py:added_lines` as the changed-line locator — it returns stripped line text per single commit with no line numbers; the gate needs the HEAD line numbers of the lines this stream changed (`git blame --porcelain <base>..HEAD` for `--commits`, `git diff -U0 <base> HEAD -- <paths>` for `--files`).
keep because: `## Decisions` item 1 names the new `scripts/mutate.py` + test.

### Review axes

- `attacker-controlled input: yes — runs a shell command and applies patches read from CLI args and an agent-written JSON file`
- `hot path: no — runs once per round, time-boxed to 10 min`
- `public surface: yes — new CLI and the probes JSON / summary-line formats other roles consume`

### Verification commands

cwd: the WS-1 worktree of `/Users/g.evdokimov/teamlead-retro`
- `python3 scripts/test_mutate.py`
- `ruff check .`
- `bash -c 'f=0; for s in scripts/test_*.py; do python3 "$s" || f=1; done; exit $f'`

## Dependency DAG / waves

WS-1, WS-2, WS-3, WS-4, WS-5, WS-6 → WS-7, WS-8. Wave-1 streams share no file and no manifest (stdlib only); WS-2 and the docs depend on wave 1 only through the contracts in D3, D6, D9–D12, D17.

- Wave 1: WS-1, WS-2, WS-3, WS-4, WS-5, WS-6
- Wave 2: WS-7, WS-8 (disjoint scopes; both start from a tree with wave 1 merged)

## Decisions taken

| id | decision | evidence |
|---|---|---|
| D1 | The verifier runs `mutate.py` after every brief command passes; `MUTATION: FAIL` makes `OUTCOME: FAIL`; report at `$RUN/mutation-ws<N>-r<M>.md`. It runs in the verifier phase while every repository writer is idle, with `--commits` from the implementer report's `## Commits` and `--check-cmd` from the brief's `check:` line when one exists. | spec item 1 "after verifier PASS and before any reviewer starts", "Any survivor means verifier FAIL" |
| D2 | The implementer writes `$RUN/probes-ws<N>-r<M>.json`, one patch per brief `probe:` line; probes run first and do not count against the 20 generic mutants. | spec item 1 "planner writes the intent; the implementer writes the patch"; "generic ops … up to 20" |
| D3 | `mutate.py` CLI, probes JSON and summary line as in WS-1 "Contract"; generic candidates come only from the stream's own changes (`--commits` = the implementer report's `## Commits` hashes, or `--files` = the brief's scope fence), never the whole `<base>..HEAD` range; they skip blank lines, comment-only lines (stripped text starting `#`, `//`, `/*`, `*`, `--`) and test files (`red_freeze.TEST_PATH`). | spec item 1; a deleted comment line would always survive; `skills/delegate/SKILL.md:450` "Parallel implementers share the tree" (plan-triage row 2) |
| D4 | Invalid = stdlib `compile()` fails for `.py`, or `--check-cmd` exits non-zero. A failing mutant of a non-`.py` file with no `--check-cmd` is `unclassified`: reported, never counted `killed`, and not a gate failure by itself. For compiled languages the planner writes a `check: <command with {file}>` line into each brief's Verification commands, and the verifier passes it as `--check-cmd`, so the gate can tell INVALID from KILLED. This run's code is all Python, so its briefs carry no `check:` line. | spec item 1 "language-agnostic", "fails to compile or parse"; plan-triage row 4 |
| D5 | NOT RUN and UNCLASSIFIED rows are reported and do not fail the gate; a probe whose `old` text is absent is NOT APPLIED and fails the gate. | spec item 1 "reported NOT RUN, never counted as killed"; an unapplied probe measures nothing |
| D6 | Codex gate = `review_package.py <run> --out $RUN/codex-gate-package` then `run_codex_review.py <abs PROMPT.md> --artifact-stem codex-gate`; its triage is `$RUN/triage-gate-r<K>.md`; gate rework briefs are `impl-ws<N>-r<M+1>.md` and count against `reworkCap`. | spec item 2; `scripts/run_codex_review.py` `--artifact-stem`; `scripts/review_package.py` `--out` |
| D7 | When Codex can't run, the gate spawns `teamlead:code-reviewer`; `opusCodeReview` default becomes `fallback`. | spec item 2; `agents/code-reviewer.md` already is the codex-review fallback |
| D8 | `codexCodeReview` default becomes `on`; `off` skips the gate. | questions.md Answer 1 "default on; off skips the gate"; spec "Priority"; `scripts/paths.py:51` currently `off` |
| D9 | Triage verdicts: APPROVED, APPROVED_WITH_NOTES, NEEDS_REWORK, NEEDS_DECISION, STOP; return line gains `docs_only=yes|no` and `decisions=<n>`. NEEDS_DECISION rows carry `recommended:`; `next.py` appends the taken choice to `$RUN/decisions-log.md` (scribe copies it to final-report) and routes as NEEDS_REWORK if a rework brief exists, else as APPROVED_WITH_NOTES. | spec items 4, 7; `references/roles/triage.md:77`, `:145` |
| D10 | Docs-only: triage writes `$RUN/briefs/docs-ws<N>-r<M>.md` (exact claim + code evidence per row) instead of an implementer brief; `teamlead:writer` fixes and commits with subject prefix `docs-fix:`; no re-review; next phase is the Codex gate. | spec item 5 |
| D11 | Kickoff: `next.py` prints one baseline verifier spawn per stream at the base SHA, writing `$RUN/baseline-ws<N>.md`; later verifier rounds classify a command that failed the same way there as pre-existing. | spec item 10 |
| D12 | Writer appends deferred rows to `$RUN/deferred-rows.md` mid-run; at close `ledger.py apply $RUN --ledger <repo>/docs/deferred-work.md` inserts them; row id `<basename $RUN>-<n>` (basename starts with the date); hash = SHA-256 as integer; rows inserted sequentially; never staged or committed. | spec items 10, 11; `references/deferred-work-ledger.md` ("Never stage or commit") |
| D13 | `red_freeze.py --run` requires a clean tree, checks out RED detached, restores the original branch/HEAD in `finally` and on signals; `run_red` keeps its signature. Only the verifier runs `--run`, in the verifier phase while every repository writer is idle (D24). | spec item 10; `scripts/red_freeze.py:125` |
| D14 | Fifth plan axis id `failure-modes`, appended last in `PLAN_REVIEW_AXES`, `AXIS_TEXT` and default `codexPlanReviewAxes`. | spec item 6; `scripts/paths.py` `PLAN_REVIEW_AXES` |
| D15 | Only in-code defaults and the seed change; existing user `~/.teamlead/config.json` files are not migrated (this run's `config.json` shows values sourced from one). | user CLAUDE.md "Don't touch … configs I've set up"; `$RUN/config.json` sources |
| D16 | Questions: the planner's `questions.md`, the CONFIRMED design cards and the validator's scope card form the one pre-implementation batch (D20); mid-run the run asks only on halts (STOP, CANNOT_RUN, cap reached, scope-fence block); other calls take the recommendation and go to `decisions-log.md`. | spec item 7 |
| D17 | Coordinator edits are committed with subject prefix `coordinator-fix:`; `next.py` re-verifies (with mutation gate) commits after the last verified SHA before the Codex gate. | spec item 9 |
| D18 | No existing CLI is removed: `run_state.py`, `wait_for.py`, `review_briefs.py` keep their CLIs and exit codes; `next.py` imports from them, and shared logic moves into importable functions only. | `hooks/gate-agent-spawns.py` imports `run_state.spawn_gap`; docs reference these CLIs |
| D19 | Reviewers read `$RUN/mutation-ws<N>-r<M>.md` instead of building `probe-*` clones, and read the verifier report's RED run instead of running `red_freeze.py --run` themselves (D24); clone text leaves `reviewer.md`, `review_briefs.py:TOOLS` and `skills/delegate/SKILL.md` step 9. | spec item 1 last bullet |
| D20 | `plan-validator.md` keeps facts plus its existing non-verdict "Smaller:" scope observation; no design axis is added. Validator pass 1 runs at step 4a, in parallel with the plan design review and before the relay, so its scope card joins the single step-6 batch; its PLAN_NEEDS_FIX findings fold into the one 6b Fix round with the answers, design findings and scope decision. Pass 2 (step 6c) re-checks facts on the fixed plan only when that round returned `new_paths=yes`; it asks nothing, and a `Smaller:` cut it names is logged to `$RUN/decisions-log.md`. `run_state.plan_next` / `spawn_gap`, their tests in `test_run_state.py` and `test_gate_agent_spawns.py`, the `hooks/gate-agent-spawns.py` docstring, `skills/delegate/SKILL.md` steps 4a–6d, `plan-validator.md` and `run-directory.md` follow this order. | spec item 7 "All plan questions are asked in one batch before implementation"; spec item 6; `scripts/run_state.py:609–618`; `scripts/test_run_state.py:287–295`; `references/run-directory.md:39`; plan-triage row 6 |
| D21 | `scripts/test_gate_agent_spawns.py:6,53` fixture slug renamed to a generic one, by WS-2, which owns that file because D20 changes the validator cases it asserts. | `## Acceptance` "No plugin file mentions iap, nsd or Emma"; grep on base |
| D22 | `delegate/SKILL.md` must stay < 500 lines (now 498); `test_skill_spec.py` strings change only where the follow-up contract text legitimately changes. | `scripts/test_skill_spec.py` |
| D23 | `cycle` step 10 stops running a separate `/teamlead:codex-review` when the run's in-loop gate ran; the standalone skill remains for user-picked out-of-scope follow-ups. | spec item 2 "Post-run follow-up runs remain only for rows you pick that are out of scope" |
| D24 | RED-run ownership (design choice "Verifier only"): the implementer runs its targeted tests right after its RED commit, while HEAD is already RED (no checkout), copies each test's failure from that output as its `red:` evidence, and runs `red_freeze.py` without `--run` for the freeze check. The in-place `red_freeze.py --run` checkout happens only in the verifier phase, while every repository writer is idle; the verifier writes the `RED run` block into its report. Reviewers read that result and drop their own RED runs; their read-only freeze check without `--run` stays. `next.py` puts this round's RED hash and the `--run` command into the verifier spawn only. | questions.md Answers `design:` line; plan-triage row 3; `skills/delegate/SKILL.md` step 8a "Keep repository writers idle until every verifier and reviewer finishes." |
| D25 | `reworkCap` counts reworks, not rounds: cap 3 allows rework rounds 2–4, so round 4 is spawned and a NEEDS_REWORK after round 4 halts for the user instead of spawning round 5 — for gate-triggered and ordinary rework alike, as `scripts/run_state.py:285–292` (`rnd > r.cap`) and `scripts/test_run_state.py::case_rework_cap_stops` already do. | spec item 2 "It shares the existing `reworkCap` (3)"; plan-triage row 5 |

## Project forbiddens

- `~/.claude/rules/python.md`: "**Never use `Any`** — it violates ANN401. Use specific types: `dict[str, str]`, `list[int]`, `Sequence[Path]`, or a concrete class. If a type is genuinely open, model it (`TypeVar`, `Protocol`, a union) rather than erasing it."
- `~/.claude/rules/python.md`: "Never weaken the linter to make types pass: no `# noqa`, no `ruff` ignore sections, no loosening `pyproject.toml`. Fix the annotation instead."
- `~/.claude/CLAUDE.md`: "Never weaken linters (no ignore/disable for prettier/eslint/ruff/checkstyle)."
- `~/.claude/CLAUDE.md`: "Targeted tests while iterating; full suite once before calling a multi-file change done. Fix until green — never report partial progress as complete."
- `~/.claude/CLAUDE.md`: "Don't touch env vars, tool installs, or configs I've set up."
- `~/.claude/CLAUDE.md`: "Never invent CLI flags — confirm via `--help` first."
- `scripts/test_python_floor.py` (repo test): code must run on Python 3.9; PEP 604 annotations need `from __future__ import annotations`.
- `/Users/g.evdokimov/teamlead-evals/task-retro-2026-10-14.md`: "Everything must stay generic: no iap/nsd/Emma-specific names, paths or rules in the plugin."

## Anti-scope

- The eval suite and baseline results (spec "Prerequisite, NOT part of this PR's diff"); nothing under `/Users/g.evdokimov/teamlead-evals/` is written or added to the repo.
- The user's `~/.teamlead/config.json`, `~/.claude/` files, env vars and tool installs.
- `hooks/` (except the `hooks/gate-agent-spawns.py` docstring, owned by WS-2), `.github/`, `.claude-plugin/`, `pyrightconfig.json`, and scripts not named in a scope (`archive_reports`, `corpus_ab`, `new_run`, `plugin_copies`, `prune_runs`, `run_codex_review`, `session_title`) — unchanged.
- Removing or renaming existing script CLIs or flags (D18).
- Migrating existing ledger rows or existing user configs (spec item 11 "No migration"; D15).
- Any non-stdlib dependency or new manifest.

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
