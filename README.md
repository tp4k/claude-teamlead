# teamlead

A [Claude Code](https://claude.com/claude-code) plugin for delegated work. One
command takes a task from a plan to reviewed commits: the coordinator decomposes
it, has the plan itself reviewed before a line is written, dispatches specialist
subagents in parallel, verifies what they produce, has the result reviewed on
three axes, and triages every finding — and never writes the code itself.

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
| `/teamlead:delegate <task>` | The full loop in the current tree: plan → review the plan → validate the plan → implement in parallel workstreams → verify → review (code, security, performance) → triage. Opens with a card for the run's options, stops for open questions and design findings before dispatch, and stops for good when the rework cap says the plan itself is wrong. |
| `/teamlead:cycle <task>` | `delegate` plus the tree it runs in: a fresh worktree off `origin/main`, bootstrapped with the repo's own setup command, the session moved into it and named after the work, then `delegate`, then `codex-review`. |
| `/teamlead:codex-review [target]` | An independent review by [Codex](https://github.com/openai/codex), given the run's task, plan and diff, with every finding triaged into a ledger where each row appears once with the evidence that settled it. |

Nothing in any of the three merges or pushes. There is no flag that makes them.

## Run options

Seven things about a run are yours to decide: whether the plan gets an outside
review, whether you get a version of it written for a human, and which of the
specialist reviews run at the end. You do not have to remember any of them.
`delegate` opens with a card for the ones worth deciding per run, and every
answer — typed, configured or clicked — is resolved by one script and written to
`$RUN/config.json`, so a resumed or compacted run can still say what it was
asked to do.

| Option | Flag | Values | Effect |
| --- | --- | --- | --- |
| `codexPlanReview` | `--codex-plan-review=<v>` | `off` · `hard` · `always` | An independent [Codex](https://github.com/openai/codex) review of the plan, before any code exists. `hard` runs it only when the planner called the task complex. |
| `opusPlanReview` | `--opus-plan-review=<v>` | `off` · `fallback` · `always` | The same review by the in-session `teamlead:plan-reviewer`. `fallback` runs it only when Codex could not. |
| `humanReadablePlan` | `--with-human-readable-plan=<v>` | `off` · `generate` · `pause` | Writes `$RUN/plan-human.md` — the plan as prose, for reading rather than for dispatch. `pause` also holds the run until you have read it. |
| `securityReview` | `--security-review=<v>`, `--no-security-review` | `off` · `when-needed` · `on` | The security reviewer at the end. `when-needed` spawns it only for workstreams the planner tagged as attacker-reachable. |
| `perfReview` | `--perf-review=<v>`, `--no-perf-review` | `off` · `when-needed` · `on` | The performance reviewer. `when-needed` spawns it only for workstreams the planner tagged as on a hot path. |
| `codexCodeReview` | `--codex-code-review` | `off` · `on` | Whether the closing report hands you the `/teamlead:codex-review` one-liner for the finished tree. |
| `adr` | `--adr` | `off` · `on` | Whether the run records its decisions as an ADR. |

Two flags decide how much the run asks you: `--use-config-options` skips the
options card and takes your config as the answer, and `--autopilot` skips the
card and every other stop that can be skipped. An explicit
`--with-human-readable-plan=pause` still stops, because a flag that names a stop
is a later and more specific instruction than one that waives stops in general.

Precedence, highest first: **card answer → flag → `<repo>/.teamlead.json` →
`$TEAMLEAD_HOME/config.json` → built-in default.** The card beats the flag
because you see the card after you typed the flag — it is your later word on the
same question.

A bad value is treated differently depending on where it came from. A typo in a
config file is skipped and the next tier answers; a typo in a flag stops the run
and names the valid values. The asymmetry is the point: a config is edited once
and read for months, so a stopping rule there breaks runs that have nothing to
do with the typo — while a flag was typed seconds ago by someone watching the
output, and quietly ignoring it would run the whole loop in a mode they did not
ask for.

`when-needed` depends on the planner's per-workstream tags, which the scope
fence is what makes meaningful. With `"scopeFence": false` both `when-needed`
settings are promoted to `on` rather than silently becoming a coin flip — an
unfenced run cannot tell you which files a workstream will touch.

## What gets installed

Six agents — `implementer`, `planner`, `plan-reviewer`, `plan-validator`,
`verifier`, `writer` — and three hooks the plugin carries itself so that no one has to hand-edit
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
  (`codex login`), for `/teamlead:codex-review` and for the plan design review.
  Both are optional — `delegate` runs the whole loop without it, and a plan
  review that cannot start is reported, never fatal. Set `CODEX_BIN` if the
  binary is not on `PATH`.

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
| `planValidatorPasses` | `1` | How many falsification passes the plan validator makes. `2` costs a second pass to catch what the first one's fixes broke. |
| `codexPlanReviewAxes` | all four | Which of `decomposition`, `task-fit`, `acceptance`, `design-fit` the plan design review covers. |
| the seven [run options](#run-options) | `off` | Same keys, same values as the flags — a config entry is how you stop typing one. |

A `<repo>/.teamlead.json` of the same shape overrides the global file for that
repo. A value of the wrong type is skipped rather than fatal: the next tier, then
the default, answers instead.

Every run option defaults to `off` **in code**, so a reader of `config.json`
never has to know which keys are secretly on. The security and performance
reviews are the exception in practice and not in the code: the first run seeds a
config containing `"securityReview": "on"` and `"perfReview": "on"`, which is
what keeps them running the way they did before options existed. It is an
ordinary config file with a note in it — edit or delete those two lines freely,
and nothing reseeds them.

## State

Runs, worktree handover files and your config live under `$TEAMLEAD_HOME`,
default `~/.teamlead/` — deliberately outside the plugin, because
`claude plugin update` replaces the plugin's own directory. Set `TEAMLEAD_HOME`
to move all of it.

A run directory holds the whole paper trail: `plan.md` and the briefs the
coordinator dispatches from, `config.json` with the resolved options and where
each one came from, `plan-review-package/` and `plan-triage.md` from the plan
design review, the agents' own reports, and — when you asked for one — `plan-human.md`,
which is the file to read if you want to know what the run is about to do.

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
