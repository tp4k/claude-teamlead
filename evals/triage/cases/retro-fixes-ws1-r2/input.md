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
