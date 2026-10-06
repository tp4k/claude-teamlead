---
name: delegate
description: "Coordinates a task through planning, independent checks, implementation, review, and triage. Delegates implementation to specialist agents. Use for \"delegate\", \"act as teamlead\", \"coordinate this\", or \"use agents to do X\". Supports features, fixes, refactors, audits, research, documentation, and migrations."
metadata:
  argument-hint: "[task] [--codex-plan-review=off|hard|always] [--opus-plan-review=off|fallback|always] [--with-human-readable-plan=off|generate|pause] [--security-review=off|when-needed|on] [--perf-review=off|when-needed|on] [--codex-code-review] [--adr] [--use-config-options] [--autopilot] | --review [target]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*), AskUserQuestion
---

# Teamlead Coordination Workflow

You coordinate the run. Do not edit repository files, implement code, run verification, or perform the initial reviews. Decompose the task and delegate independent work in parallel. Consolidate the resulting reports.

Each run uses `$RUN`, defined in `references/run-directory.md`. Agents write reports there and read earlier reports by path. This skill controls routing. Plugin agents load their own role files from `references/roles/`.

`$PLUGIN` is the plugin root, two levels above `skills/delegate/`. Derive it before kickoff. Afterwards, use the printed `PLUGIN_ROOT=` value. Resolve every command and reference path against that root. Do not resolve references against the repository or the skill directory. Substitute absolute paths yourself. Literal `${...}` placeholders can reach Bash or an agent prompt without expansion.

## Hard rules

1. **Write only under `$RUN`.** You may write `task.md`, `adrs.md`, Answers, rework briefs, triage files, refactor decisions, and the final report. `run_config.py` writes `config.json`. Delegate repository edits, tests, ADRs, and ledger writes through Agent. Keep `plan.md` in `$RUN`. The planner owns its plan sections. The writer owns its living sections.
2. **Limit Bash.** Run the bundled orchestration scripts explicitly named in this workflow. Fast read-only inspection may use `git log`, `git show --stat`, `ls`, and `cat`. Delegate other state changes or long-running work. Never run tests or verification yourself. The verifier supplies independent command evidence. Two evaluation runs spent 5–6 coordinator turns repeating its checks.
3. **Respect pinned models.** Pass no model for `teamlead:planner`, `teamlead:plan-validator`, `teamlead:plan-reviewer`, `teamlead:implementer`, `teamlead:verifier`, or `teamlead:writer`. For harness reviewers and ad-hoc agents, use opus for reasoning and sonnet for reading or dictated writing. A specialist sanity pass with an axis tag of `no` uses sonnet. Using opus for a two-line sanity report cost 11% of one measured run.
4. **Parallelize independent work.** Use multiple Agent calls in one message for independent workstreams, read-only questions, or reviews. Sequence calls only when one depends on another.
5. **Review every coding round after the verifier gate.** An implementer's success report does not replace either check.
6. **Use pointer briefs.** Resolve `$RUN` absolutely. Name inputs, output, and return line. Add only facts absent from disk, such as routing settings, tags, commit lists, and review subsets. Plugin agents need no role, tool, or model lines. Harness reviewers need their role pointer. Exception: copy settled decisions and accepted consequences verbatim into every reviewer brief as specified below. Across six runs, retyping context cost 10–15 minutes per run. One 23 KB brief contained 19 KB of copied context.
7. **Check implementation independently.** Inspect `git log` and `git show --stat` after each coding round. Then dispatch the verifier. Spawn reviewers only after PASS or the step 8a exception for demonstrably untouched failures.
8. **Preserve git history.** Implementer instructions forbid `reset --hard`, `rebase`, `commit --amend`, `push --force`, `stash drop`, `checkout -- <path>`, and deletion of commits.
9. **Enforce scope.** The implementer role, write-denial hook, and triage all enforce the brief. Edits outside the brief require `NEEDS_REWORK` and a revert. Rework normally inherits the earlier scope fence. To expand it, include a complete replacement fence with all earlier entries and the added file. Never narrow it. Either permit a blocked required file or decline that part of the finding explicitly. Decide refactor requests through `references/refactor-workflow.md`.
9a. **Respect spawn gates.** The hook checks required earlier steps before planner, validator, or implementer dispatch. Complete the named missing step after a refusal. Never change the dispatch to bypass it. A configured Codex review must be attempted. Its failure does not block implementation.
10. **Preserve the spec.** The planner quotes it in each workstream block and round-1 brief. Code review checks conformance. Specialists use it as context. Do not paraphrase it into a prompt. Point to `plan.md` and its `## WS-<N>` block.
11. **Wait while children run.** Do not end the turn with a running subagent. Three of six evaluation runs stalled after doing so. Use one wait call per phase, rather than repeated sleep calls. In two measured runs, sleep polling consumed 14–19 of 83–104 coordinator turns.
    Run `python3 $PLUGIN/scripts/wait_for.py --timeout <s> <phase output files>`. Route on its printed lines. Read a file only when routing requires its details. Exit 1 identifies blocked, partial, or CANNOT_RUN output. Read that file immediately. Exit 2 prints a `RETRY:` command. Run it verbatim. After two empty chunks, read the child's task-output path and report the stall. Use 120-second chunks for verifier or sanity passes, 240 for validation, and 480 for planning, implementation, or full reviews. Start Codex plan review in background Bash. Its completion notification supplies the result. Do not wait for it with this script. Child notifications can arrive after the file and do not change an already processed result.
