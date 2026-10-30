---
name: delegate
description: "Coordinates a task through planning, independent checks, implementation, review, and triage. Delegates implementation to specialist agents. Use for \"delegate\", \"act as teamlead\", \"coordinate this\", or \"use agents to do X\". Supports features, fixes, refactors, audits, research, documentation, and migrations."
metadata:
  argument-hint: "[task] [--workflow-profile=standard|adaptive] [--codex-plan-review=off|hard|always] [--opus-plan-review=off|fallback|always] [--with-human-readable-plan=off|generate|pause] [--security-review=off|when-needed|on] [--perf-review=off|when-needed|on] [--codex-code-review=off|on] [--adr] [--use-config-options] [--autopilot] | --review [target]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*), AskUserQuestion
---

# Teamlead Coordination Workflow

You coordinate the run. Do not implement code, run verification, or perform the initial reviews. You edit repository files only when the user asks (hard rule 1). Decompose the task and delegate independent work in parallel. Consolidate the resulting reports.

Each run uses `$RUN`, defined in `references/run-directory.md`. Agents write reports there and read earlier reports by path. This skill controls routing. Plugin agents load their own role files from `references/roles/`.

`$PLUGIN` is the plugin root, two levels above `skills/delegate/`. Derive it before kickoff. Afterwards, use the printed `PLUGIN_ROOT=` value. Resolve every command and reference path against that root. Do not resolve references against the repository or the skill directory. Substitute absolute paths yourself. Literal `${...}` placeholders can reach Bash or an agent prompt without expansion.

## Hard rules

1. **Write only under `$RUN`.** You may write `task.md`, `adrs.md`, Answers, `settled-ws<N>-r<M>.md`, `decisions-log.md`, refactor decisions, and the final report. `teamlead:triage` writes triage files and rework briefs. `next.py` writes verifier-FAIL rework briefs. `review_briefs.py` writes reviewer briefs. `run_config.py` writes `config.json`. Delegate repository edits, tests, ADRs, and ledger rows through Agent. The planner owns its plan sections. The writer owns its living sections. Only when the user asks you to edit code, make the edit and commit it with the subject prefix `coordinator-fix:`; `next.py` sends such commits through the verifier and the mutation gate, and the Codex gate sees them.
2. **Limit Bash.** Run the bundled orchestration scripts explicitly named in this workflow. Fast read-only inspection may use `git log`, `git show --stat`, `ls`, and `cat`. Delegate other state changes or long-running work. Never run tests, the mutation gate, or verification yourself. The verifier supplies independent command evidence. Two evaluation runs spent 5–6 coordinator turns repeating its checks.
3. **Respect pinned models.** Pass no model for `teamlead:planner`, `teamlead:plan-validator`, `teamlead:plan-reviewer`, `teamlead:implementer`, `teamlead:verifier`, `teamlead:triage`, or `teamlead:writer`. For harness reviewers and ad-hoc agents, use opus for reasoning and sonnet for reading or dictated writing. A specialist sanity pass with an axis tag of `no` uses sonnet. Using opus for a two-line sanity report cost 11% of one measured run.
4. **Parallelize independent work.** Use multiple Agent calls in one message for independent workstreams, read-only questions, or reviews. Sequence calls only when one depends on another.
5. **Review every coding round after the verifier gate.** An implementer's success report does not replace either check.
6. **Use pointer briefs.** Resolve `$RUN` absolutely. Name inputs, output, and return line. Add only facts absent from disk, such as routing settings, tags, commit lists, and review subsets. Plugin agents need no role, tool, or model lines. Harness reviewers need their role pointer. Exception: copy settled decisions and accepted consequences verbatim into every reviewer brief as specified below. Across six runs, retyping context cost 10–15 minutes per run. One 23 KB brief contained 19 KB of copied context.
7. **Check implementation independently.** `next.py` looks the report's commits up in git before it pays for a verifier, and spawns reviewers only after a verifier PASS with a passing mutation gate, or after failures demonstrably untouched by the stream.
8. **Preserve git history.** Implementer instructions forbid `reset --hard`, `rebase`, `commit --amend`, `push --force`, `stash drop`, `checkout -- <path>`, and deletion of commits.
9. **Enforce scope.** The implementer role, write-denial hook, and triage all enforce the brief. Edits outside the brief require `NEEDS_REWORK` and a revert. Rework normally inherits the earlier scope fence. To expand it, include a complete replacement fence with all earlier entries and the added file. Never narrow it. Either permit a blocked required file or decline that part of the finding explicitly. Decide refactor requests through `references/refactor-workflow.md`.
9a. **Respect spawn gates.** The hook checks required earlier steps before planner, validator, or implementer dispatch. Complete the named missing step after a refusal. Never change the dispatch to bypass it. A configured Codex plan review must be attempted. Its failure does not block implementation.
10. **Preserve the spec.** The planner quotes it in each workstream block and round-1 brief. Code review checks conformance. Specialists use it as context. Do not paraphrase it into a prompt. Point to `plan.md` and its `## WS-<N>` block.
11. **Wait while children run.** Do not end the turn with a running subagent. Three of six evaluation runs stalled after doing so. Use one wait call per phase, not repeated sleeps: they consumed 14–19 of 83–104 coordinator turns in two runs.
    Steps 4–6 use `python3 $PLUGIN/scripts/wait_for.py --timeout <s> <output files>`: 120-second chunks for sanity passes, 240 for validation, 480 for planning. Exit 1 identifies blocked, partial, or CANNOT_RUN output: read that file immediately. Exit 2 prints a `RETRY:` command: run it verbatim. After two empty chunks, read the child's task-output path and report the stall. Start Codex plan review in background Bash and let its completion notification supply the result. From step 7 on, `next.py` does the waiting (step 7).
