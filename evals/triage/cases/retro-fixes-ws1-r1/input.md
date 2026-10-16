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

===== review-ws1-r1-code.md =====
# Review — WS-1 Mutation gate script — round 1 — code

**Verdict:** NEEDS_REWORK

**Coverage:** I checked spec item 1, contract D1–D5, the observable acceptance, the 12 `new:` tests, TDD, the reuse list, file scope and public surface 3a. Snapshot: `head:` 643e4229 matches the shared HEAD, and the tree is clean. Failures are rows 1–8. The decisive check was running the gate on WS-1's own six commits (`--base e7c5dcf --cmd "python3 scripts/test_mutate.py" --commits e6f72bb 776036c 6b1ef1a 171fe82 4a6fe7e e8e6314`, default cap and time box). It printed `MUTATION: FAIL killed=13 survived=3 invalid=4 unclassified=0 not_run=0 not_applied=0` with exit 1. The survivors were at `scripts/mutate.py:43` (docstring delete-line), `:353` (ne->eq) and `:287` (delete-line). The tree was clean afterwards.

## Probes

list: 12 brief + 8 added; off-list clauses: 9; LIST_GAP: 6

- rerun: flip `<`/`<=` → `(?<!<)<(?![<=])` → `<(?![<])` at scripts/mutate.py:90 → killed by scripts/test_mutate.py::case_each_op_flips_both_ways
- rerun: up to 20 per workstream → `keyed[:max(cap, 0)]` → `+ 1` at scripts/mutate.py:231 → killed by scripts/test_mutate.py::case_sampling_deterministic_and_capped
- `--check-cmd` non-zero is INVALID (added clause) → `if code != 0:` → `if code == 0:` at scripts/mutate.py:353 → SURVIVED (also SURVIVED in the self-gate run)
- changed lines only, `--files` arm [off-list] → `count = 1 if m.group(2) is None else int(m.group(2))` → `count = 1` at scripts/mutate.py:186 → SURVIVED
- deleted files skipped in `--commits` mode [off-list] → `"--diff-filter=d"` removed at scripts/mutate.py:152 → SURVIVED
- trap kills the test command's process group on a signal [off-list] → `kill_group(proc)` removed from the `except BaseException` arm at scripts/mutate.py:294–295 → SURVIVED
- test command output kept off the gate's stdout [off-list] → delete-line at scripts/mutate.py:287 (`stdin=…DEVNULL, stdout=…DEVNULL,`) → SURVIVED (self-gate run)
- no `__pycache__` written by test runs [off-list] → `env = dict(os.environ)` at scripts/mutate.py:285 → SURVIVED
- a probe's `old` is replaced once [off-list] → `text.replace(m.old, m.new)` (all occurrences) at scripts/mutate.py:260 → SURVIVED
- probe row line number [off-list] → `count("\n") + 1` → `count("\n")` at scripts/mutate.py:317 → killed by scripts/test_mutate.py::case_out_report
- generic replacement keeps the line ending [off-list] → `text + ending` → `text` at scripts/mutate.py:227 → killed by scripts/test_mutate.py::case_each_op_flips_both_ways
- unkillable prose lines [off-list] → delete-line at scripts/mutate.py:43 (docstring) → SURVIVED (self-gate run, and reproduced as a direct probe)
- trap, second signal (scenario, not a mutation) → two SIGTERMs 5 ms apart while the test command runs → 20/20 runs exit 3 with `M a.py`, and the mutant `return n <= 3` is left in the source file. At 10 ms: clean tree, but exit -15 (signal death) in 20/20 runs.

## Findings