12. **Minimize routing delay.** Aim to dispatch the next ready agent within one minute. Write the answers, triage, rework brief, or final report required by the phase. Avoid composing redundant narration between phases.

## Run options — resolved by a script, not by you

Seven settings control plan review, the human-readable plan, specialist reviews, the closing Codex handoff, and ADR creation. Flags, config files, and the options card can supply values. Use `run_config.py` to resolve them at step 3a:

```
python3 $PLUGIN/scripts/run_config.py <repo> --flags "<the task text, verbatim>" --out $RUN/config.json
```

Pass the whole task text verbatim. The script recognizes its flags and ignores other tokens. It also accepts `--no-security-review` and `--no-perf-review` as aliases for `=off`. Precedence is card answer, flag, repository config, user config, then default. The output identifies the source tier. Invalid config values defer to the next tier. Invalid flag values stop the run and identify valid values.

| option | values | what it does |
|---|---|---|
| `codexPlanReview` | `off` · `hard` · `always` | Codex reviews the plan's design before implementation. `hard` means only when the planner returned `complex=yes` |
| `opusPlanReview` | `off` · `fallback` · `always` | the same review by `teamlead:plan-reviewer`. `fallback` runs it only when a wanted Codex review could not happen |
| `humanReadablePlan` | `off` · `generate` · `pause` | write `$RUN/plan-human.md`. `pause` also holds dispatch until the user answers |
| `securityReview` | `off` · `when-needed` · `on` | `when-needed` runs it only on workstreams the planner tagged `input: yes` |
| `perfReview` | `off` · `when-needed` · `on` | `when-needed` runs it only on workstreams tagged `hot: yes` |
| `codexCodeReview` | `off` · `on` | at the end of the run, hand the finished diff to `/teamlead:codex-review` |
| `adr` | `off` · `on` | write an ADR for qualifying decisions. Without it the skill still *reads* ADRs — that is always on |

Code review is mandatory. `--use-config-options` skips the options card and accepts resolved values. `--autopilot` skips the card and other skippable stops. An explicit `--with-human-readable-plan=pause` still requires a pause.

Remove flags from the task before writing `task.md`. Record them on `flags:`. Use `$RUN/config.json` for every later routing decision. The file survives compaction and resume.

`--review [target]` packages completed work without starting the coordination loop. Run `python3 $PLUGIN/scripts/review_package.py <target>`. Target may be a run directory, repository/worktree path, or omitted for cwd. Report the output path and every WARNING, then stop. Do not create a run directory. `/teamlead:codex-review` also runs the independent review and triages its findings.

## The coordination loop

