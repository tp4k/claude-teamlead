# teamlead

A [Claude Code](https://claude.com/claude-code) plugin for delegated work. One
command takes a task from a plan to reviewed commits: the coordinator decomposes
it, dispatches specialist subagents in parallel, verifies what they produce, has
it reviewed on three axes, and triages every finding — and never writes the code
itself.

The separation is the point. A coordinator that starts editing files stops
tracking the other workstreams, and a reviewer that is also the author grades its
own homework. Each role here is a separate agent with its own context, its own
tools and its own report.

## Install

```
/plugin marketplace add tp4k/claude-teamlead
/plugin install teamlead@claude-teamlead
```

## Commands

| Command | What it does |
| --- | --- |
| `/teamlead:delegate <task>` | The full loop in the current tree: plan → validate the plan → implement in parallel workstreams → verify → review (code, security, performance) → triage. Stops for open questions before dispatch, and stops for good when the rework cap says the plan itself is wrong. |
| `/teamlead:cycle <task>` | `delegate` plus the tree it runs in: a fresh worktree off `origin/main`, bootstrapped with the repo's own setup command, the session moved into it and named after the work, then `delegate`, then `codex-review`. |
| `/teamlead:codex-review [target]` | An independent review by [Codex](https://github.com/openai/codex), given the run's task, plan and diff, with every finding triaged into a ledger where each row appears once with the evidence that settled it. |

Nothing in any of the three merges or pushes. There is no flag that makes them.

## What gets installed

Five agents — `implementer`, `planner`, `plan-validator`, `verifier`, `writer` —
and three hooks the plugin carries itself so that no one has to hand-edit
`~/.claude/settings.json`:

- **`PreToolUse` (allow)** pre-approves the report writes every teamlead agent
  makes inside its own state directory. It only ever grants: a write anywhere
  else gets no decision and follows the normal permission flow.
- **`PreToolUse` (deny)** refuses an implementer's write outside the fenced
  `scope` block of its own brief. It answers only for implementer subagents whose
  brief declares a fence, so every other write in the session — including yours —
  is untouched. Set `"scopeFence": false` to turn it off.
- **`UserPromptSubmit`** names the session after the run. It never overwrites a
  title you chose yourself.

Hooks are installed user-wide, so all three are written to stay silent outside a
teamlead run.

## Requirements

- **Claude Code**, recent enough to support plugins.
- **git**. `/teamlead:cycle` also needs `git worktree`.
- **Python 3.9+** for the bundled scripts. Standard library only — nothing to
  install, no virtualenv.
- **[Codex CLI](https://github.com/openai/codex)** with a saved login
  (`codex login`), for `/teamlead:codex-review` only. `delegate` runs without it.
  Set `CODEX_BIN` if the binary is not on `PATH`.

## Configuration

Every setting is optional; no config file at all is a supported state. Copy
[`config.example.json`](config.example.json) to `~/.teamlead/config.json` and keep
the keys you want:

| Key | Default | Meaning |
| --- | --- | --- |
| `adrPath` | unset | Root of your ADR store. Unset, or set to a directory that does not exist, falls back to `<cwd>/docs/adr`, then skips ADRs entirely. |
| `adrSubdir` | `null` | Subdirectory within `adrPath`. |
| `reworkCap` | `3` | Rework rounds a workstream gets before triage must stop. |
| `maxAgeDays` | `30` | A run directory older than this is prunable. |
| `keepLastPerRepo` | `5` | ...unless it is among the newest N runs of its repo. |
| `scopeFence` | `true` | Whether the scope-fence hook refuses out-of-scope implementer writes. |

A `<repo>/.teamlead.json` of the same shape overrides the global file for that
repo. A value of the wrong type is skipped rather than fatal: the next tier, then
the default, answers instead.

## State

Runs, worktree handover files and your config live under `$TEAMLEAD_HOME`,
default `~/.teamlead/` — deliberately outside the plugin, because
`claude plugin update` replaces the plugin's own directory. Set `TEAMLEAD_HOME`
to move all of it.

## Tests

No pytest, no dependencies — a suite that needs an install is a suite nobody
runs:

```sh
for suite in scripts/test_*.py; do python3 "$suite"; done
ruff check .
```

CI runs the same two things on Python 3.9 through 3.13.

## License

[MIT](LICENSE).