| Sev | Location | Req/Concern | Problem → Fix |
|---|---|---|---|
| HIGH | scripts/mutate.py:123-135, 224 | Spec "Any survivor means verifier FAIL" + D1 (gate runs on every stream) | **Problem:** Generic ops also mutate prose lines: docstrings, string-only lines, and `.md`/`.rst`/`.txt` lines. No test can kill a mutant there. Running the gate on WS-1's own commits FAILs on a deleted docstring line (`SURVIVED scripts/mutate.py:43 op=delete-line`). Streams that only touch docs, such as WS-7 and WS-8 in this run, would FAIL on nearly every sampled mutant. The cause is a gap in D3's skip list, not an implementer guess, so **get a coordinator/user ruling before coding.** **Proposed fix:** ADD to `generic_mutants` (1) a skip for files with suffix `.md`, `.markdown`, `.rst` or `.txt`, and (2) for `.py` files, a skip for lines that the stdlib `tokenize` marks as part of a STRING token forming a whole expression statement (docstrings). ADD `case_prose_lines_not_mutated`: a stream commit adds a module docstring line and a `notes.md` line, both pass `--cmd true`, and the case asserts that neither appears in stdout. KEEP every assertion in `case_generic_ops_changed_lines_only`. |
| MEDIUM | scripts/mutate.py:337, 410-411, 432-451 | Spec "Use a trap" — brief probe "trap" | **Problem:** A second SIGTERM that arrives while `restore` runs raises `Terminated` inside `git checkout`. The mutant stays in the source file and the exit code is 3 (20/20 runs at a 5 ms gap; see Probes). A signal after the handlers are restored kills the process with -15 instead of exit 3. **Fix:** Make `on_signal` set SIGTERM and SIGINT to `SIG_IGN` before it raises `Terminated`, so restore cannot be interrupted. On the `Terminated` path, run the final `status_porcelain` check and print any leftover. ADD a check to `case_restore_on_signal` that sends SIGTERM twice 5 ms apart after the marker appears and asserts `repo.status() == ""`, original `lib.py` bytes, and `returncode == 3`. KEEP its existing single-signal checks for SIGTERM and SIGINT. |
| MEDIUM | scripts/mutate.py:353 / scripts/test_mutate.py:386-392 | Added clause "`--check-cmd` non-zero is INVALID" | **Problem:** The `!=`→`==` mutant survives. With `test -s {file}`, delete-line becomes KILLED and `a != b` becomes INVALID, and the counts are still invalid=1 killed=1. **Fix:** ADD to that check an assertion on the rows: the `delete-line` row for `m.txt:1` is `INVALID` and the `eq->ne` row is `KILLED` (regex on `out`). KEEP the three count assertions. |
| MEDIUM | scripts/mutate.py:186 / scripts/test_mutate.py:279-283 | Brief probe "changed lines only", `--files` arm | **Problem:** With `count = 1`, only the first line of each multi-line hunk is a candidate, and the mutant survives. The `--files` check compares file names only. **Fix:** ADD to `case_stream_scope_only`, after the `--files` run, `assert ("a.py", 2) in hit_files` and `("pkg/deep.py", 2) in hit_files`, using the `(file, line)` set built from `out` the same way as the `--commits` run. KEEP `files == {"a.py", "pkg/deep.py"}`. |
| MEDIUM | scripts/mutate.py:294-295 | Brief probe "trap" (the test command runs with `start_new_session=True`) | **Problem:** If `kill_group` is removed from the `BaseException` arm, the test still passes. Because the child is in its own session, a Ctrl-C or TERM sent to the gate never reaches it. Without this kill, the test command keeps running in the shared worktree after the gate exits 3. **Fix:** ADD to `case_interrupt_exit_code` a test command `touch <marker>; sleep 30; touch <late>`, send the signal, wait 2 s after exit and assert `<late>` does not exist. Alternatively, write `$$` to a file and assert `os.kill(pid, 0)` raises `ProcessLookupError`. KEEP the `returncode == 3` assertion. |
| LOW | scripts/mutate.py:152 | Deleted files in `--commits` mode [off-list] | **Problem:** Removing `--diff-filter=d` survives because no fixture deletes a file. A stream that deletes a file would then hit `git blame` on a missing path and exit 2. **Fix:** ADD a new case: the base commit also adds `gone.py`, and a stream commit deletes `gone.py` and appends a line to `lib.py`. Run `--commits <that sha> --cmd true` and assert exit 0, that the `MUTATION: PASS` line is present, and that `lib.py` was mutated. KEEP the existing assertions. |
| LOW | scripts/mutate.py:286-288 | Rows and summary on stdout [off-list] | **Problem:** Deleting the `stdin/stdout=DEVNULL` line survives the self-gate run, so the test command's output would mix into the gate's stdout. **Fix:** ADD a check with `--cmd "echo NOISE; false"` on `repo.stream()` that asserts `"NOISE" not in out`. KEEP the summary-line assertions. |
| LOW | scripts/mutate.py:260, 285 | Docstring "`old` is replaced once" and implementer item 6 (no `__pycache__`) [off-list] | **Problem:** The replace-all mutant survives (no probe `old` occurs twice). The `PYTHONDONTWRITEBYTECODE` mutant also survives, because the test's own `ENV` already sets it. **Fix:** ADD (a) a probe whose `old` occurs twice in `ops.txt`, asserting that the snapshot changes only the first occurrence; (b) a run of `mutate()` with an env lacking `PYTHONDONTWRITEBYTECODE`, `--cmd "python3 tests/test_lib.py"`, on a repo with no `.gitignore`, asserting exit 0/1 (not 3) and `repo.status() == ""`. KEEP the existing checks. |

