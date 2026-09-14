# The run directory — where a run's state lives

Every `/teamlead:delegate` invocation gets one directory, outside the plugin:

```
~/.teamlead/runs/<repo-name>/<YYYY-MM-DD-HHMM>-<slug>/
```

Outside deliberately: `claude plugin update` replaces the plugin directory, so state kept under it is state a version bump can delete, and a plugin someone else can install cannot carry one machine's briefs and repo paths. `$TEAMLEAD_HOME` moves the whole tree if you want it elsewhere (`scripts/paths.py`); every script resolves it, so no path here is ever typed by hand.

It is created by `scripts/new_run.py <repo> "<slug>" --task-file <task.md>` (which also prunes old runs per `~/.teamlead/config.json`) and printed as `RUN_DIR=<path>`. The coordinator waits for each phase's files with `scripts/wait_for.py --timeout <s> <files>` (one blocking call per phase; prints a routing line per file). Below, `$RUN` means that path.

`scripts/run_state.py $RUN` reads the same layout in the other direction: given the file set, it prints which step of the loop the run is on and the one next action, exiting 1 when that action is the user's. Use it on **resume** — a new session, or after a compaction — where `wait_for.py` is the wrong tool: it waits for an agent, and the agents of a previous session are all dead. That is why a missing file there means "spawn it again" rather than "wait", and why a resumed coordinator should never poll.

## Why files, not prompt text

Measured across six eval runs, the coordinator spent 10–15 minutes per run retyping context into briefs — the spec excerpt, the plan's acceptance and test plan, the implementer's report tail, the verifier output — 19 KB of a 23 KB reviewer brief was text that already existed somewhere. Retyping is slow, it sits on the critical path, and it fills the coordinator's context with copies. So every agent **writes its own report to `$RUN`** and every later agent **reads what it needs from `$RUN`**. A brief is a pointer: which run files are its inputs, which file to write — and, for a reviewer, which role file to read. The coordinator (or the workflow script) only ever passes paths and a few routing facts.

Agents may write to `$RUN` without prompts: the plugin's `hooks/allow-run-writes.py` approves `Edit`/`Write` under `~/.teamlead/runs/` and `~/.teamlead/tasks/` (the cycle's handover files) and nothing else, so no settings entry has to be added by hand. Nothing under `$RUN` is ever committed to the repo. In the repo tree, implementers write code within their brief's scope — enforced, not only asked: `hooks/deny-out-of-scope-writes.py` resolves the implementer's brief from its own dispatch prompt and refuses an `Edit`/`Write` outside the fenced ```scope block in its `## Scope` section. It answers only for implementer subagents whose brief declares that fence, so a hand-written brief, an older run or anyone else's write gets no decision at all. `teamlead:writer` owns exactly one file per invocation — the living sections of `$RUN/plan.md`, a new ADR, `docs/deferred-work.md`. The two repo files are written but **never committed**: the user commits them when they choose. The plan is deliberately not among them; it stays a run artifact, so no teamlead run ever leaves an untracked `PLAN.md` behind for the user to commit or ignore.

## Layout

