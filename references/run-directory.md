# The run directory — where a run's state lives

Every `/teamlead:delegate` invocation gets one directory, outside the plugin:

```
~/.teamlead/runs/<repo-name>/<YYYY-MM-DD-HHMM>-<slug>/
```

Keep state outside the plugin because updates replace its directory. Installed plugins must not contain one machine's repository paths or briefs. `$TEAMLEAD_HOME` changes the state root through `scripts/paths.py`. Scripts resolve these paths.

`new_run.py <repo> "<slug>" --task-file <task.md>` creates the directory and prunes old runs according to config. It prints `RUN_DIR=<path>`. `$RUN` means that path.

Use one `wait_for.py --timeout <s> <files>` call per active phase. It prints each file's routing line.

On resume or after compaction, run `run_state.py $RUN`. It reads the files and prints the next step and action. Exit 1 means the user must act. In a new session, earlier agents no longer run. A missing output requires redispatch, not polling or waiting for the old agent.

## Why files, not prompt text

Across six evaluation runs, retyped context cost 10–15 minutes per run. One 23 KB reviewer brief contained 19 KB already present in files. Repeating it delays dispatch and consumes context.

Each agent writes its report under `$RUN`. Later agents read the required files. Briefs primarily supply input paths, output paths, and routing facts. Reviewer briefs also identify the role reference and settled decisions.

The allow-run-writes hook approves Edit and Write under runs and cycle task directories. No one needs to edit settings manually. Do not commit run artifacts to the repository.

Implementers write within their briefs. The scope hook reads the dispatch prompt and active fence, then refuses Edit or Write outside it. It makes no decision for other agents or briefs without a fence.

The writer owns one assigned file per invocation: living plan sections, a human plan, an ADR, or deferred-work rows. The user decides whether to commit generated ADRs or ledger files. Keep the plan outside the repository.

## Layout

| File | Written by | Read by | Contents |
|---|---|---|---|
| `repo.txt` | `new_run.py` | everyone | absolute repo path, one line |
| `task.md` | coordinator via `new_run.py --task-file` | planner, reviewers, scribe | the user's task **verbatim**, flags stripped, plus a `flags:` line (`--no-perf-review`, `--no-security-review`, `--adr`, or `none`) |
| `plan.md` | planner (opus), with living-section writer updates for complex tasks | validator, coordinator, reviewers, triage, scribe | Goal and workstreams. Each stream contains a verbatim spec, acceptance, tests, reuse guidance, review tags, and verification commands. Also contains dependencies, decisions, project rules, and anti-scope. Complex plans append Progress, Surprises & Discoveries, Decision Log, and Outcomes & Retrospective. Keep enough context for a fresh session. |
| `questions.md` | planner, then coordinator for Answers | coordinator, implementers, scribe | Questions with 2–4 lettered options, recommendation, evidence, and alternative consequences. Answers contain verbatim selections and applicable design/scope decisions. With no questions, begin `No open questions.` End with the PLAN_WRITTEN block under Routing. Write this file last as the plan-completion signal. |
| `briefs/impl-ws<N>-r1.md` | planner | implementer, verifier, reviewers | Workstream scope, quoted spec, acceptance, tests, rules, protected files, and verification commands with cwd. The implementer agent loads its generic role rules independently. |
| `briefs/impl-ws<N>-r<M>.md` (M ≥ 2) | triage | implementer, verifier, reviewers | Previous-brief pointer, merged findings, any verifier-output pointer, and test additions. |
| `plan-validation.md` | validator (sonnet) | coordinator, planner in Fix mode | PLAN_VALID or PLAN_NEEDS_FIX, factual findings, and scope observation. For a real cut, supply labeled choices, costs, and Recommend. Otherwise use Smaller: none. Scope observations do not change the verdict. |
| `implementer-ws<N>-r<M>.md` | implementer (sonnet) | verifier, reviewers, triage | Status, confidence, commits, TDD evidence, freeze result, verification, probes, questions, and refactor requests. |
| `verifier-r<M>.md` | verifier (sonnet) | reviewers, triage | PASS, FAIL, or CANNOT_RUN with per-command exit codes, output, and touched-file analysis. |
| `review-r<M>-<axis>.md` | full reviewer (opus) or specialist sanity reviewer (sonnet) | triage | Code, security, or performance report following review-standard.md. |
| `triage-r<M>.md` | coordinator | later reviewers, final report | Worst verdict, merged defects, demotions and reasons, user Notes, and next review set with each specialist's basis. |
| `refactor-decisions.md` | coordinator | ledger writer, final report | Append `<reject\|defer\|approve> — <what> — <reason> (<files/symbols>)`. Omit the file when no request exists. |
| `final-report.md` | coordinator | user | Delivered behavior, commits, roles, manual checks, Notes, and deferred items in 5–12 lines. |

Use r1 for initial implementation. Increment the round for each rework. Verification, reviews, and triage use the workstream's round.

For multiple workstreams, use `verifier-ws<N>-r<M>.md`, `review-ws<N>-r<M>-<axis>.md`, and `triage-ws<N>-r<M>.md`. For one workstream, omit the `ws<N>-` infix. Every prompt must identify the applicable convention.

For a same-round verification retry, first wait for every current-wave verifier and reviewer to finish. Run `archive_reports.py $RUN <all current-wave verifier, review, and triage paths>` before redispatch. The script moves existing reports into a unique directory under `$RUN/report-history/`. This preserves evidence and removes stale routing files. Keep implementer reports, briefs, and earlier rounds in place. Wait on the original report paths for the new attempt.

## The pointer brief

Every agent prompt has the same skeleton, and it fits in 15–25 lines:

```
Run directory: $RUN      Repo: <absolute path>      Workstream: WS-<N>      Round: <M>
Inputs: <the $RUN files this role lists, by name, plus anything round-specific>
Output: write $RUN/<file> exactly as the role file specifies, then return <the short return line the role file specifies>.
<the few facts only the sender knows: flags, the axis tag and its reason, the commit list, the re-review set>
```

The six pipeline agents load their own role files. Their briefs do not name those roles. The reviewers are harness subagent types this plugin does not own, so brief R alone opens with `Role: read and follow <plugin>/references/roles/reviewer.md` and lists its tools.

The return value of an agent is **short and routable** — a verdict line and a file path, never the report. The coordinator reads the file only when it has to decide something the return line does not settle.

## Two rules that fall out of this

- **Write before returning.** A return line without its report leaves the next agent without an input.
- **Point to existing context.** Name the workstream in plan.md for specs. Name commits for diff inspection. Add only new routing facts. The settled-decision exception copies decisions and accepted consequences into reviewer briefs as required by delegate.