## Notes

- RED_CHANGED `LIB_BASE` (776036c → 6b1ef1a): this is a fixture correction, not a weakened assertion. With the old `def base()` body, deleting `def below` still parses, so `invalid == 2` was wrong. Accept it. There is no RED run block in `verifier-ws1-r1.md`, so the per-test RED failure rests only on the implementer's `0 passed, 29 failed`.
- Fail-open shapes to put to the coordinator; the spec does not decide them. A mutant that hangs the test command uses up the whole time box, so every later mutant is NOT RUN and the gate PASSes. A `--files` typo, or a `--commits` SHA outside `base..HEAD`, yields zero mutants and `MUTATION: PASS killed=0 …`.
- `===`/`!==` (JS/TS) are deliberately never flipped (`OPS` lookarounds), so a "language-agnostic" gate skips strict equality. This is worth a ruling.
- A `GitError` from `status_porcelain` at scripts/mutate.py:452 is uncaught, which gives a traceback and exit 1 (looks like FAIL) instead of 3. The `except GitError` and `except UsageError` arms at :423-428 have identical bodies and could be merged.

## Verification

per $RUN/verifier-ws1-r1.md: PASS. Code-axis runs (clones at 643e4229): `python3 scripts/mutate.py … --commits <WS-1 commits>` → exit 1, `MUTATION: FAIL … survived=3` (rows 1, 3, 7). `red_freeze.py --repo … 776036c` → `RED_CHANGED — 1 of 425` (see Notes).

===== review-ws1-r1-security.md =====
# Review — WS-1 — round 1 — security

**Verdict:** NEEDS_REWORK