| File | Written by | Read by | Contents |
|---|---|---|---|
| `repo.txt` | `new_run.py` | everyone | absolute repo path, one line |
| `task.md` | coordinator via `new_run.py --task-file` | planner, reviewers, scribe | the user's task **verbatim**, flags stripped, plus a `flags:` line (`--no-perf-review`, `--no-security-review`, `--adr`, or `none`) |
| `plan.md` | planner (opus); writer appends the living sections on `complex=yes` | validator, coordinator, reviewers, triage, scribe | the full plan: goal, workstream table (`WS-1`…), per-workstream block with inline **verbatim spec excerpt**, observable acceptance, test plan, `reuse:` / `do not reuse:` / `keep because:` lines, the three review axes, dependency DAG, `Decisions taken`, project forbiddens, task-wide anti-scope (`roles/planner.md`). On a complex task it continues as a living ExecPlan — `Progress`, `Surprises & Discoveries`, `Decision Log`, `Outcomes & Retrospective`, kept current by `teamlead:writer` (`references/execplan-template.md`). This is the artifact that has to be self-contained enough to resume a run from cold |
| `questions.md` | planner; coordinator appends `## Answers` | coordinator, implementers (via brief), scribe | numbered open questions, each with an `options:` list of 2–4 lettered, self-describing candidate answers, the `recommended:` letter, the `rests on:` spec/code line and the `otherwise:` consequence — the coordinator relays each question as its own `AskUserQuestion` card built from those options, so they are menu entries, not prose. `## Answers` is one `n. <chosen option, verbatim>` line per question plus, when a scope card was on the table, `scope: <letter> — <option>`. Empty list ⇒ first line `No open questions.`; ends with `## Routing` = the planner's `PLAN_WRITTEN` block. Written **last** by the planner — the coordinator's `scripts/wait_for.py` waits on this file as the whole-plan-on-disk signal |
| `briefs/impl-ws<N>-r1.md` | planner | implementer, verifier, reviewers | round-1 implementer brief for workstream N — workstream-specific parts only (scope, spec excerpt, acceptance, test plan, forbiddens, verification commands with cwd, anti-scope). The generic rules live in `roles/implementer.md`, which the brief tells the implementer to read first |
| `briefs/impl-ws<N>-r<M>.md` (M ≥ 2) | triage (agent or coordinator) | implementer, verifier, reviewers | rework brief: the merged findings rows + verifier output if any + test-plan additions + pointer to the previous brief |
| `plan-validation.md` | plan validator (opus) | coordinator / planner fix | `PLAN_VALID` / `PLAN_NEEDS_FIX` + findings table + the `Smaller / none` scope section — lettered options whose text before the colon names the option on its own (the coordinator relays them as the labels of a scope card), their prices and a `Recommend:` line when a cut exists, `Smaller: none` when it does not; never a blocker either way. See `roles/plan-validator.md` |
| `implementer-ws<N>-r<M>.md` | implementer (sonnet) | verifier, reviewers, triage | the structured report (status, confidence, commits, test plan, verification, questions, refactor requests) |
| `verifier-r<M>.md` | verifier gate (sonnet) | reviewers, triage | `OUTCOME: PASS \| FAIL \| CANNOT_RUN` + per-command exit codes + output tails + pre-existing analysis |
| `review-r<M>-<axis>.md` | reviewer (opus); axis ∈ `code`, `security`, `perf` | triage | the report in the shape of `review-standard.md` |
| `triage-r<M>.md` | coordinator | next reviewers, the final report | consolidated verdict (worst wins), de-duplicated rows, rows demoted to Notes with the reason, Notes for the user, the re-review set for the next round with the basis per specialist |
| `refactor-decisions.md` | coordinator, appended per decision | ledger writer, the final report | one line per refactor request: `<reject\|defer\|approve> — <what> — <reason> (<files/symbols>)`. Absent when no request was made |
| `final-report.md` | coordinator | user | 5–12 lines: delivered, commits, who did what, manual checks, Notes, deferred |

Round numbering: `r1` is the first implementation of a workstream; every rework increments it. The verifier and reviewers use the round of the workstream they check. With several workstreams in one run, the verifier, reviewers and triage write one file per workstream: `verifier-ws<N>-r<M>.md`, `review-ws<N>-r<M>-<axis>.md`, `triage-ws<N>-r<M>.md`; with one workstream the `ws<N>-` part is dropped. Every prompt says which case applies.

## The pointer brief

Every agent prompt has the same skeleton, and it fits in 15–25 lines:

```
Run directory: $RUN      Repo: <absolute path>      Workstream: WS-<N>      Round: <M>
Inputs: <the $RUN files this role lists, by name, plus anything round-specific>
Output: write $RUN/<file> exactly as the role file specifies, then return <the short return line the role file specifies>.
<the few facts only the sender knows: flags, the axis tag and its reason, the commit list, the re-review set>
```

The five `teamlead:<role>` plugin agents load their own role file, so no brief names one. The reviewers are harness subagent types this plugin does not own, so brief R alone opens with `Role: read and follow <plugin>/references/roles/reviewer.md` and lists its tools.

The return value of an agent is **short and routable** — a verdict line and a file path, never the report. The coordinator reads the file only when it has to decide something the return line does not settle.

## Two rules that fall out of this

- **A report is a file first.** An agent that returns a verdict without having written its file has not finished; the next agent will read an empty slot. Role files say: write, then return.
- **Nobody retypes what is on disk.** If a prompt needs the spec excerpt, it names the workstream block in `plan.md`; if it needs the diff, it names the commits and the agent runs `git show`. The only text that travels inside a prompt is what does not exist in a file yet.