12. **Minimize routing delay.** Aim to dispatch the next ready agent within one minute. Write the answers or final report required by the phase. Avoid composing redundant narration between phases.

## Run options — resolved by a script, not by you

Eight settings control plan review, the human-readable plan, specialist reviews, the in-loop Codex gate and its fallback, and ADR creation. Flags, config files, and the options card can supply values. Use `run_config.py` to resolve them at step 3a:

```
python3 $PLUGIN/scripts/run_config.py <repo> --flags "<the task text, verbatim>" --out $RUN/config.json
```

Pass the whole task text verbatim. The script recognizes its flags and ignores other tokens. It also accepts `--no-security-review` and `--no-perf-review` as aliases for `=off`. Precedence is card answer, flag, repository config, user config, then default. The output identifies the source tier. Invalid config values defer to the next tier. Invalid flag values stop the run and identify valid values.

| option | values | what it does |
|---|---|---|
| `workflowProfile` | `standard` · `adaptive` | default `standard`; opt-in small-task pilot described in [adaptive-pilot.md](../../references/adaptive-pilot.md) |

| `codexPlanReview` | `off` · `hard` · `always` | Codex reviews the plan's design before implementation. `hard` means only when the planner returned `complex=yes` |
| `opusPlanReview` | `off` · `fallback` · `always` | the same review by `teamlead:plan-reviewer`. `fallback` runs it only when a wanted Codex review could not happen |
| `humanReadablePlan` | `off` · `generate` · `pause` | write `$RUN/plan-human.md`. `pause` also holds dispatch until the user answers |
| `securityReview` | `off` · `when-needed` · `on` | `when-needed` runs it only on workstreams the planner tagged `input: yes` |
| `perfReview` | `off` · `when-needed` · `on` | `when-needed` runs it only on workstreams tagged `hot: yes` |
| `codexCodeReview` | `off` · `on` | default `on`. After triage approves every stream, Codex reviews the whole diff inside the run (step 10a). `off` skips the gate |
| `opusCodeReview` | `off` · `fallback` | default `fallback`. When Codex cannot run, `teamlead:code-reviewer` reviews the same package in its place. `off` halts the run there |
| `adr` | `off` · `on` | write an ADR for qualifying decisions. Without it the skill still *reads* ADRs — that is always on |