Tag: `attacker-controlled input: yes — runs a shell command and applies patches read from CLI args and an agent-written JSON file` (validator's final tag; full review).

## Findings

| Sev | Location | Req/Concern | Problem → Fix |
|---|---|---|---|
| MEDIUM | scripts/mutate.py:248-253, 214-216, 323-337, 272-276 | Probe `file` must be repo-relative (contract D3/D5); every mutant must be restored by `git checkout -- <file>` | The only containment check is `is_absolute()` / `..` on the probe path. Writes go through `Path(repo)/file` with `write_bytes`, which follows symlinks and accepts untracked/ignored files, while restore is `git checkout -- <file>`, which cannot undo either. Reproduced at 643e422 (`$RUN/probe-ws1-r1-security/repro.sh`): (1) committed symlink `link.txt -> ../outside/victim.txt` + probe on `link.txt` → `outside/victim.txt` left as `SECRET = 666`, status clean, **exit 0 `MUTATION: PASS`**; (2) in-repo symlink `alias.txt -> real.txt` → `real.txt` left mutated, exit 3, nothing restores it; (3) probe on a gitignored `ignored.cfg` → restore fails, file left `IGN = 666` permanently (no git copy exists), status clean. The generic path has the same hole: `changed_files` keeps a committed symlink and `target.is_file()` follows it. → Before any write, accept a target only if `git ls-files -s -- <file>` shows it tracked with mode `100644` or `100755` (not `120000`) and `Path(repo, file).resolve()` lies under `Path(repo).resolve()` and outside `.git/`. A probe failing this is a usage error in `load_probes` (exit 2, no file touched); a generic candidate failing it is skipped in `generic_mutants`. ADD to `scripts/test_mutate.py` a case: a committed symlink to a file outside the repo + a probe on it exits 2 and the outside file's bytes are unchanged; an ignored-file probe exits 2 and the file is unchanged; a generic run whose only changed path is a symlink mutates nothing outside the repo. KEEP the existing absolute/`..` rejection and every existing assertion. |
| LOW | scripts/mutate.py:365-369, 438, 442 | Last stdout line is the `MUTATION:` summary (contract) | `describe()` prints the agent-written probe label raw; a label containing `\nMUTATION: PASS killed=9 …` prints a fake summary line. When a later mutant aborts the run (exit 3, no real summary), the forged line is the last stdout line. Reproduced (repro.sh case 4): exit 3, last stdout line `MUTATION: PASS killed=9 survived=0 …`. → In `describe()`, replace `\r` and `\n` in `m.label` (and `m.file`) with a space, as `write_report` already does for the label. ADD a case: a probe whose label contains `\nMUTATION: PASS` prints no stdout line starting with `MUTATION:` other than the real summary. KEEP the `--out` sanitising. |

## Notes

- `--check-cmd` quotes `{file}` with `shlex.quote`; a template that wraps `{file}` in double quotes (`"{file}"`) re-exposes `$(...)` in a committed file name. Documenting "do not quote `{file}`" in the help text would close it.
- A signal delivered while `restore()` itself runs (inside the `finally` at mutate.py:336-337) aborts the restore and exits 3 with the file still mutated; the final status check is skipped on that path. SIGHUP is not trapped. Narrow windows; restoring from the in-memory `original` bytes on `Terminated` would cover both.
- `--cmd` runs with `shell=True` by design (brief's test command, written by the planner); no new trust boundary beyond the brief.
- `red_freeze.py` at HEAD: `RED_CHANGED — 1 of 425` (`LIB_BASE` fixture constant, 6b1ef1a) — code-axis ruling, not a security defect.

## Verification

per $RUN/verifier-ws1-r1.md: PASS (head 643e4229ec9a23c3ed46080d9e13b3593832bccf, tree CLEAN). Exploit reproductions ran against a detached clone of that SHA and a throwaway repo under `$RUN/probe-ws1-r1-security/`; the shared repository was not modified.


===== verifier-ws1-r1.md =====
# Verifier — round 1

OUTCOME: PASS

## Snapshot

head: 643e4229ec9a23c3ed46080d9e13b3593832bccf
tree: CLEAN
HEAD and `git status --porcelain=v1 --untracked-files=all` checked before and after the commands: HEAD unchanged, status empty. All six implementer commits (e6f72bb 776036c 6b1ef1a 171fe82 4a6fe7e e8e6314) are in the history of HEAD.

## Commands

python3 scripts/test_mutate.py → exit 0 (=== 34 passed, 0 failed)
ruff check . → exit 0
bash -c 'f=0; for s in scripts/test_*.py; do python3 "$s" || f=1; done; exit $f' → exit 0 (every suite 0 failed, including test_run_state.py: 91 passed, 0 failed)

## Pre-existing analysis

none (no failures)

## Flaky

none
