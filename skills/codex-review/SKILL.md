---
name: codex-review
description: "Runs an independent Codex review of completed teamlead work and triages every finding. Use for \"review this run\", /teamlead:delegate --review, a requested Codex review, or pasted findings. With opusCodeReview=fallback, dispatches the Opus reviewer when Codex cannot run."
metadata:
  argument-hint: "[run dir | repo/worktree path] [--list] [--base SHA] [--with-diff] [--out DIR] [--package-only] [--timeout-minutes N] [--opus-code-review=off|fallback]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/review_package.py *), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/run_codex_review.py *)
---

# Review a teamlead run with Codex

`$PLUGIN` is the plugin root, two levels above this skill's directory. Substitute its absolute path in commands. Literal placeholders may reach Bash without expansion.

Perform the four steps below in order. Codex performs the initial review. If enabled, the fallback agent performs it when Codex cannot run. The coordinator triages findings and must reject them only with evidence.

## 1. Build the package

```
python3 $PLUGIN/scripts/review_package.py <target> [--with-diff]
```

Target may be a run directory, repository/worktree path, or omitted for cwd. The script finds the newest matching run. If the user supplies no target and cwd is not the intended worktree, run `--list` and ask the user to select one. For an explicit `--list`, print the list and stop.

The package contains PROMPT.md and a sibling copy of the complete plan. PROMPT.md includes task, base SHA, commits, changed files, rubric, and answer contract. The script also copies files referenced by the task. A prior review used as a fix request supplies acceptance criteria. Codex cannot expand the coordinator's `$RUN` placeholders.

Use `--with-diff` only when the reviewer cannot access the repository. Otherwise it reads git directly. For work without a teamlead run, pass `--plan <file>` and any written request as `--task <file>`. A PR body can supply the plan. Without intent sources, the prompt identifies the limitation rather than inventing scope.

Retain base SHA, commit/file counts, package path, and every WARNING verbatim. A base warning can indicate an incorrect review range. If packaging exits 1, report the error and stop. A corrected `--base` or `--out` commonly resolves it.

Retain the printed `opus    : opusCodeReview=<value>  (<source>)` line. It governs fallback before review starts. Pass through an explicit `--opus-code-review=<v>` to the packager. It overrides config.

For `--package-only`, report counts, base, warnings, and the printed manual handoff exactly. Put `Follow instructions to review PR @<abs>/PROMPT.md` last and stop. Do not pass `--package-only` to the packager itself.

## 2. Run the independent Codex review

```
python3 $PLUGIN/scripts/run_codex_review.py <absolute-PROMPT.md> [--timeout-minutes N] [--no-network]
```

Skip this step for package-only. The runner reads the repository from PROMPT.md and checks saved Codex login. It starts a fresh session in a disposable linked worktree beside the prompt.

The normal sandbox permits workspace writes and network access. Network access enables PR/CI checks, gh, and test dependencies. Before review, the runner saves `git diff HEAD` and copies untracked files into `pre-review-tree/`. It applies that backup to the isolated tree.

Untracked copying stops at 500 files or 50 MB. It skips symlinks and non-regular files. Each omission produces a warning. Review continues, but silence about omitted files proves nothing. Report every warning.

The runner supplies the disposable path through stdin. It removes that worktree on success, failure, or timeout. File edits inside that checkout disappear with it.

### Source-state warnings

The runner compares the source HEAD and dirty-content digest. A filesystem warning during isolation means the reviewer changed the live tree outside the disposable checkout. Report it verbatim.

Linked worktrees share git metadata. The runner also snapshots the common git directory, including unanticipated files. These warnings can reflect source repository changes without a filesystem escape.

Read configuration warnings first. `core.hooksPath` and aliases can change later command execution. Read hook warnings next, then reflog warnings. Reflogs retain earlier branch positions, so shrinking them can erase recovery history.

Object warnings use object IDs available from local loose objects and pack indexes. They do not compare storage layout or follow `objects/info/alternates` into borrowed stores. Changes inside a borrowed store produce no warning. Changes to the pointer file do. Repacking or garbage collection produces no object warning if every object remains available.

A `deleted` entry identifies a lost local object or removed reachability metadata, including alternates pointers. A `created` entry identifies a newly available object, new reachability metadata, or corrupt loose-object bytes.