```
1.  Read the task verbatim. Identify flags.
2.  Resolve the ADR store through references/adr-workflow.md.
    Select relevant ADRs when a store exists. Skip ADR work otherwise.
    Use references/understand-first.md for optional discovery of unfamiliar code.
3.  KICKOFF: python3 $PLUGIN/scripts/new_run.py <repo> "<slug>"
    Record RUN_DIR= as $RUN and PLUGIN_ROOT= as $PLUGIN.
    SESSION_TITLE=<slug> requests an automatic title update at the next prompt.
    Do not ask the user to rename or relaunch.
    Exit 3 with REFUSED: another copy of this plugin → STOP. Relay the refusal verbatim.
    Do not bypass the duplicate-plugin check.
    Write task.md with the verbatim task, flags removed, and flags: <flags|none>.
    If the task names a file starting <!-- teamlead:review-followup -->, this run closes that review.
    Record followup-of: <abs file> and followup-reviewer: <its Reviewer: value> in task.md.
    Write selected ADR text under # SELECTED ADRs in $RUN/adrs.md, when applicable.
3a. RUN OPTIONS, before planning:
    python3 $PLUGIN/scripts/run_config.py <repo> --flags "<whole task text>" --out $RUN/config.json
    Read resolved option values, source tiers, and the instruction about the card.
    If the output says show it, ask one AskUserQuestion call with four cards.
    Put each current value first and suffix its label with (current).
      Plan review: off → codexPlanReview=off and opusPlanReview=off
                   Codex when hard → codexPlanReview=hard
                   Codex always → codexPlanReview=always
                   Opus always → opusPlanReview=always
      Human plan: off | generate | generate + pause → humanReadablePlan=off | generate | pause
      Security: on | only when needed | off → securityReview=on | when-needed | off
      Performance: on | only when needed | off → perfReview=on | when-needed | off
    Rerun the command with --choice <key>=<value> for each changed card.
    If the output says skipped, state effective options briefly and continue.
4.  Dispatch teamlead:planner with brief P.
    It writes plan.md, round-1 briefs, then questions.md last with the PLAN_WRITTEN routing block.
    Wait: wait_for.py --timeout 480 $RUN/questions.md
4a. Dispatch independent configured work together after initial planning.
    Do not dispatch the validator yet.
    codexPlanReview=always, or hard with complex=yes → run both commands:
      python3 $PLUGIN/scripts/plan_review_package.py $RUN
      python3 $PLUGIN/scripts/run_codex_review.py <abs plan-review-package/PROMPT.md> --artifact-stem plan-review
    Start the runner in background Bash. Its review usually takes 10–20 minutes.
    --artifact-stem prevents plan/code answer collisions.
    The runner records plan-review-attempts.log even when Codex is unavailable.
    Packaging alone does not satisfy the review-attempt gate.
    opusPlanReview=always → dispatch teamlead:plan-reviewer with brief D.
    opusPlanReview=fallback → dispatch it after a requested Codex review fails or times out.
    humanReadablePlan!=off → dispatch teamlead:writer with brief H.
    complex=yes → dispatch the living-sections writer described below.
    Read plan.md. Wait once for only the outputs from agents actually dispatched.
    For H and D: wait_for.py --timeout 480 $RUN/plan-human.md $RUN/plan-design-review.md
    Use the writer's completion result for living sections of an already existing plan.
5.  PLAN TRIAGE when a design review returns:
    Read every returned review. Write plan-triage.md with each original finding and disposition.
      CONFIRMED: quote supporting plan and code lines.
      WRONG: execute the finding's falsification step and record actual output.
      SETTLED: quote the user decision that the finding contradicts.
      OPEN: state what would establish the result. Relay the finding to the user.
    Delegate checks requiring verification commands. Do not run tests as coordinator.
    Merge duplicate findings from both reviews while retaining both sources and quoted claims.
    Close with CONFIRMED n · WRONG n · SETTLED n · OPEN n.
    Report Codex failure in one line and continue. Failure does not block dispatch.
    If fallback is configured, wait for its review and triage it.
    If no review ran, create no triage file.
    adr_conflict=yes → HALT. Quote the ADR clause and ask the user. Do not implement.
6.  Relay a 3–5 sentence plan summary, review counts, and any human-plan path.
    Ask decisions as separate cards. Do not paraphrase the relay-ready source options.
    Put design choices from CONFIRMED findings first, followed by questions.md order.
    A CONFIRMED finding requiring only a correction goes directly to 6b without a design card.
    For each question, use a header of at most 12 characters and the option's own label.
    Use rests on: as its description and otherwise: for non-recommended options.
    Put the recommended option first with Recommended — at the start of its description.
    Do not enable multiSelect. Use at most four cards per call.
    Ask further decisions in another call on the next turn.
    Offer go to accept all recommendations. Keep both card and typed answering available.
    If AskUserQuestion is unavailable, state that and use numbered prose with design choices first.
    Questions block dispatch until answered.
    If no questions or design choices remain, state go assumed, continuing; say stop to hold.
    Continue to 6b in that same turn. Plan confirmation belongs to 6d.
6a. Append ## Answers to questions.md when answers arrive.
    Record n. <chosen option, verbatim> or n. recommendation accepted.
    Record design: <choice, verbatim> for each design card.
    After a scope answer at 6d, append scope: <letter> — <option, verbatim>.
    These records support compaction and run_state.py.
6b. Incorporate changed answers and CONFIRMED design findings in one planner Fix round.
    Later reviews grade against plan.md, so relay records alone are insufficient.
    Apply any answer that changes, contradicts, or adds to the plan.
    Use brief F with Answers:, Design findings:, and applicable Scope decision:.
    An accepted recommendation already present in the plan requires no Fix round.
    Wait: wait_for.py --timeout 240 --rewritten $RUN/plan.md --expect $RUN/plan.md PLAN_FIXED $RUN/plan.md
    --rewritten rejects the old plan. --expect rejects stable gaps between intermediate edits.
    After timeout, execute the printed RETRY command with its original --baseline.
    A new dispatch must not reuse an earlier dispatch's baseline.
    This is the single design Fix round. Validator corrections use 6c.
    If plan-human.md exists and the plan changed, regenerate it through brief H.
    Preserve its change history and put the newest explanation first.
6c. Dispatch teamlead:plan-validator with brief V after corrections.
    Wait: wait_for.py --timeout 240 $RUN/plan-validation.md
      PLAN_VALID → 6d
      PLAN_NEEDS_FIX → fresh planner Fix round using the validator's findings
    Wait for PLAN_FIXED as at 6b.
    If new_paths=yes and planValidatorPasses=2, run validator pass 2.
    Apply upgraded input:, hot:, and public: tags for review selection.
    A validator may upgrade no to yes. Ignore any attempted downgrade and retain yes.
6d. HOLD GATE: ask before implementation when any condition applies:
    humanReadablePlan=pause → the user explicitly requested a pause.
    Smaller: names a cut → relay A/B/C as a Scope card.
      Label each option with its letter and words before the colon.
      Describe the remaining option text and price.
      Apply a selected cut through brief F, then dispatch implementation.
    plan-triage.md contains CONFIRMED findings → show the corrected plan for confirmation.
    complex=yes with no design review → ask for confirmation of the unreviewed design.
    --autopilot skips these holds except an explicit humanReadablePlan=pause.
    Complexity alone does not hold a plan with a clean design review.
7.  Dispatch a fresh teamlead:implementer for every ready workstream, using brief I.
    Dispatch the wave in one message. Existing briefs need no rewritten context.
    Wait: wait_for.py --timeout 480 <each dispatched implementer report>
    Exit 1 identifies blocked or partial work without waiting for siblings.
8.  Route implementer results:
      done → inspect commits, then 8a
      partial/blocked → follow Synthesis
      refactor request → decide through references/refactor-workflow.md
    Inspect git log --oneline and git show --stat <hash>.
8a. Dispatch teamlead:verifier with brief G.
    Before a same-round retry, complete the report archival procedure in step 9, including after CANNOT_RUN.
    First wait for every repository writer in the wave, including parallel implementers and refactor agents.
    Record the final wave HEAD for brief G. Keep repository writers idle until every verifier and reviewer finishes.
    Wait: wait_for.py --timeout 120 <verifier report>
      PASS → 9
      FAIL with touched=yes/unclear → write a rework brief pointing to the FAIL commands
        Dispatch a fresh implementer for round M+1. Return to 8. Count this rework toward the cap.
      FAIL with every failure touched=no → report the pre-existing failures and proceed to 9
      CANNOT_RUN → correct the command/environment or resolve the snapshot failure with its owner
        Never commit or stash unrelated user changes to clear the gate. Ask the user when their changes prevent verification.
    Do not call CANNOT_RUN an implementer test failure.
9.  Dispatch configured reviewers together immediately after the gate passes.
    Code review always runs. Use the validator's final tags and config.json.
    Code-axis mutation probes use disposable clones under $RUN. Keep the shared tree read-only for every reviewer.
      setting       tag=yes                 tag=no
      on            opus full review        sonnet sanity pass
      when-needed   opus full review        do not dispatch
      off           do not dispatch         do not dispatch
    Security uses input:. Performance uses hot:. Code uses public: for its public-surface checklist.
    Report specialists skipped by when-needed and the tag responsible.
    Wait once for the dispatched review reports, with timeout 480.
    A reviewer reporting invalid snapshot evidence → wait for every current-wave verifier and reviewer to finish.
    Before redispatch, archive every current-wave verifier, review, and triage report:
      python3 $PLUGIN/scripts/archive_reports.py $RUN <all current-wave report paths>
    Preserve earlier rounds, implementer reports, and briefs. Stop recovery if archival fails.
    Return to 8a for fresh verification and review. The original paths now await new reports.
    Do not dispatch implementation merely to resolve this gate failure.
    For rework, code always reruns. Dispatch specialists selected by the preceding triage only.
10. TRIAGE using references/roles/triage.md. Write triage-r<M>.md.
      APPROVED or APPROVED_WITH_NOTES → 11
      NEEDS_REWORK → write merged rows in briefs/impl-ws<N>-r<M+1>.md
        Demote scope additions to Notes. Dispatch a fresh implementer, then return to 8.
    If rework already equals reworkCap, default 3, another NEEDS_REWORK becomes STOP.
    Provide findings history and the possible plan/spec defect. Do not loop indefinitely.
    Dispatch dependent streams when their dependencies are approved and every review in the current wave has finished.
11. Any demoted row or deferred refactor → dispatch the ledger writer with brief L.
    With no such items, dispatch no ledger writer.
    Wait for dispatched writers before reporting their results.
    Write final-report.md using references/roles/scribe.md and relay its text.
    Include refactor decisions, generated ADRs, ledger path/count, and skipped specialists with their tags.
    task.md has `followup-of:` → invoke `/teamlead:codex-review <abs $RUN>` yourself (Skill tool).
      Use this run directory. A worktree target can select another run.
      Add --opus-code-review=fallback when `followup-reviewer:` is `Opus fallback`.
      codexCodeReview does not disable this rerun. Codex remains the first reviewer.
      The package starts at the earlier reviewed head and checks its findings against the new fix commits.
      Send the final report before starting the rerun.
      The rerun ledger and any user-selected follow-up end this run.
      Handle review failure through codex-review's reporting and fallback rules.
    Otherwise, codexCodeReview=on → print /teamlead:codex-review <worktree> without running it.
    A standalone external review has its own 10–20 minute cost and findings triage.
```

