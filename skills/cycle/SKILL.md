---
name: cycle
description: 'One delivery cycle from one free-text task, in one session: a fresh worktree off origin/main, bootstrapped, the session moved into it and named after the work, then /teamlead:delegate, then a full /teamlead:codex-review with its findings ledger. Three decision points, not zero. Use when the user says "cycle this", "full teamlead cycle", "fresh tree + teamlead", or hands over a task and wants the worktree, the run and the review packaged together.'
user-invocable: true
argument-hint: "<task description> [--slug NAME] [--base REF] [--no-perf-review] [--no-security-review] [--adr] | --resume <slug>"
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

`$ARGUMENTS` is the task. Strip `--slug`, `--base`, `--resume` and the flags `/teamlead:delegate`
parses itself (`--no-perf-review`, `--no-security-review`, `--adr`) before the remaining
text becomes the task; the `/teamlead:delegate` flags are passed through untouched.

## Three decision points

The cycle is one command, not one turn. It stops for you three times, and you should know
where before you start it:

1. **`/teamlead:delegate` step 6** — open questions and the scope cut block dispatch. Arrives as
   `AskUserQuestion` cards; `go` accepts every recommendation at once.
2. **The plan confirmation** (`$RUN/plan.md`), only when the planner returns `complex=yes` — proceed,
   edit it first, or send it back to the planner.
3. **`/teamlead:codex-review` step 4** — which of the triaged findings to act on.

A fourth appears only on a collision (step 2). Nothing else is asked; nothing is
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
flags: <the /teamlead:delegate flags, or none>
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

Invoke the `teamlead` skill with the task text from the file plus its `flags:` line, telling
it the repo is this worktree. It owns planning, questions, implementation, verification,
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

One message: worktree path, branch, base SHA, run directory, commit count, the review
ledger's counts line, the `review-followup.md` path, the `/teamlead:delegate <path>` one-liner, and
the deferred-work rows added if any.

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