Loose corruption includes a hash mismatch or a zlib stream without a complete end. It produces a `created` entry for that path even if the object existed earlier. Only unverifiable loose objects enter the content-comparison map.

### Completion and failure

`--no-network` uses the hard read-only sandbox and skips disposable worktree creation. Use it when no claim requires PR or CI access.

The runner writes `codex-review-rN.md` and `codex-review-rN.jsonl` beside PROMPT.md. Use the exact printed paths. Saved ChatGPT login does not require OPENAI_API_KEY. The new process receives no Claude conversation. Its context consists of the package, referenced files, and repository access.

Start the runner in background Bash. Real reviews take 10–20 minutes and exceed foreground limits. Let its completion notification resume the workflow. Do not poll JSONL or use repeated sleeps. The runner terminates the entire process group at its timeout, default 30 minutes, and reports retained JSONL.

Do not start interactive login or weaken sandbox settings beyond the runner's defaults. Never use `--dangerously-bypass-approvals-and-sandbox`. Do not substitute your own initial review.

On failure, report the error and any retained JSONL path. With `opusCodeReview=off`, stop. With `opusCodeReview=fallback`, continue to step 2b. A separate Codex process on the same machine can read the repository and does not require `--with-diff`.

Codex can load skills from `~/.agents/skills`. A packaging-side skill named codex-review there can give the independent reviewer the wrong role. An earlier run announced that skill instead of starting from its package. Do not install such a packaging copy there.

On success, read the complete answer and continue directly to triage. Do not ask the user to paste it.

## 2b. The Opus stand-in — only with `opusCodeReview=fallback`

Use fallback only after runner failure and resolved `opusCodeReview=fallback`. It prevents a requested independent review from ending as an unactioned error.

Record the live tree metadata before dispatch. The reviewer must not change files, HEAD, refs including stash, local config, or hooks:

```bash
{ git -C <repo> rev-parse HEAD; git -C <repo> status --porcelain;
  git -C <repo> for-each-ref --format='%(objectname) %(refname)';
  git -C <repo> config --local --list;
  ls -lA "$(git -C <repo> rev-parse --path-format=absolute --git-path hooks)"; }   > <abs dir of PROMPT.md>/tree-before-rN.txt
```

This block records status and metadata. It does not hash every tracked or untracked file. Exclude ignored build outputs because permitted test commands can recreate them on every run.

Dispatch `teamlead:code-reviewer` in the foreground with this prompt:

```
PROMPT.md: <abs path of review-package/PROMPT.md>
Repo: <abs repo path from the package output>
Answer: <abs dir of PROMPT.md>/opus-review-rN.md   (N = the first unused number)
Codex could not run (<the runner's error line, verbatim>), so this is the only review of this change.
```

If the agent type is unavailable in this session, use general-purpose with model opus. Prepend `Read $PLUGIN/agents/code-reviewer.md first; it is your instruction set.` with the resolved path.

After completion, repeat the metadata block into tree-after-rN.txt and compare with diff. Report any difference as WARNING. Do not revert it yourself. Read the entire answer and use the same triage rules as for Codex. Record reviewer identity in the ledger.

## 3. Triage the Codex findings

Read the five required parts: findings, Blocking, Per axis, Plan defects, and Verified for this review. Start with Verified. It distinguishes executed checks from inferred claims. Use that evidence to plan each row's verification. Do not omit verification for any row.

A follow-up package prints `closes  :` and requests `## Earlier findings`. Each earlier row receives FIXED, PARTIAL, or NOT FIXED. The range starts at the earlier reviewed head and contains only the fix run's commits.

Triage every PARTIAL or NOT FIXED record as a findings row. Prefix it `earlier:` in the ledger. CONFIRMED means it remains unresolved. FIXED requires no verdict, but include its count in the closing line. Report these counts beside any new defects in the fixes.

If the user instead pasted findings from another agent, skip package creation and the
Codex run and triage that pasted review using the same rules below.

Handle `## Blocking` before any code row: a conflict, a branch that does not contain its
base, or a head with no CI run makes the rest of the review provisional, and each blocking
claim is one command away from settled.

Then reach a verdict on **every** table row. An outside reviewer has no access to the
run's decisions and will sometimes flag things the plan settled on purpose — but the same
prompt invited it to say the plan itself is wrong, so the plan is evidence of intent here,
not the arbiter. Read the cited lines first, then pick:

