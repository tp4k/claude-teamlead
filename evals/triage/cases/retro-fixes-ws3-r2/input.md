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

## WS-3 — Config defaults and fifth plan axis

Definition: Change the in-code defaults in `scripts/paths.py` (`codexPlanReview` `always`, `securityReview`/`perfReview` `when-needed`, `codexCodeReview` `on`, `opusCodeReview` `fallback`), stop `run_config.py` seeding security/perf `on`, add the fifth plan-review axis `failure-modes` to `paths.PLAN_REVIEW_AXES` and `plan_review_package.py:AXIS_TEXT`, and mirror all of it in `config.example.json` (D7, D8, D14, D15).

```scope
scripts/paths.py
scripts/run_config.py
scripts/test_run_config.py
config.example.json
scripts/plan_review_package.py
scripts/test_plan_review_package.py
```

### Spec excerpt

`/Users/g.evdokimov/teamlead-evals/task-retro-2026-10-14.md`, `## Decisions`:

> 6. **Plan checks.**
>    - Codex plan review gains a fifth axis, failure modes and semantics: restart, cold start, abort, retry, degraded dependency, and what each metric counts.
>    - `codexPlanReview` defaults to `always`.
>    - The plan validator stays on Sonnet and checks facts only.
> 8. **Specialists.** `securityReview` and `perfReview` default to `when-needed`, which means no Sonnet sanity pass on streams tagged no.

`## Acceptance`: "README, the roles in `references/roles/*.md`, `config.example.json` and `paths.py` defaults all match the new behaviour." / "No plugin file mentions iap, nsd or Emma."

### Observable acceptance

With an empty `TEAMLEAD_HOME` (no global config), `run_config.py` writes a run `config.json` whose options show `codexPlanReview: always`, `codexCodeReview: on`, `opusCodeReview: fallback`, `securityReview: when-needed`, `perfReview: when-needed`, and whose `codexPlanReviewAxes` ends with `failure-modes`; the first-run seed no longer writes security/perf `on`. `plan_review_package.py <run>` emits a fifth axis section covering restart, cold start, abort, retry, degraded dependency and what each metric counts.

### Test plan