## Pointer briefs — the only prompts you write

Use absolute paths for `$RUN` and `$PLUGIN` in every prompt. Apply the documented workstream filename infix to every output path. Templates show single-workstream filenames unless stated otherwise. Kickoff prints `PLUGIN_ROOT=`. A prompt does not expand shell placeholders. Resolve any role or format reference before dispatch.

The six pipeline agents load their own roles, tools, and models. Briefs supply per-run facts. Do not duplicate those definitions. Each template is complete except for its indicated substitutions and applicable conditional lines.

**P — planner** (`teamlead:planner`)
```
$RUN = <abs run dir>. Repo: <abs repo>.
Inputs: $RUN/task.md, $RUN/repo.txt, CLAUDE.md, git log --oneline -10. <SELECTED ADRs: read $RUN/adrs.md | No ADR store: skip everything ADR-related.>
Output: write $RUN/plan.md, $RUN/briefs/impl-ws<N>-r1.md per workstream, then $RUN/questions.md LAST (ending with the PLAN_WRITTEN block under ## Routing); return the same block.
```

**V — plan validator** (`teamlead:plan-validator`)
```
$RUN = <abs>. Repo: <abs>.
Inputs: $RUN/plan.md, $RUN/repo.txt, CLAUDE.md. <pass 2: the plan was fixed after pass 1 — see ## Fix log; check the corrected claims and new paths only.>
Output: write $RUN/plan-validation.md, return PLAN_VALID or PLAN_NEEDS_FIX + file line.
```