| verdict | what it means | what it takes to say it |
|---|---|---|
| `CONFIRMED` | the claim holds against the diff | the cited lines, quoted |
| `PLAN-DEFECT` | the code matches the plan and the **plan** is wrong | the plan line and the code line side by side |
| `VALID-OUT-OF-SCOPE` | true, and not this change's business | the anti-scope or spec line that excludes it |
| `PRE-EXISTING-UNTOUCHED` | the fault predates the change, in code it did not rebuild | `git show <base>:<path>` output, quoted |
| `PRE-EXISTING-SUBSYSTEM-REWRITTEN` | predates the change, but this change rebuilt the thing that owns it | the same base quote, plus the diff hunk that rebuilt it |
| `WRONG` | falsified | the row's own "how to falsify" step, **executed**, with its output |
| `OPEN` | not verifiable with what you have | one line on what you tried and what would settle it |

WRONG requires the executed falsification step and actual output. Both PRE-EXISTING verdicts require a quotation from the file at the base SHA. Without evidence, use OPEN and report it to the user. Do not silently discard hard-to-reproduce races, cross-process failures, or load-dependent findings.

Distinguish untouched pre-existing defects from those in a subsystem this change rewrites. The latter need an explicit user decision. This distinction produced the most useful finding in an earlier review.

Then report the **ledger**, which is the whole point of this step:

```
Reviewer: Codex | Opus (fallback — Codex <the runner's error, short>) | pasted: <who>

| # | row (verbatim) | verdict | evidence |
|---|---|---|---|

CONFIRMED n · PLAN-DEFECT n · OUT-OF-SCOPE n · PRE-EXISTING n (n in rewritten subsystems) · WRONG n · OPEN n · reviewer: Codex | Opus fallback | pasted
```

Include reviewer identity in the header and counts line. Counts can travel alone into chat or the cycle report. Opus shares a model family with the implementation agents. Its fresh read does not provide Codex's cross-vendor independence.

Quote every finding exactly once and record its disposition. Do not summarize rows away. Add Plan defects as PLAN-DEFECT rows. Record Per axis verdicts on a closing line.

Append VALID-OUT-OF-SCOPE findings to `docs/deferred-work.md` with Source = external review. Follow `references/deferred-work-ledger.md`. Read first and append with Edit. Never Write over an existing ledger or stage it.

## 4. Route the accepted rows back

Show the user the ledger and ask which `CONFIRMED`, `PLAN-DEFECT` and
`PRE-EXISTING-SUBSYSTEM-REWRITTEN` rows to act on. For the ones they pick, write
`<run>/review-followup.md`:

- A header first, exactly these five lines — `/teamlead:delegate` reads them to know that its
  run is closing this review, and reruns it on the fixed tree at its step 11:

  ```
  <!-- teamlead:review-followup -->
  Reviewer: Codex | Opus fallback
  Target: <abs path of the repo/worktree you reviewed>
  Review package: <abs path of review-package/PROMPT.md>
  Reviewed head: <the full head SHA the package script printed>
  ```

  `Reviewer:` is the one that wrote the answer you just triaged, on its own: `Codex` or
  `Opus fallback`, nothing after it. A pasted review gets `Codex` — the rerun has no paste
  to wait for, so it goes to the default reviewer. `Reviewed head:` is what makes the rerun
  a review of the fixes rather than a repeat: the fix run's package starts its range there,
  so the reviewer reads only the new commits, and checks each row below against them.
  A pasted review with no package gets `git rev-parse HEAD` of the tree it was about.
- `# Task` — one paragraph naming the repo, the worktree and the base SHA, and saying
  these findings come from the verified external review of that range.
- `## Findings to fix` — the accepted rows verbatim, each with the lines you read and the
  evidence that confirmed it. Verbatim matters: a rephrased finding is a new claim nobody
  verified.
- `## Not in scope` — the rejected and deferred rows in one line each with their verdict,
  so the fix run does not re-open a settled row or re-derive a rejection.

Provide `/teamlead:delegate <run>/review-followup.md` for the selected fixes. That separate run reruns this review on its own run directory at completion. Codex remains first. Add `--opus-code-review=fallback` when the header identifies Opus fallback.

If the user selects no rows, create no follow-up file and start no fix run. Every iteration therefore requires a user selection.

Fix findings directly only when the user explicitly requests it. Otherwise this skill ends with the verified ledger and selected follow-up task.
