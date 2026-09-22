---
name: cycle
description: 'One delivery cycle from one free-text task, in one session: a fresh worktree off origin/main, bootstrapped, the session moved into it and named after the work, then /teamlead:delegate with the plan reviewed by Codex before anything is built, then a full /teamlead:codex-review with its findings ledger. Four decision points, not zero. Use when the user says "cycle this", "full teamlead cycle", "fresh tree + teamlead", or hands over a task and wants the worktree, the run and the review packaged together.'
user-invocable: true
argument-hint: "<task description> [--slug NAME] [--base REF] [--security-review=off|when-needed|on] [--perf-review=off|when-needed|on] [--with-human-readable-plan=off|generate|pause] [--adr] | --resume <slug>"
allowed-tools: Bash(git worktree list), Bash(git rev-parse *), Bash(git show-ref *), Bash(git check-ignore *), Bash(git log *), Bash(git status *), Bash(git fetch *), EnterWorktree, AskUserQuestion
---

# Teamlead cycle

One free-text task in; a fresh named worktree, a `/teamlead:delegate` run and an independent review
out. Everything else is derived, and it all happens in **one session**: step 7 moves this
session into the worktree with `EnterWorktree`, and only then does part 2 run.

That move is not cosmetic. A path-scoped `CLAUDE.md` loads only for files under one of the
session's **workspace roots** — cwd alone does not do it — so a coordinator still rooted in the
primary checkout hands every subagent a workspace the worktree is not inside. Run
`/teamlead:delegate` before step 7 and a server workstream never sees `apps/server/CLAUDE.md`.
`EnterWorktree` moves the roots and cwd together, which is the whole reason this used to demand
a second session.

`$ARGUMENTS` is the task. Strip `--slug`, `--base` and `--resume`; everything else is the task
text, and `/teamlead:delegate` resolves its own options out of it (`run_config.py` reads the flags
it knows and ignores the prose, so nothing here has to decide what is a flag).

**The cycle adds two of those options itself**, appended to the task text it passes on:
`--codex-plan-review=always --with-human-readable-plan=generate`. A cycle is the expensive
shape of this workflow — a fresh tree, a full run, then a 10–20 minute independent review of
the diff — and the cheapest place by far to catch a wrong design is before any of that starts:
a plan defect costs a paragraph here and a whole round after implementation. The human-readable
plan comes with it because the cycle is also the path where the user is furthest from the work,
having handed over one line of text. A user flag wins over both: an explicit
`--codex-plan-review=off` in the task text is theirs, not a value to override.

## Four decision points

The cycle is one command, not one turn. It stops for you four times, and you should know
where before you start it:

1. **The run options card** (`/teamlead:delegate` step 3a) — the plan review, the human-readable
   plan, and whether the security and performance reviewers run always, only where the planner
   flags a surface, or not at all. Current values are pre-marked; every one of them has a config
   default, so this card is a chance to change your mind, not a form to fill in.
2. **`/teamlead:delegate` step 6** — the open questions, plus a card for any design finding that is
   a real choice. Arrives as `AskUserQuestion` cards; `go` accepts every recommendation at once.
3. **The hold gate** (`/teamlead:delegate` step 6d) — the plan is final and something wants your
   eyes on it: a scope cut the validator named, confirmed design findings, or `=pause`. This is
   where `$RUN/plan-human.md` is worth reading; it is the same plan in about a page.
4. **`/teamlead:codex-review` step 4** — which of the triaged findings to act on.

A fifth appears only on a collision (step 2). Nothing else is asked; nothing is
merged or pushed at any point.

---

# Part 1 — prepare the tree

## 1. Resolve the names, mutate nothing

```
git rev-parse --path-format=absolute --git-common-dir     # → <repo>/.git, even from a linked worktree
```

`<repo>` is that path's parent — never `--show-toplevel`, which returns the worktree you
happen to be standing in and would nest a tree inside a tree.

- **slug**: `--slug` if given; otherwise `<issue-number>-<two-or-three-word-kebab>` derived
  from the task (`980-toolgate`, `deferred-ledger`). Lower-case `[a-z0-9-]`, ≤ 30 chars.
  Derive it silently — do not ask. This one string names the worktree, the branch, the
  `/teamlead:delegate` run directory and the session, so all four are findable together later.
- **worktree**: `<repo-parent>/<repo-name>-<slug>`, a sibling of the repo.
- **branch**: `<type>/<slug>`, type from the task's verb (`fix` / `feat` / `chore` / `docs`).
- **base**: `--base` if given, else `main`.