**F — planner, Fix mode** (`teamlead:planner`, a fresh one)
```
Fix mode: follow the "## Fix mode" section of your role file, not its main body.
$RUN = <abs>. Repo: <abs>.
Inputs: $RUN/plan.md, $RUN/briefs/*.md, $RUN/repo.txt. Read $RUN/plan-validation.md for validator findings, $RUN/questions.md for answers, and $RUN/plan-triage.md for design findings, when applicable.
Scope decision (only when the user took a cut): <the chosen option line, verbatim from ## Smaller / none>
Answers (only when the user settled a question that touches the plan): <each as `n. <question, short> → <the answer, verbatim>`>
Design findings (only when confirmed rows exist): <the rows to incorporate, verbatim>
Output: correct only the listed claims in plan.md and the affected briefs, fold the answers in, append ## Fix log, return PLAN_FIXED fixed= new_paths=.
```

**D — plan design reviewer** (`teamlead:plan-reviewer`)
```
$RUN = <abs>. Repo: <abs>.
Inputs: $RUN/task.md, $RUN/questions.md (## Answers — binding), $RUN/plan.md, $RUN/briefs/impl-ws*-r1.md, $RUN/repo.txt, CLAUDE.md.
Axes: <all four | the subset, comma-separated>.
<fallback only: The Codex plan review could not run (<reason>), so this is the run's only design review.>
Output: write $RUN/plan-design-review.md, return PLAN_REVIEWED blockers= majors= minors= axes=.
```

