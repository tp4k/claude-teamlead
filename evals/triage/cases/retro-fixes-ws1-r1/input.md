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
- `===`/`!==` (JS/TS) are deliberately never flipped (`OPS` lookaround
…[truncated]

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
