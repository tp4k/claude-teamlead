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