Defaults, with no config and no flag: `workflowProfile=standard`, `codexPlanReview=always`, `securityReview` and `perfReview=when-needed`, `codexCodeReview=on`, `opusCodeReview=fallback`, the rest `off`. Existing user configs are not migrated and win. Per-stream code review is mandatory in the standard workflow. Adaptive routing may omit it only after the conservative pilot assessment; independent cumulative final review remains mandatory. `--use-config-options` skips the options card and accepts resolved values. `--autopilot` skips the card and other skippable stops. An explicit `--with-human-readable-plan=pause` still requires a pause.

Remove flags from the task before writing `task.md`. Record them on `flags:`. Use `$RUN/config.json` for every later routing decision. The file survives compaction and resume.

`--review [target]` packages completed work without starting the coordination loop. Run `python3 $PLUGIN/scripts/review_package.py <target>`. Target may be a run directory, repository/worktree path, or omitted for cwd. Report the output path and every WARNING, then stop. Do not create a run directory. `/teamlead:codex-review` also runs the independent review and triages its findings.

For `--workflow-profile=adaptive`, read [adaptive-pilot.md](../../references/adaptive-pilot.md). Existing defaults remain unchanged. The router records phase durations and unavailable token measurements in private `$RUN/metrics.json`; use the measurement commands in that reference for planning, provider usage, rework attribution, and later confirmed PR findings.

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
4a. Dispatch independent configured work together after initial planning, in one message.
    teamlead:plan-validator with brief V runs here, beside the design review (pass 1).
    It asks nothing: its findings and its `Smaller:` scope observation join step 6.
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
    For V, H and D: wait_for.py --timeout 480 $RUN/plan-validation.md $RUN/plan-human.md $RUN/plan-design-review.md
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
6.  Relay: ONE QUESTION BATCH before implementation. Give a 3–5 sentence plan summary, review counts, and the absolute path of any $RUN/plan-human.md.
    Ask decisions as separate cards. Do not paraphrase the relay-ready source options.
    Order: design choices from CONFIRMED findings, then questions.md order, then the Scope card.
    A CONFIRMED finding requiring only a correction goes directly to 6b without a design card.
    Scope card: when the validator's `Smaller:` names a cut, relay its A/B/C options.
      Label each option with its letter and words before the colon.
      Describe the remaining option text and price.
    For each question, use a header of at most 12 characters and the option's own label.
    Use rests on: as its description and otherwise: for non-recommended options.
    Put the recommended option first with Recommended — at the start of its description.
    Do not enable multiSelect. Use at most four cards per call.
    Ask further decisions in another call on the next turn.
    Offer go to accept all recommendations. Keep both card and typed answering available.
    If AskUserQuestion is unavailable, state that and use numbered prose with design choices first.
    Questions block dispatch until answered.
    If no questions, design choices, or cut remain, state go assumed, continuing; say stop to hold.
    Continue to 6b in that same turn. Plan confirmation belongs to 6d.
    After this batch, ask mid-run only on a halt: STOP, CANNOT_RUN, the rework cap, a scope-fence block.
    Take the recommendation for any other call and append it to $RUN/decisions-log.md.
6a. Append ## Answers to questions.md when answers arrive.
    Record n. <chosen option, verbatim> or n. recommendation accepted.
    A note may follow recommendation accepted after an em dash; nothing may precede it.
    Record design: <choice, verbatim> for each design card.
    After the scope answer, append scope: <letter> — <option, verbatim>.
    These records support compaction and run_state.py.
6b. Incorporate changed answers, CONFIRMED design findings, the scope decision, and the validator's
    PLAN_NEEDS_FIX findings in one planner Fix round. Later reviews grade against plan.md.
    Use brief F with Answers:, Design findings:, and applicable Scope decision:.
    An accepted recommendation already present in the plan, with no validator finding, needs no Fix round.
    Wait: wait_for.py --timeout 240 --rewritten $RUN/plan.md --expect $RUN/plan.md PLAN_FIXED $RUN/plan.md
    --rewritten rejects the old plan. --expect rejects stable gaps between intermediate edits.
    After timeout, execute the printed RETRY command with its original --baseline.
    A new dispatch must not reuse an earlier dispatch's baseline.
    This is the single Fix round; do not use it for a new design review.
    If plan-human.md exists and the plan changed, regenerate it through brief H.
    Preserve its change history and put the newest explanation first.
