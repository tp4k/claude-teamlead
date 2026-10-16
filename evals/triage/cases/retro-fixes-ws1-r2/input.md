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

===== review-ws1-r2-code.md =====
# Review — WS-1 Mutation gate script — round 2 — code

**Verdict:** NEEDS_REWORK

**Coverage:** I checked the 10 triage rows from `triage-ws1-r1.md` against 7e93f10, 570f8b0 and ea1cd68 (production diff, the RED and test-only diffs, and removed lines), TDD, and 3a for the changed public surface. Snapshot: verifier `head:` ed0a968f matches the shared HEAD, `tree: CLEAN`, and `git status` is empty. All 10 rows are addressed in code and tests. Row 1 drops `.txt`, and the implementer reported this; see Notes. The failures are rows 1–2 below. Freeze: `red_freeze.py --repo … 776036c 7e93f10` → `RED_CHANGED — 1 of 564`. The one missing line is the round-1 `LIB_BASE` fixture fix, which was already accepted. The only test line removed in 7e93f10 is the `case_interrupt_exit_code` `cmd`, which was replaced by the authorized pid-file command. Every assertion was kept.

## Probes

list: 0 brief + 0 added; off-list clauses: 0; LIST_GAP: 0

- every production probe → NOT PROBED. The permission system refused the mutation edit in the disposable clone `probe-ws1-r2-code` (checked out at ed0a968, baseline `=== 50 passed, 0 failed`). It refused a plain `sed -i` on `scripts/mutate.py` and the combined edit+run as well. I did not work around the refusal. `cmp` against the saved original shows the clone file is unmodified. These were planned: `only_strings = False` → `pass` at scripts/mutate.py:161, docstring `range(first, tok.start[0] + 1)` narrowed to its first line at :155, a rerun of `signal.signal(sig, signal.SIG_IGN)` → `pass` at :465, a rerun of `one_line(m.label)` → `m.label` at :422, and removal of `report_leftover(repo)` at :517. Row 2 rests on fixture reading (grep), not on an executed mutant.

## Findings

| Sev | Location | Req/Concern | Problem → Fix |
|---|---|---|---|
| MEDIUM | scripts/mutate.py:21-25, 40-44 (module docstring) | 3a item 4: public surface `yes`. The CLI and probes-JSON contract are documented in the module docstring | **Problem:** 570f8b0 added three new behaviors, and the docstring that documents the skip list and exit codes is now stale. (a) Generic ops now also skip bare-string (docstring) lines in `.py` files and whole `.md`/`.markdown`/`.rst` files (:255, :262, :269). (b) Generic candidates that are not tracked regular files inside the repo are now skipped (:258). (c) A probe whose `file` is not a tracked mode 100644/100755 file resolving inside the repo is now a usage error, exit 2 (:297-299). The docstring still says only "Blank lines, comment-only lines and test files are skipped", and its exit-2 clause names only the `--commits`/`--files` case. The implementers who write `--probes` JSON and the verifier read this text. **Fix:** EDIT the generic bullet (:21-25) to list the added skips: bare-string/docstring lines in `.py` files, files ending `.md`/`.markdown`/`.rst`, and paths that are not tracked regular files inside the repo. ADD to the probes bullet (:16-20) that `file` must be a tracked regular file (not a symlink, not untracked or ignored) inside the repo, or the run is a usage error. EXTEND the exit-2 clause (:42) with "or a probe file that is not a tracked regular file". KEEP every other docstring sentence unchanged. |
| LOW | scripts/mutate.py:73 / scripts/test_mutate.py:567-578 | Triage row 1: skip files with suffix `.markdown` and `.rst` (code) | **Problem:** `PROSE_SUFFIXES = (".md",)` would also pass. `case_prose_lines_not_mutated` uses only `notes.md`, and no fixture in `scripts/test_mutate.py` has a `.rst` or `.markdown` path (grep finds none). Dropping either suffix therefore survives the suite. **Fix:** ADD to `case_prose_lines_not_mutated` two files in the same stream commit, `guide.rst` and `intro.markdown`, each with a line holding a generic op (for example `read more == here`). WIDEN the `hit` regex to `(\S+\.(?:py|md|rst|markdown)):(\d+)` and ADD `not any(f in ("guide.rst", "intro.markdown") for f, _ in hit)`. KEEP the `("doc.py", 4) in hit`, `doc.py n <= 3` and `notes.md` assertions. |