existing: `scripts/test_run_config.py`, `scripts/test_plan_review_package.py` (covers `--axes`).
rewritten existing cases in `scripts/test_run_config.py` (they assert the old in-code default `off` or the old seed `on`, and go red once `paths.DEFAULTS` and `seed_global_config` change):
- `case_a_missing_config_is_seeded_with_both_reviewers` (`:70-81`) — now asserts the seed does not write security/perf `on` and both resolve to `when-needed`; rename it to match.
- `case_a_config_typo_is_skipped_not_fatal` (`:144-155`) — an invalid `securityReview` value now falls through to `when-needed` (source `default`), not `off`.
- `case_task_text_is_not_mistaken_for_flags` (`:210-217`) — its `perfReview == "on"` came from the seed; it now expects `when-needed`.
unchanged because the value comes from a flag or an explicit config, not a default: `case_a_flag_beats_the_config` (`:99-109`, `--codex-plan-review=hard` is a flag and `hard` stays in `paths.CHOICES`), `case_the_old_negative_flags_still_work` (`:188-197`, `--no-*-review` flags), `case_a_disabled_scope_fence_promotes_when_needed` (`:320-339`, explicit `when-needed` config promoted by `scopeFence: false`). No `scripts/test_plan_review_package.py` case counts axes, so none is rewritten there.
new (each new test follows its file's runner convention: a plain `case_*`/`check_*` function registered in that file's `main()`, run as `python3 scripts/test_<name>.py`, no pytest; a NEW test file copies that shape from an existing `scripts/test_*.py`; the `file::test_*` names below are labels, not collected names):
- `scripts/test_run_config.py::test_defaults_without_global_config` — options resolve to the new defaults with sources `default`, including `codexCodeReview: on` and `opusCodeReview: fallback`.
- `scripts/test_run_config.py::test_seed_does_not_force_specialists_on` — the first-run seed leaves security/perf at `when-needed`.
- `scripts/test_run_config.py::test_existing_global_config_wins` — a global config saying `securityReview: on` still resolves to `on` (user configs are not migrated, D15).
- `scripts/test_plan_review_package.py::test_failure_modes_axis` — default package has five axes, the fifth names restart, cold start, abort, retry, degraded dependency and metric semantics; `--axes failure-modes` alone works.
probe: `codexPlanReview` defaults to `always` — default left at `off` (today's `paths.DEFAULTS` value)
probe: no stale default assertion survives — revert only `seed_global_config` to write security/perf `on`: the renamed seed case and `case_task_text_is_not_mistaken_for_flags` must go red; revert only `DEFAULTS["securityReview"]` to `off`: `case_a_config_typo_is_skipped_not_fatal` and `test_defaults_without_global_config` must go red. Then `grep -nE '== "(on|off)"' scripts/test_run_config.py`: every remaining hit is flag- or config-sourced, as listed above
probe: specialists default to `when-needed` — `paths.DEFAULTS` changed but the seed still writes `on`
probe: fifth axis — axis added to `AXIS_TEXT` but not to `PLAN_REVIEW_AXES` (or the reverse), so the default package still has four
probe: config.example.json matches — example file keeps `"on"` / four axes / "Every in-code default is off"
probe: Codex final gate on by default — `codexCodeReview` left at `off`

### Reuse and scope

reuse: `scripts/paths.py:DEFAULTS`, `paths.CHOICES`, `paths.PLAN_REVIEW_AXES`; `scripts/run_config.py:seed_global_config`, `run_config.SEED_NOTE`, `run_config.render`; `scripts/plan_review_package.py:AXIS_TEXT`, `plan_review_package.resolve_axes`.
keep because: `## Decisions` items 2, 6 and 8 (with questions.md Answer 1), and `## Acceptance` ("`config.example.json` and `paths.py` defaults all match").

### Review axes

- `attacker-controlled input: yes — reads user-written JSON config files`
- `hot path: no — runs once per run`
- `public surface: yes — config keys, their defaults, and the plan-review axis names`

### Verification commands

cwd: the WS-3 worktree of `/Users/g.evdokimov/teamlead-retro`
- `python3 scripts/test_run_config.py`
- `python3 scripts/test_plan_review_package.py`
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

===== review-ws3-r2-code.md =====
# Review — WS-3 — round 2 — code

**Verdict:** APPROVED_WITH_NOTES

**Coverage:** I checked triage-ws3-r1 rows 1 to 4 against 7bc8f31 and cc1ced9 (WS-3 part: `scripts/run_config.py`, `config.example.json`, `scripts/test_run_config.py`). Every row is met. Row 1: `run_config.py:43`, restored `expected` line `test_run_config.py:388`, new case `:420` registered in `CASES`, "eight keys" matches the 8 entries in `OPTION_KEYS`. Row 2: `config.example.json:20,23`. I checked the prose against `next.py:835-851,980-984`; the names `--artifact-stem codex-gate` and `triage-gate-r<K>.md` and the `opusCodeReview=off` halt all exist there. Row 3: `test_run_config.py:439`. Row 4: `test_run_config.py:6-8`. HEAD is ed0a968, the same SHA the verifier recorded, and the tree is clean.

## Probes

list: 3 brief + 0 added; off-list clauses: 0; LIST_GAP: 0

- opusCodeReview reaches run options → delete `"opusCodeReview",` at scripts/run_config.py:43 → NOT PROBED: auto mode refused the mutant test run in the clone `probe-ws3-r2-code` (the unmutated baseline there passed 27/27). Static trace: `resolve()` and `render()` iterate `OPTION_KEYS` (`run_config.py:230,276`). Without the key, `written["options"].get("opusCodeReview")` is `None`, so `case_opus_code_review_reaches_the_run_config` and the restored `expected` line in `case_defaults_without_global_config` both go red.
- example matches defaults → set `"opusCodeReview"` to `"off"` at config.example.json:24 → NOT PROBED: same refusal. `case_config_example_matches_the_defaults` compares every `DEFAULTS` key present in the example, so this mutant would show up as drift.
- fifth axis in example → reorder the axes at config.example.json:36 → NOT PROBED: same refusal. Covered by the list-equality comparison and the `[-1] == "failure-modes"` check.

## Findings

| Sev | Location | Req/Concern | Problem → Fix |
|---|---|---|---|

## Notes

- `case_config_example_matches_the_defaults` skips a key that is missing from the example (`if key in example`). That is the shape triage row 3 asked for, but deleting `codexCodeReview` from the example entirely would still pass.
- The WS-3 GREEN content went into the WS-4 commit cc1ced9 (`review_package.py` is in it too) because the two workstreams shared an index. No history repair is allowed, so this needs only an attribution note in the ledger.
- red_freeze `846bedb 7bc8f31` gives RED_CHANGED, 4 lines, all from round 1's 16741fb and all accepted in triage-ws3-r1 Notes. The restored opus line is now frozen. The verifier report has no `RED run` block, so this round's RED failure is the implementer's claim only.
- `skills/delegate/SKILL.md:36,44-52` and `README.md:178,311,315` still say "seven" options, describe `codexCodeReview` as the closing hand-off, and omit `opusCodeReview` from the table. These files are outside WS-3 scope; they belong to the README/roles stream.
- Verifier Flaky: `test_run_state.py`'s `"6d" not in r.stdout` matches random tempdir names. This is not WS-3, but it will flake again.

## Verification

per $RUN/verifier-ws3-r2.md: PASS


===== review-ws3-r2-security.md =====
# Review — WS-3 — round 2 — security

**Verdict:** APPROVED_WITH_NOTES

## Findings

| Sev | Location | Req/Concern | Problem → Fix |
|---|---|---|---|

## Notes

- Attacker-controlled input (tag `yes`): `opusCodeReview` in `OPTION_KEYS` (`scripts/run_config.py:43`) means a cloned repo's `.teamlead.json` value now reaches run options. It is still allowlisted: `resolve` uses `paths.setting(key, repo, paths.one_of(key))` against `paths.CHOICES["opusCodeReview"] = ("off", "fallback")` (`scripts/paths.py:68`), `tier_of` applies the same validator, and `--choice` goes through `parse_choices`. A hostile repo `off` fails closed. `scripts/next.py:981-984` raises `Halt` when Codex cannot run, so the gate is never skipped. Before this change, `review_package.py:1076` already read the same repo key.
- Test-only lines in cc1ced9 remove docstring prose only (`scripts/test_run_config.py:6-12`). No assertion was removed. 7bc8f31 is additive, and it restores the frozen `"opusCodeReview": "fallback"` line.
- The `config.example.json` prose edits (`:4,20,23`) are documentation only. They do not change the vendor-egress Note from round 1.

## Verification

per $RUN/verifier-ws3-r2.md: PASS (head ed0a968f5336d047851803de835d587313bc3442, tree CLEAN; shared HEAD matches, status empty)


===== verifier-ws3-r2.md =====
# Verifier — round 2

OUTCOME: PASS

## Snapshot

head: ed0a968f5336d047851803de835d587313bc3442
tree: CLEAN
HEAD and `git status --porcelain=v1 --untracked-files=all` checked before and after the commands: unchanged, empty status. Commits 7bc8f31 and cc1ced9 are both ancestors of HEAD.

## Commands

python3 scripts/test_run_config.py → exit 0 (27 passed, 0 failed)
python3 scripts/test_plan_review_package.py → exit 0 (13 passed, 0 failed)
ruff check . → exit 0
bash -c 'f=0; for s in scripts/test_*.py; do python3 "$s" || f=1; done; exit $f' → exit 0 on the retry (first attempt exit 1, see Flaky)

## Pre-existing analysis

none (no command failed in the final run)

## Flaky

The full-suite loop failed once and passed on the retry.
- Attempt 1 → exit 1. The one failure was in scripts/test_run_state.py (99 passed, 1 failed):
  `FAIL  a `Smaller:` cut is asked inside the step-6 relay, named`
  `exit=1 out="RUN=/var/folders/lv/.../T/tmp6d6qte3k/2026-09-04-1200-coupons\nrepo=/repo/pricing\nstep: 6 — user relay outstanding\n..."`
  The assertion `"6d" not in r.stdout` (scripts/test_run_state.py:~400) matched the random tempdir name `tmp6d6qte3k` in the RUN= line. This looks like a random-name collision in the test, not a product regression. It is a diagnosis for the caller, not a fix.
- Attempt 2 (whole loop rerun) → exit 0. scripts/test_run_state.py alone also gave 100 passed, 0 failed.


===== triage-ws3-r1.md =====
# Triage — round 1

Verdict: NEEDS_REWORK

## Rows
| Sev | Location | Req/Concern (reviewers) | Problem → Fix |
|---|---|---|---|
| MEDIUM | scripts/run_config.py:36 | Observable acceptance "run config.json options show opusCodeReview: fallback"; D7 (code) | **Problem:** `opusCodeReview` is not in `OPTION_KEYS`, so run `config.json` `options` never carry it; `scripts/next.py:957` falls back to `paths.DEFAULTS` and a user's `opusCodeReview: off` (global, `.teamlead.json` or `--choice`) is silently ignored; the implementer edited the frozen RED line (16741fb) instead. **Fix:** (1) ADD `"opusCodeReview"` to `OPTION_KEYS` right after `"codexCodeReview"`; no new flag (`review_package.py --opus-code-review` stays the standalone override). (2) In `scripts/test_run_config.py::case_defaults_without_global_config` ADD `"opusCodeReview": "fallback"` back into `expected` (restores the frozen line); KEEP the `opus_code_review_in(home) == "fallback"` and `codexPlanReviewAxes[-1]` assertions. (3) ADD a new case registered in `CASES`: global config `{"opusCodeReview": "off"}` plus `--out` gives `written["options"]["opusCodeReview"] == "off"`; a second run with `--choice opusCodeReview=off` over a global `fallback` gives `"off"` with source `options card`. (4) In `config.example.json:3` change "The seven keys below" to "The eight keys below" (verify the count against the final file). |
| MEDIUM | config.example.json:20 | D8 "off skips the gate"; D7; Acceptance "config.example.json matches new behaviour" (code) | **Problem:** `_codexCodeReview` still says the run ends with the /teamlead:codex-review one-liner, "offered rather than run"; with D8 `on` (default) runs the in-loop Codex final gate. `_opusCodeReview` (`:23`) omits that the in-loop gate fallback reads it. **Fix:** rewrite `_codexCodeReview` to `off \| on`: `on` (default) runs the in-loop Codex final gate after the streams are approved (`review_package.py` package, `run_codex_review.py --artifact-stem codex-gate`, triage in `triage-gate-r<K>.md`, gate rework counts against `reworkCap`); `off` skips the gate and the run closes. In `_opusCodeReview` ADD one sentence: the in-loop gate uses the same key when Codex cannot run, and `off` there halts the run. KEEP the existing `--opus-code-review` and ledger sentences. |
| MEDIUM | scripts/test_run_config.py:419 | Acceptance "config.example.json and paths.py defaults all match"; brief probe "config.example.json matches" (code) | **Problem:** no test reads `config.example.json`; reverting `codexCodeReview` to `off` or `codexPlanReviewAxes` to four entries leaves all suites green. **Fix:** ADD a case registered in `CASES`: load `<repo root>/config.example.json`; for every key not starting with `_` that is in `paths.DEFAULTS`, assert `example[key] == (list(v) if isinstance(v, tuple) else v)`; also assert `example["codexPlanReviewAxes"][-1] == "failure-modes"`. Keys absent from `DEFAULTS` (`adrPath`, `adrSubdir`) are skipped. |
| LOW | scripts/test_run_config.py:6 | Prose cited as proof (code) | **Problem:** module docstring lines 6-11 still say every run option defaults to off and the seed keeps the two old reviewers; both halves false after 85a9e18. **Fix:** replace lines 6-11: the in-code defaults already enable the specialists (`when-needed`); the seed writes only a comment; it must fire exactly once and never touch a config the user has edited (D15). KEEP the second paragraph (config-versus-flag asymmetry) unchanged. |

## Demoted to Notes
none

## Notes for the user
- RED_CHANGED (5 lines, 16741fb): code reviewer accepts three lines (word tuple to FAILURE_MODE_WORDS, E501) and the opus-line replacement; row 1 restores the original opus line additively.
- Verifier report has no `RED run` block; code reviewer reproduced RED non-destructively: five test_run_config.py cases and case_the_failure_modes_axis_is_the_fifth fail on assertions.
- `--codex-code-review` (bare = on) is now a no-op since on is default; no `--no-codex-code-review` alias exists. Turning the gate off takes `--codex-code-review=off`. Spec does not require an alias.
- Old user configs are not migrated: a global codexPlanReviewAxes with four entries never gains failure-modes (D15 accepts this).
- Security: codexPlanReview=always and codexCodeReview=on now send plan and diff to an external vendor on every no-config run, including existing installs. Follows Decision 6, not a defect; README/roles (WS-7/WS-8) should state it plainly and name the off switches for confidential repos.
- A cloned repo's .teamlead.json can set codexCodeReview/securityReview off to skip gates; pre-existing.
- seed_global_config keeps pre-existing check-then-write (exists then write_text follows symlinks under TEAMLEAD_HOME); pre-existing, home is user-owned.

## Re-review set
code: re-run — always
security: re-run — fix changes OPTION_KEYS, which governs which config values reach run options (config parsing path); uncertain impact
perf: carried — perfReview=when-needed, hot=no (skipped in round 1; /Users/g.evdokimov/.teamlead/runs/teamlead-retro/2026-10-14-1103-retro-fixes/briefs/review-ws3-r1-perf.skip)

## Rework count
1