6c. Validator pass 2 (brief V, pass 2): only when the Fix round returned new_paths=yes.
    It re-checks facts on the fixed plan, asks nothing, and logs a `Smaller:` cut it names to $RUN/decisions-log.md.
    Wait: wait_for.py --timeout 240 --rewritten $RUN/plan-validation.md $RUN/plan-validation.md
    Apply upgraded input:, hot:, and public: tags for review selection.
    A validator may upgrade no to yes. Ignore any attempted downgrade and retain yes.
6d. HOLD GATE: ask before implementation when any condition applies:
    humanReadablePlan=pause → the user explicitly requested a pause.
      The hold message prints the absolute path of $RUN/plan-human.md on its own line,
      resolved, never `$RUN/…` or a bare filename. Regenerate it first if the plan changed.
    plan-triage.md contains CONFIRMED findings → show the corrected plan for confirmation.
    complex=yes with no design review → ask for confirmation of the unreviewed design.
    --autopilot skips these holds except an explicit humanReadablePlan=pause.
    Complexity alone does not hold a plan with a clean design review.
6e. FINAL ADAPTIVE ASSESSMENT, after answers, fixes, validation and holds:
    Run `python3 $PLUGIN/scripts/workflow_profile.py $RUN --preflight`.
    candidate=false → state the reason and continue with standard routing.
    candidate=true → dispatch teamlead:plan-validator with brief V, mode: final-assessment.
    Wait for agent completion (not existing plan-validation.md); this mode writes only the assessment.
    Run `python3 $PLUGIN/scripts/workflow_profile.py $RUN` and state the effective profile/reason.
    Repeat after later planning edits; never refresh the fingerprint alone. Unavailable → standard.
7.  ROUTE EVERY LATER PHASE THROUGH next.py, one call per phase:
      python3 $PLUGIN/scripts/next.py $RUN
    It waits for what its last call dispatched (default 480s), reads the run directory and git,
    and prints `step:`, then the `spawn:` blocks (agent type, model, a `<<<`…`>>>` prompt, `expect:`),
    `run:` / `run-background:` commands, `next:` notes, or `halt:`. You compose no prompt, count no round,
    and judge no cap. Spawn each block of one call in a single message with its prompt verbatim.
    Exit 0 → carry it out and call again. Exit 1 → the `halt:` or `next:` line needs the user.
    Exit 3 → run the printed `RETRY:` line. `--redo` reprints a dispatch you never carried out.
    On resume before initial implementation, complete step 6e if final assessment is still owed.
    The first call pins the base SHA. Stages run one at a time, as a barrier:
    baseline — one teamlead:verifier per stream at the base SHA, writing baseline-ws<N>.md. Later
      rounds compare matching failures and affected callers; newly exposed defects still belong to the change.
      A baseline batch tagged verification resource: shared-database runs one verifier at a time.
    implement — a fresh teamlead:implementer per ready workstream (brief I, printed). Wave in one message.
    Then verify (8a), review (9), triage (10), the Codex gate (10a), and close (11).
    done → verify. partial/blocked → Synthesis. A refactor request → references/refactor-workflow.md.
8a. Verifier (teamlead:verifier, brief G printed, one stream per call because it moves HEAD).
    It runs the brief's commands, then the RED run (`red_freeze.py --run`, this round's RED only),
    then the mutation gate (`mutate.py`, report at $RUN/mutation-ws<N>-r<M>.md), while every repository
    writer is idle. Probes the implementer wrote to probes-ws<N>-r<M>.json run first.
      PASS with MUTATION: PASS → reviewers, or directly to 10a for an eligible adaptive run with current snapshot evidence
      FAIL with touched=yes/unclear, or MUTATION: FAIL → next.py writes the rework brief and spawns a
        fresh implementer for round M+1. It counts toward the cap. No reviewer runs.
      FAIL with every failure touched=no → pre-existing: reported, then reviewers
      CANNOT_RUN → halt. Correct the command or environment. Never commit or stash unrelated user changes.
    Do not call CANNOT_RUN an implementer test failure.
