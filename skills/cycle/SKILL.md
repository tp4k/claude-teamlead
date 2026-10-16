---
name: cycle
description: "Runs a task in a fresh worktree, prepares its environment, moves the session, then invokes /teamlead:delegate, whose in-loop Codex gate reviews the finished diff. Includes user decisions. Use for \"cycle this\", \"full teamlead cycle\", or \"fresh tree + teamlead\"."
metadata:
  argument-hint: "<task description> [--slug NAME] [--base REF] [--security-review=off|when-needed|on] [--perf-review=off|when-needed|on] [--with-human-readable-plan=off|generate|pause] [--adr] | --resume <slug>"
allowed-tools: Bash(git worktree list), Bash(git rev-parse *), Bash(git show-ref *), Bash(git check-ignore *), Bash(git log *), Bash(git status *), Bash(git fetch *), EnterWorktree, AskUserQuestion
---

# Teamlead cycle

Prepare a fresh worktree and run `/teamlead:delegate` in one session. Delegate's final gate gives the diff an independent Codex review inside the run. Step 7 moves the session into the worktree before implementation.

A matching cwd alone does not load path-scoped CLAUDE.md outside workspace roots. `EnterWorktree` moves both cwd and roots. Without it, subagents can miss files such as `apps/server/CLAUDE.md`. Earlier versions required a second session for this move.

`$ARGUMENTS` contains the task. Remove `--slug`, `--base`, and `--resume`. Pass the remaining prose and flags to delegate. Its `run_config.py` resolves known flags.

Add `--codex-plan-review=always` and `--with-human-readable-plan=generate` only when the user supplied no explicit value for that option. User flags take precedence. A plan correction costs less before building and reviewing the work. The human-readable plan lets a user inspect the result of a one-line request.

## Four decision points

The cycle can present four routine decisions, subject to run settings:

1. **Delegate step 3a:** choose plan review, human plan, security review, and performance review. The card shows current resolved defaults.
2. **Delegate step 6:** answer the one batch of unresolved questions, design choices, and any scope card. `go` accepts all recommendations. After this batch the run asks again only when it halts.
3. **Delegate step 6d:** inspect the final plan when the hold conditions require it. These include confirmed design corrections and a requested pause. Read `$RUN/plan-human.md` when generated.
4. **Codex-review step 4:** choose which verified out-of-scope findings to follow up. It appears only when you run that skill.

A collision or ambiguous bootstrap can require an additional setup decision. No step merges or pushes.

# Part 1 — prepare the tree

## 1. Resolve the names, mutate nothing

```
git rev-parse --path-format=absolute --git-common-dir
```

Use that path's parent as `<repo>`. `--show-toplevel` can return a linked worktree and incorrectly nest another tree.

- **Slug:** use `--slug` or derive `<issue-number>-<two-or-three-word-kebab>` from the task. Examples: `980-toolgate`, `deferred-ledger`. Use lowercase `[a-z0-9-]`, at most 30 characters. Do not ask the user to derive it. The slug identifies worktree, branch, run, and session.
- **Worktree:** `<repo-parent>/<repo-name>-<slug>`, beside the repository.
- **Branch:** `<type>/<slug>`. Derive type as fix, feat, chore, or docs from the task.
- **Base:** use `--base`, otherwise main.

## 2. Collision check — before creating anything

```
git worktree list
git show-ref --verify --quiet refs/heads/<branch>
```

If the path or branch exists, ask one AskUserQuestion card with these choices in order:

1. **Fresh worktree under another slug:** supply a new slug and continue at step 3. Recommend this option.
2. **Inspect the existing tree:** do not run the cycle. Report its path, branch, latest commit, and porcelain status. Provide `cd <path>` and the delegate command for the user.
3. **Stop:** create nothing. You cannot terminate the session. Explain `/exit` or Ctrl-C twice.

Never reuse an existing tree or choose the collision outcome yourself. Another session can own it, making concurrent work indistinguishable.

## 3. Create the worktree

```
git -C <repo> fetch origin <base>
git -C <repo> worktree add -b <branch> <worktree> origin/<base>
git -C <worktree> log --oneline -1
```

Confirm HEAD equals `origin/<base>`.

## 4. Carry the ignored local config

A fresh checkout lacks ignored files. Missing `.env` configuration can make connection failures look like regressions.

For every root `.env*` file, confirm `git check-ignore -q <file>` before copying it. Never overwrite a tracked file with an old local copy. Report copied filenames. If none exist, say so and continue.

## 5. Bootstrap — the repo's own command, never a hardcoded one

Use the repository's documented setup command verbatim. Check CLAUDE.md, README, or package setup/bootstrap scripts.

If the repository documents no command, select a package manager from the root lockfile and use its normal installation command:

| Root lockfile | Manager |
|---|---|
| `pnpm-lock.yaml` | pnpm |
| `package-lock.json` | npm |
| `yarn.lock` | yarn |
| `bun.lock` / `bun.lockb` | bun |
| `Cargo.lock` | cargo |
| `uv.lock` | uv |
| `poetry.lock` | poetry |
| `go.sum` | go |
| `Gemfile.lock` | bundler |

Check pinning flags against the manager's help before using them. Yarn 2+ uses `--immutable`. Yarn 1 uses `--frozen-lockfile`. Never invent a flag. A normal install without a pinning flag is acceptable here.

If there are multiple root lockfiles, no lockfile, or an unsupported manager, stop and ask for the bootstrap command. Record the answer in step 6's task file.

Bootstrap before moving the session. If it fails, report the command and output, then stop. Do not enter a worktree that cannot build.

## 6. Write the task file

Use `$TEAMLEAD_HOME/tasks/<slug>.md`, defaulting to `~/.teamlead/tasks/<slug>.md`. This lies outside repositories and the replaceable plugin directory. `scripts/paths.py` resolves the state root.

