---
name: codex-review
description: 'Have Codex independently review a finished /teamlead:delegate run with its full task, plan, and diff context, then triage every finding in Claude Code. Use when the user says "review this run", "/teamlead:delegate --review", asks for a Codex review of teamlead work, or pastes back findings from another agent.'
user-invocable: true
argument-hint: "[run dir | repo/worktree path] [--list] [--base SHA] [--with-diff] [--out DIR] [--package-only] [--timeout-minutes N]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/review_package.py *), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/run_codex_review.py *)
---

# Review a teamlead run with Codex

**`$PLUGIN` is the plugin root** — two levels above this skill's base directory, which the harness names when it loads this file. Resolve it yourself in the commands below; a `${...}` reaches your Bash unexpanded.

Four jobs, in order. Do not perform the initial review yourself — Codex is the
independent reviewer. Your job on the way back is the opposite one: make sure
nothing it found is lost, and reject a finding only on evidence.

## 1. Build the package

```
python3 $PLUGIN/scripts/review_package.py <target> [--with-diff]
```

`<target>` is a run directory, a repo/worktree path, or omitted (uses cwd); the script
works out which and finds the newest matching run. **If the user names no target and this
session's cwd is not the worktree, do not guess** — run `--list`, show the runs, and ask
which one. The script does the same thing on failure, so a wrong path is self-correcting.
If the user explicitly passed `--list`, show the script's list and stop; there is no
package or review to run yet.
It writes `PROMPT.md` (small: task, base SHA, commits, changed files, the rubric, the
answer contract) plus `plan.md` (whole, as a sibling) into `<run>/review-package/`, and
copies any file the task itself points at — when the task is "fix the issues from this
review", that review is the acceptance criteria, and `$RUN/…` is a path the reviewing
agent cannot expand. Add `--with-diff` only when the reviewing agent has no access to the
repo — the prompt otherwise tells it to read the diff from git itself.

A branch written outside a `/teamlead:delegate` run has no run directory, so nothing states the
request: pass `--plan <file>` (a PR body does) and `--task <file>` if the ask exists in
writing anywhere. Both matter more than they look — the prompt grades the diff against
whatever intent it can quote, and with neither it tells the reviewer so instead of
inventing a boundary to measure against.

Keep the base SHA, commit/file counts, package path, and **every WARNING the script
printed verbatim** for the final report. A base warning means the review may cover the
wrong range — never suppress it. If the script exits 1, report the error and stop; the
usual fix is `--base <sha>` or `--out <dir>`.

If the user passed `--package-only`, retain the old manual handoff: report the base SHA
and commit/file counts, every warning, and then copy the script's final
`Follow instructions to review PR @<abs>/PROMPT.md` line exactly as printed. Put that
line last and stop. Do not pass `--package-only` to `review_package.py`.

## 2. Run the independent Codex review

Unless this is `--package-only`, pass the generated prompt to the bundled runner:

```
python3 $PLUGIN/scripts/run_codex_review.py <absolute-PROMPT.md> [--timeout-minutes N] [--no-network]
```

The runner extracts the repository from the generated prompt, checks the saved Codex
CLI login, and starts a **fresh** Codex session in a disposable linked worktree beside
the prompt. The sandbox is `workspace-write` with network access on, because that is the
only Codex mode that has network — and a reviewer without network cannot run `gh`, settle
a `## Blocking` CI claim, check the PR, or fetch what a test needs. Before Codex starts,
the runner saves the source's uncommitted work — `git diff HEAD` as a patch, plus the
untracked files copied whole — into `pre-review-tree/`, then uses that same backup to make
the disposable checkout equivalent to the live tree. The untracked copy stops at 500 files
or 50 MB, and skips symlinks and anything that is not a regular file; each of those is a
warning rather than a silent truncation. The review still runs either way, so such a
warning means the isolated tree is missing untracked files and the reviewer's silence
about them proves nothing. Report it with the rest. The prompt sent through stdin names
the disposable path, and the runner force-removes it on success, failure, or timeout, so
anything the networked reviewer writes **to that checkout's files** is discarded with it.

The runner retains the original tree's HEAD and dirty-content digest comparison as a
backstop. A filesystem warning while isolation is active means the reviewer escaped the
disposable checkout and changed the live tree; report every such `WARNING:` verbatim.

**Not everything the reviewer writes is contained** — a linked worktree shares the whole
repository, so the runner snapshots the git common directory byte for byte rather than a
list of the surfaces someone thought to name. Refs, config, reflogs, hooks and the object
database are all in there, and so is whatever this paragraph has not anticipated: a file
nobody predicted still produces a warning naming it. Those warnings are separate from the
filesystem ones because they are real changes to the source repository without being an
escape. Report them too, and read them in this order. A config warning comes first —
`core.hooksPath` and the `alias.*` keys decide what later commands in that repository
execute — and a hook warning is the same danger arriving directly. A reflog warning is
next: ref tips say where the branches are now, the reflog is the only record of where they
were, so a shrinking one means the repository lost its way back rather than merely moving.
An object warning is judged by which object IDs the repository can still serve from
its own object store — local loose objects and local pack indexes — not by storage
layout or by a store reached through `objects/info/alternates`, so a change inside
that borrowed store produces no warning, a change to the pointer file itself still
does, and a `git repack` or `git gc` that keeps every object produces none either. A
`deleted` line means an object the repository could serve before the review is gone,
or that mutable metadata deciding which objects are reachable (such as
`objects/info/alternates`) was removed. A `created` line is the addition side of the
same comparison — a new object the repository can now serve, new reachability
metadata, or a loose object whose bytes no longer hash to its own name, since that
corruption is tracked as content rather than as an object ID. Either mechanism that
makes a loose object stop verifying — a hash that no longer matches, or a zlib stream
that never reaches its own end — reads as a `created` line on that path whether or
not the object was present before the review, since only an object that no longer
verifies is ever entered into that map.
`--no-network` keeps the hard read-only sandbox and skips the disposable worktree — worth
passing when the change under review touches nothing GitHub can answer for, since no CI
or PR claim then needs settling. The runner writes the final answer to
`codex-review-rN.md` and the JSONL event stream to `codex-review-rN.jsonl` beside the
prompt; use the exact paths it prints. It does not need `OPENAI_API_KEY` when `codex
login status` reports a saved ChatGPT login. The Codex process does not inherit Claude's
conversation: the generated package, its referenced files, and repository access are
its complete task context.