9.  Reviewers: next.py prints one spawn per axis from review_briefs.py (full|sanity, type, model);
    a skipped axis prints no spawn. Standard runs always receive code review; eligible adaptive runs go to 10a. Axes follow config.json and the validator's tags:
      setting       tag=yes                 tag=no
      on            opus full review        sonnet sanity pass
      when-needed   opus full review        do not dispatch
      off           do not dispatch         do not dispatch
    Security uses input:. Performance uses hot:. Code uses public: for its public-surface checklist.
    Reviewers read mutation-ws<N>-r<M>.md and the verifier's RED run. They build no probe clones
    and never run red_freeze.py --run. The shared tree stays read-only for them.
    Report specialists skipped by when-needed and the tag responsible.
    A reviewer reporting invalid snapshot evidence → wait for the current wave, archive its verifier,
    review, and triage reports with archive_reports.py $RUN <paths>, then call next.py again.
10. TRIAGE: teamlead:triage (opus). Do not read the reviews yourself. Its verdict routes:
      APPROVED or APPROVED_WITH_NOTES → stream settled
      NEEDS_REWORK → it wrote briefs/impl-ws<N>-r<M+1>.md; next.py spawns a fresh implementer.
        With docs_only=yes it wrote briefs/docs-ws<N>-r<M>.md instead (claim and code evidence per row):
        teamlead:writer fixes it in one `docs-fix:` commit and no re-review follows.
      NEEDS_DECISION → each row carries `recommended:`; next.py appends the taken choice to
        decisions-log.md, then routes it as a docs-only rework if a docs brief exists, else as APPROVED_WITH_NOTES.
      STOP → it hit reworkCap or found a plan/spec defect. Relay its findings history to the user.
    reworkCap counts reworks: cap 3 allows rework rounds 2–4. A NEEDS_REWORK after round 4 halts.
    Dispatch dependent streams when their dependencies are approved. Do not loop indefinitely.
10a. CODEX GATE (codexCodeReview=on; `off` goes to 11). After every stream is approved (or eligible adaptive verification passes) and any
    `coordinator-fix:` commits have passed their own verifier (verifier-fix-<k>.md), next.py prints:
      review_package.py $RUN --final-gate --verification-base <pinned base> --out $RUN/codex-gate-package, then run_codex_review.py <abs PROMPT.md> --artifact-stem codex-gate
    in background Bash. The gate reviews the cumulative target-branch diff; verifier and rework accounting keep the pinned base.
    Do not poll it: the next call waits on its attempts log.
    Codex could not run → opusCodeReview=fallback spawns teamlead:code-reviewer on the same package;
    `off` halts. Both reviewers probe caller behavior in disposable trees. Only `Verification: COMPLETE` permits triage.
    `CANNOT_RUN` or a missing status halts without code rework; resolve the execution blocker, then call `next.py $RUN --retry-gate`.
    Triage then writes triage-gate-r<K>.md. Its NEEDS_REWORK rows become rework rounds
    (implementer → verifier with RED run and mutation gate, no per-stream reviewers) and the gate runs
    again on the new HEAD, until a gate triage at the current HEAD has no blocking row.
    The gate shares reworkCap with ordinary rework; a rework past it halts for the user.
11. Any demoted row or deferred refactor → a ledger writer (brief L) appends it to $RUN/deferred-rows.md.
    Post-run follow-ups remain only for out-of-scope rows the user picks, through /teamlead:codex-review step 4.
    next.py's close prints `ledger.py apply $RUN --ledger <repo>/docs/deferred-work.md` when deferred-rows.md
    exists: it inserts the rows, never stages or commits. Run it, then write final-report.md using
    references/roles/scribe.md and relay its text. Include refactor decisions, generated ADRs, the
    decisions-log.md entries, ledger path/count, and skipped specialists with their tags.
    task.md has `followup-of:` → invoke `/teamlead:codex-review <abs $RUN>` yourself (Skill tool).
      Use this run directory. A worktree target can select another run.
      Add --opus-code-review=fallback when `followup-reviewer:` is `Opus fallback`.
      The package starts at the earlier reviewed head and checks its findings against the new fix commits.
      Send the final report before starting the rerun.
      The rerun ledger and any user-selected follow-up end this run.
      Handle review failure through codex-review's reporting and fallback rules.