## 2. Collision check — before anything is created

```
git worktree list
git show-ref --verify --quiet refs/heads/<branch>
```

If the worktree path exists **or** the branch exists, stop and put it to the user as one
`AskUserQuestion` card, in this order:

- **Start a fresh worktree under a different slug** — you supply the new slug, and the cycle
  continues from step 3 with it. First option, and the recommended one.
- **Switch to the existing tree** — the cycle does not run. Report the tree's path, its
  branch, its `git log --oneline -1` and its `git status --porcelain` so the user can see
  what is in it, and print `cd <path>` plus the `/teamlead:delegate` line they would run there.
- **Stop here** — the cycle ends immediately having created nothing. You cannot terminate a
  session yourself; say so and print how to leave it (`/exit`, or Ctrl-C twice).

Never reuse an existing tree, and never pick between these yourself. A tree another session
may own is the one thing this skill must not touch: two sessions in one worktree costs the
attribution of both and duplicates work invisibly.

## 3. Create the worktree

```
git -C <repo> fetch origin <base>
git -C <repo> worktree add -b <branch> <worktree> origin/<base>
git -C <worktree> log --oneline -1              # HEAD must equal origin/<base>
```

## 4. Carry the ignored local config

A worktree is a fresh checkout: everything git ignores is absent from it. Typically that
is `.env`, and without it the suite fails with mass `ECONNREFUSED` that reads exactly like
a regression the change caused.

Copy every root file matching `.env*` that `git check-ignore -q <file>` confirms is ignored
— confirm, don't assume, so a tracked file git already provides is never overwritten by a
stale local copy. Report each file copied by name. If the repo has none, say so and move on;
that is normal for most repos, not an error.

## 5. Bootstrap — the repo's own command, never a hardcoded one

Prefer a bootstrap command the repo documents: a `CLAUDE.md` "Common Commands" section, the
README's setup steps, or a `setup` / `bootstrap` script in `package.json`. Use that verbatim.

Only when the repo documents nothing, pick the package manager from the lockfile at the
repo root and run its plain install:

| lockfile at root | manager |
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

Lockfile-pinning flags differ by major version and are the easiest thing here to get wrong
— `yarn install --immutable` is Yarn 2+, Yarn 1 spells it `--frozen-lockfile`. Confirm the
flag against `<manager> install --help` before you use one, or run the plain install without
it. Never invent a flag.

**Two lockfiles at the root, or none, means stop and ask** — do not guess which one owns the
tree. Same for a repo where nothing above matches: report it, ask what the bootstrap is, and
carry the answer into step 6's task file so part 2 has it.

This step blocks, and it stays before step 7 on purpose: a bootstrap that fails here costs
nothing and is reported from the primary checkout, while the same failure found after the move
leaves the session standing in a tree that cannot build. If it fails, report the command and
its output and stop — do not move into a tree that cannot build.

## 6. Write the task file

```
~/.teamlead/tasks/<slug>.md
```

It lives outside the repo deliberately: no `.gitignore` in any repo has to cooperate, and
nothing can be committed by accident. It also lives outside the plugin, for the reason the
run directory does — `claude plugin update` replaces that tree (`scripts/paths.py`);
`$TEAMLEAD_HOME` moves both. Contents:

```
slug: <slug>
repo: <abs repo>
worktree: <abs worktree>
branch: <branch>
base: <base>@<sha>
flags: <the user's own flags, plus --codex-plan-review=always --with-human-readable-plan=generate>
bootstrap: <the command step 5 ran>

# Task
<the task text, VERBATIM, flags stripped>
```

Verbatim matters the same way it does everywhere in this workflow: a paraphrase is a new
request nobody agreed to. The file is also what makes `--resume <slug>` possible at all, so
write it even though the normal path never reads it back.

## 7. Move this session into the tree

```
EnterWorktree({ path: "<worktree>" })
```

One call, and the session's cwd, its write access and its workspace roots are all inside the
worktree; the worktree's own `CLAUDE.md` and settings load with it. Report one line and
continue straight into part 2 — same session, same turn if nothing needs asking:

```
Worktree <worktree> on <branch>, base <base>@<sha>, <n> file(s) carried, bootstrap OK. Session moved into the tree.
```