A review of a real change takes 10 to 20 minutes, longer than a foreground Bash call is
allowed to run, so start the runner **in the background** and let its completion
notification bring you back. Do not poll the JSONL or sleep in a loop while it runs:
nothing in the stream changes what you do next, and every poll costs a turn. The runner
kills the whole Codex process group after `--timeout-minutes` (default 30) and reports
the retained JSONL path, so a hung review cannot outlive the cap.

Do not start an interactive login, retry with `--dangerously-bypass-approvals-and-sandbox`
or any other weakening beyond what the runner already sets, or fall back to reviewing the
change yourself. If authentication is unavailable, report the runner's
login instruction and stop. If Codex fails or times out, report the error and retained
JSONL path and stop. Never add `--with-diff` merely because Codex is a separate process;
it runs on the same machine and reads the repository directly.

Codex loads skills from `~/.agents/skills` on its own. Nothing named `codex-review`
may live there: a copy written for the packaging side describes the wrong role to the
reviewer, and the last time one was present Codex announced it was "using the
codex-review skill" before starting the review.

When the runner succeeds, read `codex-review-rN.md` in full and continue directly to
triage. Do not ask the user to copy or paste the review.

## 3. Triage the Codex findings

The Codex prompt asks for five parts: a findings table, `## Blocking`, `## Per axis`,
`## Plan defects` and `## Verified for this review`. Read the last one first — it tells
you which findings were derived from something the reviewer actually ran, and that
changes how much work each row's verification takes, not whether it gets one.

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

**A rejection has to prove itself.** `WRONG` needs the falsification run and its real
output; both `PRE-EXISTING` verdicts need the file quoted at the base SHA, not an
assertion that it was probably always like that. If you cannot produce that evidence, the
verdict is `OPEN` — reported to the user, never dropped. This is deliberate: the cheapest
way for an outside review to become worthless is a triage where anything not instantly
provable quietly disappears, and the rows most likely to be unprovable in five minutes are
the ones about races, cross-process state and things that only fail under load.

`PRE-EXISTING-SUBSYSTEM-REWRITTEN` exists because the split matters. A fault in code this
change did not touch is genuinely someone else's problem. The same fault in the primitive
this change just rebuilt is a decision the user should take knowingly — it was the single
most valuable row in the last real review this workflow received.

Then report the **ledger**, which is the whole point of this step:

```
| # | row (verbatim) | verdict | evidence |
|---|---|---|---|

CONFIRMED n · PLAN-DEFECT n · OUT-OF-SCOPE n · PRE-EXISTING n (n in rewritten subsystems) · WRONG n · OPEN n
```

Every row the reviewer sent appears exactly once, quoted as they wrote it. Nothing is
summarised away: a reader must be able to see what was asked and what became of it, which
is the difference between "the review was mostly rejected" and "five of seven asks were
accepted". Add the reviewer's `## Plan defects` items as `PLAN-DEFECT` rows and the
`## Per axis` verdicts as one closing line — those are the parts a table cannot hold.

`VALID-OUT-OF-SCOPE` rows go to `<repo>/docs/deferred-work.md` with `Source` =
`external review`, following the append rules in
`$PLUGIN/references/deferred-work-ledger.md` — **`Read` first, append
with `Edit`, never `Write` over an existing ledger, never `git add`**. That file is how a
deferral survives the chat it was decided in.

## 4. Route the accepted rows back

Show the user the ledger and ask which `CONFIRMED`, `PLAN-DEFECT` and
`PRE-EXISTING-SUBSYSTEM-REWRITTEN` rows to act on. For the ones they pick, write
`<run>/review-followup.md`:

- `# Task` — one paragraph naming the repo, the worktree and the base SHA, and saying
  these are verified findings from an external review of that range.
- `## Findings to fix` — the accepted rows verbatim, each with the lines you read and the
  evidence that confirmed it. Verbatim matters: a rephrased finding is a new claim nobody
  verified.
- `## Not in scope` — the rejected and deferred rows in one line each with their verdict,
  so the fix run does not re-open a settled row or re-derive a rejection.

Then hand the user the one-liner: `/teamlead:delegate <run>/review-followup.md`. That is the
handoff — fixing is out of scope here, and a confirmed finding that ends its life in a
chat message is the same loss as one that was never reported. Fix rows directly only if
the user explicitly asks you to.