```
slug: <slug>
repo: <abs repo>
worktree: <abs worktree>
branch: <branch>
session: <this session's CLAUDE_CODE_SESSION_ID>
base: <base>@<sha>
flags: <user flags plus cycle defaults only for options the user did not set>
bootstrap: <the command step 5 ran>

# Task
<the task text, VERBATIM, flags stripped>
```

Preserve the exact request. Write the file even when normal execution does not reread it. Resume depends on it.

## 7. Move this session into the tree

```
EnterWorktree({ path: "<worktree>" })
```

Write the task file first and supply the same absolute worktree path. The allow-cycle-worktree hook checks both the worktree and session ID. It grants no other session access. It also requires a worktree created within 30 minutes. Slow bootstrap or decision waits can therefore cause a permission prompt. A missing or incorrect ID has the same effect.

The move updates cwd, write access, workspace roots, CLAUDE.md, and settings. Report this line and continue into part 2:

```
Worktree <worktree> on <branch>, base <base>@<sha>, <n> file(s) carried, bootstrap OK. Session moved into the tree.
```

The UserPromptSubmit hook names the session from the task. Delegate kickoff prints `SESSION_TITLE=<slug>` to refine the title at the next prompt. Do not ask the user to rename or relaunch.

EnterWorktree refuses a worktree of a different repository from the one this session was launched in, for example a cycle started from the plugin checkout for an app repository. When it refuses or is unavailable, launch the resume session yourself. Do not ask the user to do it:

```
python3 $PLUGIN/scripts/launch_cycle_session.py <worktree> <slug>
```

`$PLUGIN` is the plugin root, two levels above this skill's directory. Substitute the absolute path.

It starts a Claude Code background session (`claude --bg`) with its cwd in the tree, running `/teamlead:cycle --resume <slug>`. That works in any terminal: the session runs under Claude Code's background service, not in a terminal pane.

- **Exit 0, `LAUNCHED <id> <worktree>`:** report the setup line, ending it with `Resume session <id> started; part 2 runs there. Open it with: claude attach <id>`, and stop. Its cards wait in that session. Part 2 must not also run here.
- **Exit 1, `MANUAL: …`:** no claude binary, or `claude --bg` refused, for example because the tree is untrusted. Relay Claude's error and the printed command, then stop. This is the only case where the user types the command.
- **Exit 2:** a bad slug or path. Fix the argument; it is a step 1 or 3 bug.

# Part 2 — run the cycle

Continue from step 7 or resume in a session started inside the worktree.

## 8. Load and check

On `--resume <slug>`, read the task file under `$TEAMLEAD_HOME/tasks/`. Confirm cwd equals its `worktree:` before continuing. If it differs, stop and print the correct cd command. Running from the primary checkout can silently omit nested CLAUDE.md rules.

## 9. Implement — `/teamlead:delegate`

Invoke `/teamlead:delegate` with the saved task and `flags:`. Identify this worktree as the repository. Relay the human-readable plan path when generated.

Delegate owns planning, questions, implementation, verification, review, triage, and the Codex gate. Do not duplicate them. Its run path is `$TEAMLEAD_HOME/runs/<worktree-dir-name>/<timestamp>-<slug>/`.

If delegate halts before the gate approves, stop the cycle. No further review runs. Report the cause, run directory, and every landed commit:

- **ADR conflict:** implementation did not start.
- **Rework cap:** work remains unapproved, in stream rework or gate rework alike. Other completed streams may already be approved.
- **CANNOT_RUN:** the environment or command prevented verification.
- **Blocked or partial:** work needs an answer or another implementation round.
- **Codex cannot run with `opusCodeReview=off`:** the gate has no reviewer.


## 10. Review — the in-loop Codex gate

Delegate's step 10a already ran the independent review: after every stream was approved, Codex reviewed the whole diff (the Opus fallback when Codex could not run), triage folded its findings into rework rounds, and the gate looped until clean. Do not start a separate `/teamlead:codex-review` after it.

Run `/teamlead:codex-review` with this worktree only when `codexCodeReview=off` skipped the gate and the user wants the review anyway. Use `--no-network` only when no review claim needs GitHub, PR, or CI access. If Codex cannot run, stop unless `opusCodeReview=fallback`.

Rows the gate triaged as out of scope sit in the run's ledger rows and final report. The user may pick any of them for a follow-up with `/teamlead:codex-review <run>`, which writes `review-followup.md` and supplies `/teamlead:delegate <path>`.

Do not use `--package-only` or report its manual `Follow instructions to review PR @<abs>/PROMPT.md` handoff as the completed review.

## 11. Closing report

Report the worktree, branch, base SHA, run directory, commit count, plan-review counts, and human-plan path. Include the gate's verdict, its reviewer identity (Codex or Opus fallback), and the rework rounds it needed. Include any follow-up path, delegate command, and deferred-work count.

Selected out-of-scope fixes start a separate delegate run with its own plan, questions, and reviews. That run invokes codex-review at step 11. It reviews only new fix commits and checks earlier findings. Codex remains first, with Opus fallback available when it produced the earlier review. Do not hide this separate round inside the initial cycle.

## Never

- Merge or push.
- Reuse an existing worktree or branch. The collision procedure permits inspection, not automatic reuse.
- Run delegate before the session moves into the worktree.
- Ask for relaunch, rename, or cd when EnterWorktree is available and accepted.
- Print the manual resume command when EnterWorktree refuses, before `launch_cycle_session.py` has tried and exited 1.
- Hardcode bootstrap, package manager, or `.env` as the sole possible carried file.
- Report a package-only handoff as a completed review.
- Run a second Codex review after the in-loop gate ran.
- Enter a worktree whose bootstrap failed.