**The session's name needs nothing from you.** The plugin's `UserPromptSubmit` hook named it
from the task text the moment the cycle was invoked, and `/teamlead:delegate`'s kickoff then
requests the run's real slug (`new_run.py` prints `SESSION_TITLE=<slug>`), which replaces that
first guess at the following prompt — the answer to `/teamlead:delegate`'s open questions. Do
not print a rename instruction and do not ask the user to relaunch: a session can be renamed
in place, and that is what removed the second session from this cycle.

If `EnterWorktree` is not available or the call is declined, and only then, fall back to the
cold path — print this and stop:

```
cd <worktree> && claude "/teamlead:cycle --resume <slug>"
```

No `-n` on that line: the hook derives the name from the command itself, so the new session
comes up as `<slug>` anyway.

---

# Part 2 — run the cycle

Entered directly from step 7, or as `--resume <slug>` in a session that came up in the tree.

## 8. Load and check

On `--resume <slug>`, read `~/.teamlead/tasks/<slug>.md` — it holds everything part 1
derived. Either way, confirm cwd equals its `worktree:` line before going further; if it does
not, stop and print the correct `cd`. Running the rest from the primary checkout is the exact
failure step 7 exists to prevent, and it fails silently — the subagents work, they just never
see the nested `CLAUDE.md` files.

## 9. Implement — `/teamlead:delegate`

Invoke the `teamlead` skill with the task text from the file plus its `flags:` line — which
already carries `--codex-plan-review=always --with-human-readable-plan=generate` from step 6 —
telling it the repo is this worktree. When the run reports the human-readable plan's path, print
it: it is the artifact this cycle produces for a person rather than for an agent, and a path that
appears only inside a subagent's output is one nobody opens. It owns planning, questions, implementation, verification,
review and triage; duplicate none of that here. Its run directory is
`~/.teamlead/runs/<worktree-dir-name>/<timestamp>-<slug>/` — keyed on the
directory name it is handed, which is why the worktree carries the slug.

**If `/teamlead:delegate` halts short, the cycle stops and the review does not run.** Report the halt
reason, the run directory, and every commit that landed:

- **ADR conflict** — halted before dispatch, nothing was built.
- **Rework cap** — commits exist but no workstream is approved.
- **`CANNOT_RUN`** — the environment broke; this is never a coder's failure.
- **`blocked` / `partial`** — the stream needs an answer only the user has.

A Codex review grades work against intent. Work that failed its own verifier has no intent
to grade, and reviewing it spends 10–20 minutes saying so.

## 10. Review — `/teamlead:codex-review`

On a clean finish, invoke `codex-review` with the worktree as the target and **no flags**.
The default path is the point: it builds the package, runs a fresh Codex session in a
disposable linked worktree with network access (background, 10–20 minutes), and triages
every finding into a verdict ledger where each row appears exactly once with the evidence
that settled it. Pass `--no-network` to review in the hard read-only sandbox instead —
right when nothing in the change needs `gh`, a PR or a CI run to settle it.

Its output is that ledger plus the counts line, then it asks which `CONFIRMED`,
`PLAN-DEFECT` and `PRE-EXISTING-SUBSYSTEM-REWRITTEN` rows to act on, writes
`<run>/review-followup.md`, and hands over `/teamlead:delegate <run>/review-followup.md`.

`Follow instructions to review PR @<abs>/PROMPT.md` is **not** this path's output — that is
the legacy `--package-only` handoff. Do not pass `--package-only`, and do not report that
line as the result.

## 11. Closing report

One message: worktree path, branch, base SHA, run directory, commit count, the plan design
review's counts line, the `$RUN/plan-human.md` path, the code review ledger's counts line, the
`review-followup.md` path, the `/teamlead:delegate <path>` one-liner, and the deferred-work rows
added if any.

The fix round is deliberately **not** part of the cycle. Fixing confirmed findings is a fresh
`/teamlead:delegate` run with its own plan, its own questions and its own reviewers; folding it in
would hide a second full round of cost behind one command and give that round no independent
review of its own.

---

## Never

- Merge or push. No step does either, ever, and no flag enables it.
- Reuse an existing worktree or branch, or decide a collision yourself.
- Run `/teamlead:delegate` before step 7 has moved the session into the worktree.
- Tell the user to relaunch, rename, or `cd` anywhere while `EnterWorktree` is available.
- Hardcode a package manager, a bootstrap command, or `.env` as the only carried file.
- Report the `--package-only` handoff line as the review result.
- Enter a tree whose bootstrap failed.