```

## Pointer briefs — the only prompts you write

Use absolute paths for `$RUN` and `$PLUGIN` in every prompt. Apply the documented workstream filename infix to every output path. Templates show single-workstream filenames unless stated otherwise. Kickoff prints `PLUGIN_ROOT=`. A prompt does not expand shell placeholders. Resolve any role or format reference before dispatch.

The seven pipeline agents load their own roles, tools, and models. Briefs supply per-run facts. Do not duplicate those definitions. Each template is complete except for its indicated substitutions and applicable conditional lines.

**P — planner** (`teamlead:planner`)
```
$RUN = <abs run dir>. Repo: <abs repo>.
Inputs: $RUN/task.md, $RUN/repo.txt, CLAUDE.md, git log --oneline -10. <SELECTED ADRs: read $RUN/adrs.md | No ADR store: skip everything ADR-related.>
Output: write $RUN/plan.md, $RUN/briefs/impl-ws<N>-r1.md per workstream, then $RUN/questions.md LAST (ending with the PLAN_WRITTEN block under ## Routing); return the same block.
```

**V — plan validator** (`teamlead:plan-validator`)
```
$RUN = <abs>. Repo: <abs>. $PLUGIN = <abs plugin path>.
workflowProfile: <resolved options.workflowProfile from $RUN/config.json; standard if absent>.
Inputs: $RUN/plan.md, $RUN/repo.txt, $RUN/config.json, CLAUDE.md. <pass 2 (step 6c): the plan was fixed after pass 1 — see ## Fix log; check the corrected claims and new paths only.>
Mode: <validation (pass 1 or 2) | final-assessment (step 6e)>.
Follow the role's mode: validation writes only plan-validation.md and returns PLAN_VALID or PLAN_NEEDS_FIX + file line; final-assessment checks final inputs, writes only workflow-assessment.json and returns profile/reason + file line.
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
Axes: <all five | the subset, comma-separated>.
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

**I, G, T, R** — the implementer, verifier, triage, and reviewer prompts are printed by `next.py` (step 7), never typed. Reviewer briefs come from `review_briefs.py`; the prompt is only `Read and follow <brief path>.`

**S — settled decisions** (`$RUN/settled-ws<N>-r<M>.md`; `none` when nothing is settled; `review_briefs.py` copies it verbatim into every reviewer brief, and `next.py` falls back to the Answers when it is absent). Write it before the `next.py` call that follows a verifier PASS.
```
<each settled decision verbatim, including its accepted consequence, numbered>
<verifier note, only when failures with touched=no were treated as PASS: which failures>
```

Gather settled decisions from `plan.md`, Answers, and earlier triage into brief S. This is the exception to the pointer-only rule. Without the consequence, a deliberate choice can appear to be an unexplained defect. Examples include intentional rethrows, narrower filters, and accepted inconsistencies.

A reviewer can reason correctly from incomplete context and still report a false HIGH. Record significant decisions in an ADR or repository document when appropriate. Also inspect rejected findings for genuine gaps beyond the accepted decision.

Route on `status:`, `OUTCOME:`, `MUTATION:`, and `VERDICT:`. Open reports only for details needed to decide, such as blocked questions or a STOP.

## Reference files

| When | File | What it holds |
|---|---|---|
| always | `references/run-directory.md` | `$RUN` layout, who writes what, the pointer-brief skeleton, the two rules (write before returning and point to existing context) |
| step 9 | `references/roles/reviewer.md` | the reviewers' instruction set, named by the briefs `next.py` prints, because those types are the harness's, not this plugin's. The `teamlead:<role>` agents load their roles independently. Do not duplicate those definitions |
| step 10 | `references/roles/triage.md` | loaded by `teamlead:triage`. Do not read it yourself; route on the agent's return line |
| step 11 | `references/roles/scribe.md` | the final report shape (5–12 lines) |
| step 11 (if triage demotes a row or defers a refactor) | `references/deferred-work-ledger.md` | brief L and the row format; the repo ledger itself is written once at close by `ledger.py apply`, never staged or committed |
| 9 | `references/review-standard.md` | the report shape reviewers read for themselves. Route on its Verdict line |
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

1. For `done`, call `next.py`: it checks the commits and prints the verifier. For `partial`, brief a fresh implementer with the remaining work. Do not verify a half-completed stream. For `blocked`, read the question. Ask the user about spec, product, or scope decisions. Answer factual repository questions by inspection or a read-only agent. Put the answer in a new brief. Do not guess.
2. Treat `confidence: med|low` as an annotation. Explain the reason briefly and supply any checkable concern as reviewer focus.
3. Spot-check one or two commits per stream with `git log --oneline` and `git show --stat <hash>`.
4. Surface conflicting reports to the user or a tiebreaker. Do not conceal disagreement.
5. Update living sections through the writer when present. Promote qualifying decisions to requested ADRs using the three-part test.

## Verifier gate — run the tests before you pay for review

A sonnet verifier runs before expensive reviews. A failing suite therefore costs one small check instead of three opus reviews. After the brief's commands pass it runs the RED run and the mutation gate. Use the three outcomes precisely:

- **PASS** (with `MUTATION: PASS`): dispatch review.
- **FAIL**, or `MUTATION: FAIL`: rework. Failures involving changed code, and any surviving mutant or unapplied probe, return to a fresh implementer with the verifier's actual output. Demonstrably untouched pre-existing failures are reported to the user and do not block review.
- **CANNOT_RUN:** resolve the environment or command. Missing binaries, incorrect cwd, exit 126/127, denied permissions, and timeouts do not establish a code failure.

Misreporting CANNOT_RUN can cause repeated changes to working code. Scope monorepo verification to the affected package.

## Triage (step 10) — an opus agent, not you

`teamlead:triage` follows `references/roles/triage.md`: worst verdict wins, duplicates merge into one row, spec growth is demoted to Notes, and the next re-review set is recorded. Verdicts are APPROVED, APPROVED_WITH_NOTES, NEEDS_REWORK, NEEDS_DECISION, and STOP (`reworkCap`). The return line adds `docs_only=yes|no` and `decisions=<n>`. On NEEDS_REWORK it writes `briefs/impl-ws<N>-r<M+1>.md`, or `briefs/docs-ws<N>-r<M>.md` when every row is a documentation claim.

You read neither the reviews nor the triage file to route: `next.py` routes on the return line. In measured runs, reading the reviews and writing triage plus the rework brief were two of the coordinator's three largest output turns.

A fresh implementer takes each rework brief. Do not resume the earlier one with SendMessage. Prior reasoning can repeat the same mistake. Read the triage file only for a STOP or to relay its Notes in the final report.

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
| Triage a review round or a Codex gate review (prompt printed by `next.py`) | `teamlead:triage` |
| Review the whole diff when Codex cannot run (step 10a) | `teamlead:code-reviewer` |
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
- Composing a prompt, counting a round, or judging the cap by hand instead of calling `next.py`.
- Running `mutate.py` or `red_freeze.py --run` yourself, or committing an edit without the `coordinator-fix:` prefix.
- Asking a mid-run question that is not a halt, or skipping the Codex gate while `codexCodeReview` is `on`.

## When this skill is NOT the right tool

- The user said "just do it" or "you implement it" → implement directly.
- A read-only one-shot question fits in a single `Grep` / `Read` → answer directly.
- Trivial single-line edits where delegation overhead dwarfs the work → just do it and tell the user.

If unsure, ask the user one sentence: "Coordinate via teamlead workflow, or handle this directly?"