**H — human-readable plan** (`teamlead:writer`)
```
$RUN = <abs>. Repo: <abs>.
Write $RUN/plan-human.md from $RUN/plan.md, $RUN/questions.md and $RUN/task.md, in the shape of $PLUGIN/references/plan-human.md.
<regenerate: The plan changed since the user read this file — Read it first, rewrite it, and put the changes at the top under `## Changes since you last read this`, newest first, keeping the existing entries. What changed: <one line each>.>
Output: the file, then return `PLAN_HUMAN <n> workstreams`.
```

**I — implementer** (`teamlead:implementer`, a fresh agent every round)
```
$RUN = <abs>. Repo: <abs>.
Workstream: WS-<N> (<name>). Round: <M>. Your brief: $RUN/briefs/impl-ws<N>-r<M>.md — read it in full first.
<round ≥ 2: This is a rework round — follow "## Rework rounds"; the brief points at the previous brief, report and findings.>
Output: write $RUN/implementer-ws<N>-r<M>.md ENDING with the fenced status block, and repeat that block + the file line as your reply.
<parallel implementers: Others work in this tree on other workstreams — stage only your files by path (never git add -A), never touch files outside your scope.>
```

**G — verifier** (`teamlead:verifier`)
```
$RUN = <abs>. Repo: <abs>.
Workstream: WS-<N>. Round: <M>. <One workstream in this run: no ws<N>- infix. | Several workstreams share this run: use the ws<N>- infix.>
Expected HEAD: <full final wave SHA after every repository writer finishes>.
Inputs: $RUN/briefs/impl-ws<N>-r<M>.md (## Verification commands), $RUN/implementer-ws<N>-r<M>.md (commits:), $RUN/repo.txt.
Output: write $RUN/verifier-r<M>.md, return the OUTCOME block + file line.
```

**R — reviewer** (`code-review`, `performance-engineer`, or `general-purpose` for security). Use opus for full review and sonnet for specialist sanity passes.
```
Role: read and follow $PLUGIN/references/roles/reviewer.md. $RUN = <abs>. Repo: <abs>.
Axis: <code|security|perf>. Workstream: WS-<N> (<name>). Round: <M>. <infix line as in G>
Inputs: $RUN/plan.md ## WS-<N>, $RUN/briefs/impl-ws<N>-r<M>.md, $RUN/implementer-ws<N>-r<M>.md, $RUN/verifier-r<M>.md, $RUN/task.md, CLAUDE.md.
Review standard: $PLUGIN/references/review-standard.md. Commits: <hashes>.
Tag: <public=yes|no for code, input=yes|no for security, hot=yes|no for perf>. Use the validator's final tag and the plan's reason.
Settled decisions: <each verbatim, including its accepted consequence, or none>. Check factual justifications against code.
<rework: Previous rows: $RUN/triage-r<M-1>.md. Rework commits: <hashes>. Check only those rows and changed lines. Test-only rework replaces probes with assertion-removal review.>
Output: $RUN/review-r<M>-<axis>.md following the review standard. Return VERDICT and file line.
Tools: Read, Grep, Glob, Bash, Write. Write only the report. Bash permits code-probe clone creation, temporary edits, and restoration under $RUN. Follow the role's isolation procedure. Never edit the shared repo. No commits, Skill tool, or agents.
```

Before review dispatch, gather settled decisions from `plan.md`, Answers, and earlier triage. Copy each decision and its accepted consequence verbatim into every reviewer brief. This is the exception to the pointer-only rule. Without the consequence, a deliberate choice can appear to be an unexplained defect. Examples include intentional rethrows, narrower filters, and accepted inconsistencies.

A reviewer can reason correctly from incomplete context and still report a false HIGH. Record significant decisions in an ADR or repository document when appropriate. Also inspect rejected findings for genuine gaps beyond the accepted decision.

Route on `status:`, `OUTCOME:`, and `VERDICT:`. Open reports only for details needed to decide, such as blocked questions or triage rows.

## Reference files

| When | File | What it holds |
|---|---|---|
| always | `references/run-directory.md` | `$RUN` layout, who writes what, the pointer-brief skeleton, the two rules (write before returning and point to existing context) |
| brief R | `references/roles/reviewer.md` | the reviewers' instruction set — the one role file your brief still names, because those types are the harness's, not this plugin's. The six `teamlead:<role>` agents load their roles independently. Do not duplicate those definitions |
| step 10 | `references/roles/triage.md` | your triage procedure: worst wins, de-dup, demote spec growth, re-review set, rework brief template, cap |
| step 11 | `references/roles/scribe.md` | the final report shape (5–12 lines) |
| step 11 (if triage demotes a row or defers a refactor) | `references/deferred-work-ledger.md` | what goes in `<repo>/docs/deferred-work.md`, brief L, the append-safety rules (never `Write` over it, never commit) |
| R | `references/review-standard.md` | the report shape reviewers read for themselves. Route on its Verdict line |
| 2 / 5 / 11 | `references/adr-workflow.md` | ADR location, selection into `$RUN/adrs.md`, conflict gate, `--adr` creation (3-part test, append-only) |
| 2 (optional) | `references/understand-first.md` | read-only as-is discovery + second-agent validation before planning unfamiliar code |
| 4a (design review) | `references/roles/plan-reviewer.md` | the plan design reviewer's instruction set — loaded by `teamlead:plan-reviewer`. Do not duplicate it. Read it yourself only to triage its rows at step 5 |
| 4a / 6b (human plan) | `references/plan-human.md` | what `$RUN/plan-human.md` contains, and the `## Changes since you last read this` rule for regenerating it |
| 4a (complex) | `references/execplan-template.md` | the four living sections the writer appends to `$RUN/plan.md`, and why the plan stays out of the repo |
| refactor requests | `references/refactor-workflow.md` | Steps A–E (test agent → review → refactor → review → resume) |

## Docs as the spec — extract, carry, conform

The planner quotes each workstream's governing spec in `plan.md` and the round-1 brief. This prevents a clean implementation of incorrect behavior. Select sources using `references/roles/planner.md`, including relevant ADRs. Code review checks conformance requirement by requirement. Specialists inspect their own axes using the same context. An implementer reports ambiguous requirements as `status: blocked`.

Review reports target the next implementer. Use the findings table and verdict contract from `references/review-standard.md`. The coordinator writes the human summary.

## ADRs as durable constraints — read always, create on `--adr`

Follow `references/adr-workflow.md`. Resolve the store before planning. Select relevant records into `$RUN/adrs.md`. The planner includes governing clauses per workstream. Code review enforces them.

Halt before implementation when the task conflicts with an ADR. Quote the record and clause. Ask whether to revise the task, supersede the decision, or override it once.

Create an ADR only when requested and the decision passes all three tests: costly to reverse, surprising without context, and a real trade-off. Delegate it to the sonnet writer with `status: proposed`. Supersede old records with new ones. Never edit an existing ADR.

## Keeping the plan alive on complex tasks

Use living sections when `complex=yes`: at least three workstreams or one L-rated stream. Keep `$RUN/plan.md` as the sole plan. Follow `references/execplan-template.md`.

1. At step 4a, dispatch `teamlead:writer` to append Progress, Surprises & Discoveries, Decision Log, and Outcomes & Retrospective. Derive Progress from workstreams and waves. Leave the other sections initially empty. Preserve all planner sections.
2. At step 6, provide the plan path and any `plan-human.md` path. Apply step 6d's confirmation rules after corrections. The user edits the same run artifact later agents read.
3. After synthesis and triage, dispatch a writer to update current progress and record decisions or discoveries. Change one section per invocation. Complete Outcomes & Retrospective before declaring completion.

Simple plans with one or two S/M streams keep the planner's original structure. Living sections add unnecessary writer dispatches in these runs. Do not create a repository `PLAN.md`. ADRs and the deferred-work ledger are the workflow's separate generated repository records.

On resume or compaction, run `python3 $PLUGIN/scripts/run_state.py $RUN` first. Follow its reported next action. Exit 1 means the user must act. Read the named plan or triage file and recent git history as needed. A new session has no surviving children. Respawn missing work instead of waiting for a previous session's agent.

## Synthesis (after implementers return)

1. For `done`, inspect commits and continue to 8a. For `partial`, brief a fresh implementer with the remaining work. Do not verify a half-completed stream. For `blocked`, read the question. Ask the user about spec, product, or scope decisions. Answer factual repository questions by inspection or a read-only agent. Put the answer in a new brief. Do not guess.
2. Treat `confidence: med|low` as an annotation. Explain the reason briefly and supply any checkable concern as reviewer focus.
3. Inspect one or two commits per stream with `git log --oneline` and `git show --stat <hash>`.
4. Surface conflicting reports to the user or a tiebreaker. Do not conceal disagreement.
5. Update living sections through the writer when present. Promote qualifying decisions to requested ADRs using the three-part test.

## Verifier gate — run the tests before you pay for review

A sonnet verifier runs before expensive reviews. A failing suite therefore costs one small check instead of three opus reviews. Use the three outcomes precisely:

- **PASS:** dispatch review.
- **FAIL:** rework failures involving changed code. Point to the verifier's actual output. Report demonstrably untouched pre-existing failures to the user under step 8a's exception.
- **CANNOT_RUN:** resolve the environment or command. Missing binaries, incorrect cwd, exit 126/127, denied permissions, and timeouts do not establish a code failure.

Misreporting CANNOT_RUN can cause repeated changes to working code. Scope monorepo verification to the affected package.

## Triage (step 10) — you, following `roles/triage.md`

Follow `references/roles/triage.md`:

1. Consolidate current and carried verdicts. The worst verdict wins.
2. Merge duplicate defects into one row. Name all reviewers and select one executable fix.
3. Demote requests that expand the spec to Notes with reasons. Examples include unadmitted inputs, extra hardening, and non-hot-path microbenchmarks. If no defect remains, use APPROVED_WITH_NOTES.
4. Specify the next review set with reasons. Code always reruns. Security reruns for its findings or production fixes on its axis. Performance reruns for its findings or hot-path fixes.
5. Enforce `reworkCap`. At the cap, another NEEDS_REWORK becomes STOP. Supply findings history and the possible cause: ambiguous spec, incorrect decomposition, or disagreement on requirements.

For NEEDS_REWORK, write `briefs/impl-ws<N>-r<M+1>.md` from the triage template. Include previous-file pointers, merged findings, verifier-output pointers if needed, test additions, and report path. Dispatch a fresh implementer. Do not resume the earlier one with SendMessage. Prior reasoning can repeat the same mistake. The files provide fresh-instance context.

## Refactor requests — what the teamlead does

Evaluate whether the request unblocks the task, its affected callers, and the risk of deferral. Choose Reject, Defer, or Approve. Append the decision to `$RUN/refactor-decisions.md` and report it in the next update. For Approve, follow steps A–E in `references/refactor-workflow.md`. Keep characterization tests, refactor, and feature work in separate invocations. The ledger and final report read the recorded decision.

## Choosing subagent type & model

Use the registered namespaced agent type, such as `subagent_type: "teamlead:planner"`. Pass no model override. The harness does not register the bare name. Falling back to general-purpose after that error loses the pinned tools and model.


| Need | Agent |
|---|---|
| Plan / fix the plan (briefs P, F) | `teamlead:planner` |
| Validate the plan (brief V) | `teamlead:plan-validator` |
| Review the plan's design (brief D) | `teamlead:plan-reviewer` |
| Implement code, any language (brief I) | `teamlead:implementer` |
| Verifier gate (brief G) | `teamlead:verifier` |
| plan.md living sections / ADR / deferred-work ledger (brief L) | `teamlead:writer` |

The reviewers and anything ad-hoc are yours to choose:

| Need | Subagent type | Model |
|---|---|---|
| Code review | `code-review` | **opus** |
| Security review | `security-review`, or `general-purpose` if that type isn't registered | **opus** for full review. **sonnet** for the sanity pass on `input: no`. Not spawned at all when `securityReview` is `off`, or is `when-needed` and the tag is `no` |
| Performance review | `performance-engineer` | **opus** for full review. **sonnet** for the sanity pass on `hot: no`. Not spawned at all when `perfReview` is `off`, or is `when-needed` and the tag is `no` |
| Understand-first / as-is tracing (read-only) | `Explore` or `general-purpose` | **opus** |
| Open-ended root-cause analysis | `general-purpose` | **opus** |
| Code-base spelunking, "where is X" | `Explore` | default |
| Research / doc / audit (read-only) | `general-purpose` or `Explore` | **opus** |

Reviewers run **in parallel** in a single message — their concerns are orthogonal.

## Decomposition patterns

| Task shape | Decomposition |
|---|---|
| Understand / as-is (or change in unfamiliar code) | opus tracer (read-only) → opus validator (fresh eyes) → feed verified as-is into the planner (`references/understand-first.md`) |
| Bug fix | opus diagnose → `teamlead:implementer` fix → opus review. Independent bugs run as parallel implementers if file scopes don't overlap. |
| Feature | `teamlead:planner` → parallel `teamlead:implementer`s per module → integration step → opus review |
| Refactor | parallel opus scope-discovery (Explore) → parallel `teamlead:implementer`s per file group → opus review |
| Audit | parallel opus scanners with disjoint focus → opus synthesiser → present findings |
| Research / exploration | parallel opus / Explore agents on different angles → opus synthesiser |
| Migration (lib X → Y) | `teamlead:planner` → parallel `teamlead:implementer`s per package → opus integration review |
| Docs | opus outline → parallel sonnet writers per section → opus consolidator |
| Multi-language work | parallel per language (FE / BE / infra), each with its own `teamlead:implementer` |

Keep tightly coupled work in one agent. Do not assign overlapping scopes to manufacture parallelism. Below roughly three files or 200 changed lines, one implementer is generally faster than two. Define a factual question before assigning exploration. Then decide whether a direct Grep can answer it.

## Parallelism rules

Parallelize disjoint file scopes, read-only investigations, reviews of one diff, and independent streams that later require synthesis.

Sequence planning, implementation, verification, and review for each stream. Serialize writes to one file, dependent investigations, and edits sharing a manifest or lockfile. Cargo, npm, Python, and Go lockfiles require one owner at a time. Parallel implementers share the tree and stage only their own paths.

## Sanity-check before each launch

- Could a single `Bash` / `Read` / `Grep` answer it? Then do it directly.
- Does the prompt name the absolute `$RUN`, the input files, the output file — and, for a reviewer, its role file?
- Did I add only routing facts absent from files, plus the required verbatim settled decisions and consequences?
- For parallel calls: are scopes truly disjoint?
- A `teamlead:<role>` agent: no `model`, no role file, no tools line. A reviewer or ad-hoc agent: right `subagent_type`, right `model` (opus for thinking, sonnet for reading), tools line present with "no Skill tool, no agents"?

## Output to the user

Use one to three sentences between rounds. State ready streams, verification results, active reviews, or triage and rework counts. At completion, relay `$RUN/final-report.md`. It contains delivered behavior, commits, roles, manual checks, Notes, and deferred work in 5–12 lines.

## Anti-patterns

- Implementing repository changes as coordinator.
- Copying entire specs or reports into prompts instead of naming files.
- Opening reports when routing already supplies the required decision.
- Resuming an earlier implementer with SendMessage for rework.
- Overriding plugin-agent models, tools, or role definitions.
- Sequential dispatch of independent work.
- Skipping verification or review because the author claims success.
- Reporting CANNOT_RUN as a test failure.
- Continuing rework beyond the configured cap without the user's decision.
- Dropping Notes or treating optional improvements as defects.
- Assigning spec additions to an implementer without user authorization.
- Accepting edits outside the brief instead of requiring a revert.
- Permitting unrequested refactors or failing to report refactor decisions.
- Paraphrasing the task, spec, or settled user decision.
- Sending batched prose questions or option labels consisting only of letters.
- Claiming visible success without required manual checks.
- Adding living sections to simple plans or putting the run plan in the repository.
- Bypassing step 6d or using transcript flags instead of config.json.
- Polling background Codex review or treating its failure as a dispatch blocker.
- Performing the initial review instead of triaging independent findings.
- Using the validator correction round for a new design review.
- Omitting specialists skipped by when-needed from the final report.
- Ignoring ADR conflicts, editing old ADRs, or creating unrequested records.
- Committing generated ADRs or the ledger as part of this workflow.
- Leaving demotions and deferred refactors only in chat instead of the ledger.

## When this skill is NOT the right tool

- The user said "just do it" or "you implement it" → implement directly.
- A read-only one-shot question fits in a single `Grep` / `Read` → answer directly.
- Trivial single-line edits where delegation overhead dwarfs the work → just do it and tell the user.

If unsure, ask the user one sentence: "Coordinate via teamlead workflow, or handle this directly?"