## Notes

- Row 1 deviation: `.txt` is not skipped. The frozen round-1 fixtures (`ops.txt`, `m.txt`) use `.txt` as the language-agnostic non-`.py` extension, so skipping it fails 10 frozen checks. No WS-2…WS-8 scope in `plan.md` names a `.txt` file, so nothing in this run is affected. Skipping `.txt` needs a coordinator ruling plus a RED_CHANGED fixture rename (for example `.txt` → `.cfg`).
- `tracked_regular_file` (scripts/mutate.py:166-178) passes `rel` to `git ls-files -s --` as a pathspec, not as a literal path. `pkg` or `lib.p?` matches tracked entries, and `entry[0]` is the mode of the first match. Today `evaluate`'s `is_file()` turns a directory or glob into NOT APPLIED. An ignored file literally named `note*.txt` next to a tracked `notes.txt` would pass, though. `GIT_LITERAL_PATHSPECS=1`, or comparing the listed path to `rel`, would close this.
- `PROSE_SUFFIXES` is case-sensitive, so `CHANGELOG.MD` or `README.RST` is still mutated.
- `verifier-ws1-r2.md` has no RED run block (settled decision 3 has reviewers read it). The per-test RED failures rest on the implementer's `--run` result: `=== 42 passed, 6 failed`.
- The self-gate's remaining survivor (`--base required=True` → `False` at :448) does look equivalent: a `None` base fails `resolve_commit` with exit 2. The verifier needs a ruling before the gate runs on WS-1 itself.

## Verification

per $RUN/verifier-ws1-r2.md: PASS. Code-axis runs: `red_freeze.py --repo /Users/g.evdokimov/teamlead-retro 776036c 7e93f10` → `RED_CHANGED — 1 of 564` (the accepted `LIB_BASE` line). Mutation probes were refused by the permission system (see Probes).


===== review-ws1-r2-security.md =====
# Review — WS-1 — round 2 — security

**Verdict:** NEEDS_REWORK

Tag: `attacker-controlled input: yes — runs a shell command and applies patches read from CLI args and an agent-written JSON file` (validator's final tag). Re-review of round-1 rows (symlink/untracked targets; forged `MUTATION:` label) against 7e93f10 570f8b0 ea1cd68.

## Findings

| Sev | Location | Req/Concern | Problem → Fix |
|---|---|---|---|
| MEDIUM | scripts/mutate.py:168, 171 | Round-1 row: accept a target only if `git ls-files -s -- <file>` shows it tracked with mode `100644`/`100755` (not `120000`); every mutant restored by `git checkout` | `rel` is passed to `ls-files` as a glob pathspec, and only `entry[0]` (the first matching line's mode) is checked. A committed in-repo symlink whose name holds a glob character passes whenever a regular tracked file sorting before it also matches. Reproduced at ed0a968 (`$RUN/probe-ws1-r2-security/repro.py`): tracked `real.py` (`SECRET = 1`), tracked regular `a!x.py`, committed symlink `a*.py -> real.py`; `ls-files -s -- 'a*.py'` lists `100644 … a!x.py` first. (1) probe `{"file":"a*.py","old":"SECRET = 1","new":"SECRET = 666"}` → accepted, `real.py` left `SECRET = 666`, exit 3, ` M real.py`; (2) generic `--commits <stream>` → `SURVIVED a*.py:1 op=delete-line`, `real.py` left emptied, exit 3. Containment still blocks outside-repo targets (resolve follows the link), so this is the round-1 in-repo alias case (2) reopened. → In `tracked_regular_file` run the lookup with literal pathspecs (`git(repo, "--literal-pathspecs", "ls-files", "-s", "-z", "--", rel)` or the `:(literal)` prefix) and require exactly one entry whose path field equals `rel` before checking its mode. ADD to `scripts/test_mutate.py` a case: base commit tracks `real.py` and `a!x.py`; a stream commit adds symlink `a*.py -> real.py`; (a) a probe on `a*.py` exits 2 and `real.py` bytes are unchanged; (b) a generic `--commits` run mutates nothing reachable through `a*.py`, leaves `repo.status() == ""` and `real.py` unchanged. KEEP `case_untracked_or_linked_targets_refused`, `case_in_repo_symlink_alias_refused` and the absolute/`..` rejection unchanged. |

## Notes

- The forged-label row is fixed: `describe()` flattens `\r`/`\n` in label and file (scripts/mutate.py `one_line`), and the consumer `next.py:98` uses `re.M` `^`, which breaks only on `\n`, so other Unicode line separators cannot forge a line there.
- `restore()` (scripts/mutate.py:322) also passes the path as a glob pathspec; with a clean pre-run tree this only re-checks out extra files, harmless. Using literal pathspecs there too would keep both sides consistent.
- Test-only rework: the one removed line (7e93f10, `case_interrupt_exit_code` command) is replaced by the stronger pid-file variant; no assertion lost.

## Verification

per $RUN/verifier-ws1-r2.md: PASS (head ed0a968f5336d047851803de835d587313bc3442, tree CLEAN). Reproduction ran on a copy of `scripts/mutate.py` + `scripts/red_freeze.py` at ed0a968 against throwaway repos under `$RUN/probe-ws1-r2-security/`; the shared repository was not modified.


===== verifier-ws1-r2.md =====
# Verifier — round 2

OUTCOME: PASS

## Snapshot

head: ed0a968f5336d047851803de835d587313bc3442
tree: CLEAN
Commits 7e93f10, 570f8b0, ea1cd68 are all in HEAD history. HEAD and `git status --porcelain=v1 --untracked-files=all` were checked before and after the commands: HEAD unchanged, status empty.

## Commands

cwd: /Users/g.evdokimov/teamlead-retro
python3 scripts/test_mutate.py → exit 0 (=== 50 passed, 0 failed)
ruff check . → exit 0
bash -c 'f=0; for s in scripts/test_*.py; do python3 "$s" || f=1; done; exit $f' → exit 0 (17 suites, every summary "N passed, 0 failed"; ran past the foreground limit as a background task)

## Pre-existing analysis

none (no failures)

## Flaky

none


===== triage-ws1-r1.md =====
# Triage — round 1

Verdict: NEEDS_REWORK

## Rows
| Sev | Location | Req/Concern (reviewers) | Problem → Fix |
|---|---|---|---|
| HIGH | scripts/mutate.py:123-135, 224 | Spec item 1 "Any survivor means verifier FAIL" + D1 + D3 skip list (code) | Generic ops mutate prose lines (docstrings, `.md`/`.rst`/`.txt`) that no test can kill; the gate FAILs on WS-1's own commits. → Skip prose files and `tokenize`-detected docstring lines in `generic_mutants`; ADD `case_prose_lines_not_mutated`. |
| MEDIUM | scripts/mutate.py:248-253, 214-216, 323-337, 272-276 | Probe `file` repo-relative (D3/D5); restore via `git checkout` (security) | Symlinked and ignored/untracked targets are written but cannot be restored. → Accept only tracked, mode 100644/100755, resolved-inside-repo targets; usage error (exit 2) for probes, skip for generic; ADD three tests. |
| MEDIUM | scripts/mutate.py:337, 410-411, 432-451 | Spec "Use a trap" (code; security Note) | Second SIGTERM during `restore` leaves the mutant in place, exit 3. → Ignore SIGTERM/SIGINT in `on_signal`, final status check on the `Terminated` path; ADD double-SIGTERM check. |
| MEDIUM | scripts/mutate.py:353 | `--check-cmd` non-zero is INVALID (code, LIST_GAP) | `!=`→`==` survives. → Assert row-level INVALID/KILLED. |
| MEDIUM | scripts/mutate.py:186 | `--files` changed lines only (code, LIST_GAP) | `count = 1` survives. → Assert `(file, line)` hits for the `--files` run. |
| MEDIUM | scripts/mutate.py:294-295 | Trap kills the test command's process group (code, LIST_GAP) | Removing `kill_group` survives. → Late-marker / pid check in `case_interrupt_exit_code`. |
| LOW | scripts/mutate.py:152 | Deleted files in `--commits` (code, LIST_GAP) | `--diff-filter=d` removal survives. → ADD deleted-file case. |
| LOW | scripts/mutate.py:286-288 | Test output off gate stdout (code, LIST_GAP) | DEVNULL line removal survives. → ADD NOISE check. |
| LOW | scripts/mutate.py:260, 285 | `old` replaced once; no `__pycache__` (code, 2 LIST_GAP) | Replace-all and env mutants survive. → ADD double-occurrence probe and no-bytecode-env run. |
| LOW | scripts/mutate.py:365-369, 438, 442 | Last stdout line is the summary (security) | Probe label forges a `MUTATION:` line. → Sanitise `\r`/`\n` in `describe()`; ADD case. |

Full row text (exact fixes, KEEP clauses) is in `briefs/impl-ws1-r2.md`.

## Demoted to Notes
- Fail-closed handling of a hanging test command (a hung mutant uses the whole time box, later mutants are NOT RUN and the gate PASSes) — an unspecified failure mode, a spec decision for the user (scripts/mutate.py time-box loop)
- Failing on zero mutants (a `--files` typo or a `--commits` SHA outside `base..HEAD` prints `MUTATION: PASS killed=0`) — the spec does not say zero mutants must fail (scripts/mutate.py candidate selection)
- Flipping `===`/`!==` for JS/TS — unspecified operator coverage, would grow D3 (scripts/mutate.py `OPS`)
- Catching `GitError` from `status_porcelain` (exit 3 instead of traceback) and merging the identical `except GitError`/`except UsageError` arms — hardening and cleanup beyond the spec (scripts/mutate.py:423-428, 452)
- Documenting "do not quote `{file}`" in `--check-cmd` help (a double-quoted template re-exposes `$(...)`) — extra argument hardening; the check command is planner-written (scripts/mutate.py `--check-cmd`)
- Trapping SIGHUP and restoring from in-memory original bytes on `Terminated` — beyond the spec's trap requirement; the main window is covered by the signal row (scripts/mutate.py:336-337)

## Notes for the user
- RED_CHANGED `LIB_BASE` (776036c → 6b1ef1a): a fixture correction, not a weakened assertion (code: accept).
- `verifier-ws1-r1.md` has no RED run block, so the per-test RED failure rests on the implementer's `0 passed, 29 failed`.
- Fail-open shapes need a ruling: a hanging mutant exhausts the time box so later mutants are NOT RUN and the gate PASSes; zero mutants from a typo or out-of-range SHA prints `MUTATION: PASS killed=0`.
- `===`/`!==` are never flipped, so a "language-agnostic" gate skips strict equality; worth a ruling.
- An uncaught `GitError` from `status_porcelain` (scripts/mutate.py:452) gives a traceback and exit 1 (reads as FAIL) instead of 3; the two identical except arms at :423-428 could merge.
- A template that wraps `{file}` in double quotes re-exposes `$(...)` despite `shlex.quote`; documenting it would close it.
- A signal during `restore()` aborts it and SIGHUP is not trapped; restoring from in-memory bytes would cover both.
- `--cmd` runs with `shell=True` by design (planner-written test command); no new trust boundary.

## Re-review set
code: re-run — always
security: re-run — it raised a finding and the fixes change production behavior on its axis (path validation, `describe()` output)
perf: carried — not dispatched in round 1 (hot path: no, see /Users/g.evdokimov/.teamlead/runs/teamlead-retro/2026-10-14-1103-retro-fixes/briefs/review-ws1-r1-perf.skip); no verdict on record to carry

## Rework count
1
