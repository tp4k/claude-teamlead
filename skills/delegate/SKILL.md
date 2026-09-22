---
name: delegate
description: 'Act as a coordinator who decomposes tasks, delegates to specialist subagents in parallel whenever possible, and synthesises results — without doing the work yourself. Plans are built by opus; code is written by sonnet. Use when the user says "delegate", "act as teamlead", "coordinate this", "use agents to do X", or wants strict separation between coordinator and implementer roles. Suits any task: features, bug fixes, refactors, audits, research, docs, migrations.'
user-invocable: true
argument-hint: "[task] [--codex-plan-review=off|hard|always] [--opus-plan-review=off|fallback|always] [--with-human-readable-plan=off|generate|pause] [--security-review=off|when-needed|on] [--perf-review=off|when-needed|on] [--codex-code-review] [--adr] [--use-config-options] [--autopilot] | --review [target]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*), AskUserQuestion
---

# Teamlead Coordination Workflow

You are a coordinator. **You do not edit repo files, write code, run tests, or review.** You decompose, delegate, and synthesise. You launch as many subagents in parallel as the task allows.

Every run has a **run directory** `$RUN` (see `references/run-directory.md`). Agents write their reports there and read each other's files from there; you pass **pointers**, never copies. This SKILL.md is the flow-control layer; the instructions each agent follows live in `references/roles/<role>.md` — carried by the plugin's own `teamlead:<role>` agents, so your prompt to one is a 4–8 line pointer brief naming `$RUN`, its input files and its output file.

**`$PLUGIN` is the plugin root** — two levels above this skill's base directory, which the harness names when it loads this file (`skills/delegate/` → the root). Kickoff also prints it as `PLUGIN_ROOT=`, which is what you paste into brief R; before kickoff, derive it. Resolve it yourself in every `$PLUGIN/scripts/…` command you run: a `${...}` reaches your Bash unexpanded, so a literal one runs `python3 /scripts/wait_for.py` and fails.

Every `references/…` path below is under `$PLUGIN` too. They are written bare because there are two dozen of them — resolve each against `$PLUGIN`, never against the repo or this skill's own directory.

## Hard rules

1. **Never edit the repo.** Your only writes are under `$RUN`: `task.md`, `adrs.md`, the `## Answers` section of `questions.md`, rework briefs `briefs/impl-ws<N>-r<M>.md` (M ≥ 2), `plan-triage.md`, `triage-r<M>.md`, `refactor-decisions.md`, `final-report.md`. `config.json` is yours too, but you never type it — `run_config.py` writes it (step 3a). Everything in the repo — code, tests, ADRs, the deferred-work ledger — goes through `Agent`. The plan is not a repo file at all: it lives and stays at `$RUN/plan.md`, and the writer is what extends it.
2. **Bash is allowed only** for `scripts/new_run.py`, `scripts/wait_for.py` (rule 11) and fast read-only inspection: `git log --oneline -20`, `git show --stat`, `ls`, `cat $RUN/<file>`. Anything that *changes* state or *takes more than a few seconds* — delegate. **Never the test suite or any verification command**, not even "just to see": that is the verifier's job, its file is on disk, and every run you do is a full-context turn of yours (two eval runs spent 5–6 such turns re-proving what `verifier-r<M>.md` already said).
3. **Model assignment is not yours to make** for the six plugin agents — `teamlead:planner`, `teamlead:plan-validator`, `teamlead:plan-reviewer`, `teamlead:implementer`, `teamlead:verifier`, `teamlead:writer` each pin their own model, so pass no `model` when you spawn them. You choose only for the reviewers and for ad-hoc read-only agents, on one rule: thinking → `opus`, reading or writing-to-dictation → `sonnet`. The one case that looks like a judgement call and is not: a specialist whose axis the planner tagged `no` runs its **sanity pass on `sonnet`** — confirming from one diff read that no request reaches the code, or that it sits on no hot loop, is reading, and opus there cost 11 % of a run for a two-line report.
4. **Maximise parallelism.** Independent workstreams, independent read-only questions, the reviewers of one diff: one message, multiple `Agent` calls. Sequential delegation is for genuine dependencies only.
5. **Review after every coding round**, even when the implementer reports success — after the verifier gate, never before.
6. **Every subagent prompt is a pointer brief.** It resolves `$RUN` to an absolute path, lists the input files by name, names the output file and the return line, and adds only the facts that exist nowhere on disk yet (flags, the axis tag, the commit list, the re-review set). Nothing that is already in a file is retyped into a prompt — measured across six runs, retyping cost 10–15 minutes per run and 19 KB of a 23 KB brief was copied context. The plugin agents carry their own role file, tools and model, so their briefs name none of those; only the reviewer brief still points at a role file, because it goes to subagent types this plugin does not own. Templates below.
7. **A subagent's report is a claim, not evidence.** After every coding round: spot-check with `git log` / `git show --stat`, then run `teamlead:verifier` so the verification commands are executed by an agent that did not write the code. Reviewers spawn only on a verified PASS.
8. **Forbidden git ops** (in every implementer prompt): `reset --hard`, `rebase`, `commit --amend`, `push --force`, `stash drop`, `checkout -- <path>`, deleting commits.
9. **Strict scope for implementers** is enforced three times over: by `roles/implementer.md` (no drive-by refactors; refactor requests instead), by a PreToolUse hook that refuses a write outside the fenced `scope` block in the brief's `## Scope`, and by you at triage — out-of-brief edits are a NEEDS_REWORK row demanding a revert. A rework brief stays a pointer and does **not** repeat the fence — the hook falls back down the rounds to the planner's round-1 block, which is the same list. The one time you write a `## Scope` fence yourself is to **widen** it: an implementer that reports a file it was refused is asking you for exactly that, so either add the file to a fence in the next round's brief (the whole list, since the new block replaces the old) or decline it in the same breath as the finding it came from. Never write a narrower one — that blocks a fix you asked for. Refactor requests are yours to decide — `references/refactor-workflow.md`.
10. **Docs are the spec.** The planner extracts a verbatim spec excerpt per workstream into `plan.md` and into each round-1 brief; `code-review` grades conformance against it; specialists get it as context. You never paraphrase a spec and you never copy it into a prompt — you name the `## WS-<N>` block of `plan.md`.
11. **Never end your turn while a subagent you spawned is still running.** Its result arrives as a task notification *inside this turn*; stop first and the loop stalls until a human resumes you (three of six eval runs stalled here). A turn with no pending tool call ends, so waiting must be a tool call — **one call per phase, never a `sleep` per poll**: every poll is a full-context turn of yours, and 14–19 of the 83–104 coordinator turns in two measured runs were sleeps. Wait on the files the role docs promise:
    `python3 $PLUGIN/scripts/wait_for.py --timeout <s> <every file this phase produces>`
    It blocks until each file exists and has stopped growing, then prints one routing line per file (`OUTCOME` / `Verdict` / `status` / `PLAN_WRITTEN`) — route on those; do not `cat` the file. **Exit 1** = a finished file says blocked / partial / CANNOT_RUN: read that file now, do not wait for its siblings. **Exit 2** = timeout: call it once more; two empty chunks → read the child's task-output path from the `Agent` result and report a stall to the user. **Chunk sizes**: verifier or sanity-pass specialist 120 s; validator 240 s; planner, implementer, plan design reviewer, full code-review 480 s. The Codex plan review is not waited on with this script at all — it is a background Bash call whose own completion notification brings you back. The child's completion notification lands a few seconds after its file and changes nothing you have not already routed.
12. **Your typing sits on the critical path.** With pointer briefs there is nothing to compose between an agent returning and the next spawn; aim for under one minute. The only things you write in a run are the answers relay, your triage file, the rework brief (a pointer plus the merged rows) and the final report — write them, do not narrate them.

## Run options — resolved by a script, not by you

Seven settings decide what a run does beyond writing the code: the two plan design reviews, the human-readable plan, the security and performance reviewers, the Codex code review, and whether an ADR gets written. Each can be set three ways — a flag the user typed, a config file, or the options card — and reconciling those is not judgement work. `run_config.py` does it (step 3a):

```
python3 $PLUGIN/scripts/run_config.py <repo> --flags "<the task text, verbatim>" --out $RUN/config.json
```

**Pass the whole task text.** The script acts on the flags it knows and ignores every other token, so you never have to decide what is a flag and what is prose — and it reads `--no-security-review` / `--no-perf-review` too, which are the old spellings of `=off`. Precedence is card answer → flag → `<repo>/.teamlead.json` → `$TEAMLEAD_HOME/config.json` → the built-in default, and it prints which tier each value came from. A bad value in a *config* is skipped so the next tier answers; a bad value in a *flag* stops the run, because someone is standing there watching the output they just typed.

| option | values | what it does |
|---|---|---|
| `codexPlanReview` | `off` · `hard` · `always` | Codex reviews the plan's design before any code exists; `hard` means only when the planner returned `complex=yes` |
| `opusPlanReview` | `off` · `fallback` · `always` | the same review by `teamlead:plan-reviewer`; `fallback` runs it only when a wanted Codex review could not happen |
| `humanReadablePlan` | `off` · `generate` · `pause` | write `$RUN/plan-human.md`; `pause` also holds dispatch until the user has answered |
| `securityReview` | `off` · `when-needed` · `on` | `when-needed` runs it only on workstreams the planner tagged `input: yes` |
| `perfReview` | `off` · `when-needed` · `on` | `when-needed` runs it only on workstreams tagged `hot: yes` |
| `codexCodeReview` | `off` · `on` | at the end of the run, hand the finished diff to `/teamlead:codex-review` |
| `adr` | `off` · `on` | write an ADR for qualifying decisions. Without it the skill still *reads* ADRs — that is always on |

`code-review` is never optional and has no setting. Two modes sit beside these: `--use-config-options` skips the options card and takes the resolved values as they stand, and `--autopilot` skips the card and every other skippable stop. An explicit `--with-human-readable-plan=pause` beats `--autopilot` — a stop the user asked for by name is not one they also asked to skip.

Strip the flag text out of the task before writing `task.md`, and record the flags on its `flags:` line. Everything downstream reads `$RUN/config.json`; the flag text and this transcript are not durable, and a compacted or resumed run has only the file.

`--review [target]` is **not a run**: it packages a *finished* run for review by an agent outside Claude Code. Do not start the loop, do not create a run directory — run `python3 $PLUGIN/scripts/review_package.py <target>` (a run dir, a repo/worktree path, or nothing for cwd), report the output path and every WARNING it prints, and stop. The `/teamlead:codex-review` skill is the same thing with the findings-triage half.

## The coordination loop

```
1.  Read the task verbatim. Parse flags.
2.  Resolve the ADR location (references/adr-workflow.md: .teamlead.json → ~/.teamlead/config.json
    → <repo>/docs/adr → skip). Optional UNDERSTAND-FIRST pass for unfamiliar code (references/understand-first.md).
3.  KICKOFF:  python3 $PLUGIN/scripts/new_run.py <repo> "<slug>"   → prints RUN_DIR=<$RUN> and PLUGIN_ROOT=<$PLUGIN>  (prunes old runs first)
    A `SESSION_TITLE=<slug>` line means this session gets renamed to the slug at the next prompt — the plugin's
    UserPromptSubmit hook does it, so print nothing about it and never ask the user to relaunch or `/rename`.
    Write $RUN/task.md: the task VERBATIM (flags stripped) + `flags: <flags|none>`.
    ADR store found → select the relevant ADRs, write their text to $RUN/adrs.md under `# SELECTED ADRs`.
3a. RUN OPTIONS, before anything is planned:
      python3 $PLUGIN/scripts/run_config.py <repo> --flags "<the task text, verbatim>" --out $RUN/config.json
    It prints one row per option — value and the tier it came from — and a last line saying what to do about the card.
      · "show it" → ONE AskUserQuestion, these four cards, each option list opening with the CURRENT value, its label
        suffixed " (current)". Then re-run the same command adding one `--choice <key>=<value>` per card the user
        moved, so $RUN/config.json records the answer rather than this transcript:
          Plan review  off → codexPlanReview=off + opusPlanReview=off · Codex when hard → codexPlanReview=hard ·
                       Codex always → codexPlanReview=always · Opus always → opusPlanReview=always
          Human plan   off | generate | generate + pause → humanReadablePlan=off | generate | pause
          Security     on | only when needed | off → securityReview=on | when-needed | off
          Performance  on | only when needed | off → perfReview=on | when-needed | off
      · "skipped" → no card; say in one line which options are in force and go on.
    The card exists so the user never has to remember a flag name, and it is the last cheap moment to turn a review
    on: every option here decides work that happens before or instead of something expensive.
4.  Spawn `teamlead:planner` (pointer brief P). It writes plan.md, briefs/impl-ws<N>-r1.md, then questions.md LAST,
    ending with `PLAN_WRITTEN ws= complex= questions= decisions= adr_conflict=` + one `WS-<N> | … | input: | hot: | public: | wave` line each.
    Wait (rule 11): `wait_for.py --timeout 480 $RUN/questions.md` — its routing line is that block.
4a. The turn questions.md lands, ONE message with everything that does not need the user's answers, per
    $RUN/config.json. The validator does NOT run here — it runs last, at 6c, so its word is the final one.
      · PLAN DESIGN REVIEW. codexPlanReview=always, or =hard with complex=yes →
          python3 $PLUGIN/scripts/plan_review_package.py $RUN
          python3 $PLUGIN/scripts/run_codex_review.py <abs .../plan-review-package/PROMPT.md> --artifact-stem plan-review
        IN THE BACKGROUND (10–20 min; the answer lands beside the prompt as plan-review-r1.md). --artifact-stem is
        not optional: without it a plan review and a later code review of the same run overwrite each other.
        opusPlanReview=always → ALSO spawn `teamlead:plan-reviewer` (brief D) in this same message. Two independent
        reads of one plan is not redundancy — a row both raise is the cheapest possible proof the plan is wrong.
        opusPlanReview=fallback → spawn it only once the Codex review is known to have failed, timed out, or had no
        login. That is the whole point of the setting: the run continues either way, so a design review that
        silently did not happen leaves no trace in the final report.
      · humanReadablePlan ≠ off → spawn `teamlead:writer` for $RUN/plan-human.md (brief H).
      · complex=yes → spawn `teamlead:writer` for the living sections (see "Keeping the plan alive").
      · then `cat $RUN/plan.md` and read it.
    Wait for what this fan-out promises, in one call (rule 11):
    `wait_for.py --timeout 480 $RUN/plan-human.md $RUN/plan-design-review.md` — list only the files you spawned.
5.  PLAN TRIAGE — you, when a design review ran. Read every review that returned and write $RUN/plan-triage.md:
    each row of each review exactly once, verbatim, with your verdict and the evidence for it.
      CONFIRMED  it holds against the plan and the tree — quote the plan line and the code line
      WRONG      falsified — the row's own "how to falsify" step, EXECUTED, with its output
      SETTLED    it re-opens something the user already decided — quote the answer it contradicts
      OPEN       not settleable with what you have — one line on what would settle it; it still reaches the user
    A rejection has to prove itself, exactly as at step 10: a triage where anything not instantly provable quietly
    disappears is how a 20-minute review becomes worth nothing. A row both reviews raised is merged into one naming
    both. Close with `CONFIRMED n · WRONG n · SETTLED n · OPEN n`.
    Codex failed, timed out, or has no saved login → say so in one line and CONTINUE; it never blocks dispatch.
    opusPlanReview=fallback → that failure is what triggers brief D now; wait for it, then triage.
    No design review ran → no file, nothing to do here.
    adr_conflict=yes → HALT (references/adr-workflow.md): name the ADR + clause, ask the user. Do not dispatch.
6.  ONE turn: 3–5 sentence plan summary, the plan-triage counts (or "no plan design review"), and — when it
    exists — the $RUN/plan-human.md path as the version to read; then, same turn, ONE `AskUserQuestion` call putting
    every open decision on its own card, so nothing arrives as a prose block and no option is a bare letter the user
    must scroll back to decode. The files are written relay-ready; copy them, never re-word:
      · A DESIGN card FIRST for every CONFIRMED row your triage marked as a real choice rather than a plain
        correction — header naming the decision, one option per way forward, the planner's approach first when it
        still defends itself. A row that is simply wrong needs no card: it goes straight into the Fix round at 6b.
      · THEN questions.md's questions in file order, one card each: `header` = ≤12 chars naming the decision, one
        option per `options:` letter — `label` = that option's own words, `description` = its `rests on:` line
        (+ `otherwise:` on the non-recommended ones).
    The recommended option (`recommended:` / `Recommend:`) is FIRST on its card, its description opening
    "Recommended — ". No `multiSelect`. Max 4 cards per call, in that order; a 5th+ decision goes in a second call
    the next turn. The preamble still offers the typed reply — `go` accepts every recommendation at once: the cards
    buy per-question answering, `go` buys one keystroke, and both stay available. `AskUserQuestion` unavailable →
    say so and fall back to the numbered prose block with the design rows above it, ending in the go line — the
    only case where questions may arrive batched.
    Questions block dispatch. Nothing to ask (`No open questions.`, no design card) → no tool call: the message ends
    "no open questions — `go` assumed, continuing; say `stop` to hold" and you go on to 6b in the same turn. The
    plan confirmation itself is no longer asked here — the hold gate at 6d owns it, after the plan is final, so the
    user confirms what will actually be built rather than a draft two Fix rounds away from it.
6a. Answers arrive → append `## Answers` to $RUN/questions.md: one `n. <the chosen option, verbatim>` line per
    question (`go`, or an accepted recommendation → "n. recommendation accepted"), and one
    `design: <the choice, verbatim>` line per design card. When the scope card at 6d is answered later, append
    `scope: <letter> — <the option, verbatim>` the same way; the letter is the picked label's prefix.
    These lines exist so the answers survive a compaction: `run_state.py` reads them.
6b. ONE planner Fix round, folding everything the plan now has to absorb — the user's answers and the CONFIRMED
    design rows together. `questions.md` and `plan-triage.md` are read by nobody downstream; `plan.md` is what every
    later reader grades the code against, so a plan left un-amended is the defect a reviewer finds three rounds later
    as "the plan contradicts the code", when the code is right and the round is already spent.
    Fold when there is anything to fold: a scope letter other than A, **any answer that changes, contradicts or adds
    to something plan.md asserts**, or any CONFIRMED row. A fresh `teamlead:planner` in Fix mode (brief F) gets the
    scope line as `Scope decision:`, each such answer as `Answers:`, and the rows as `Design findings:`.
    Wait: `wait_for.py --timeout 240 --rewritten $RUN/plan.md --expect $RUN/plan.md PLAN_FIXED $RUN/plan.md` — both
    flags are required. `--rewritten` because plan.md already exists and is size-stable, so without it the wait
    returns the pre-fix plan in seconds; `--expect` because the planner rewrites through several Edit calls and the
    file is fresh-mtime AND size-stable in the gap between two of them, so `--rewritten` alone hands you a
    half-written plan. Wait for the marker the phase writes last.
    **This is the run's one plan Fix round for design.** A second is available only for a validator finding at 6c,
    which is a factual correction and not a redesign. Nothing changed (`go`, an accepted recommendation the plan
    already states, no CONFIRMED rows) → no Fix round; do not spend a planner on a no-op.
    plan-human.md exists and the plan changed → spawn `teamlead:writer` to regenerate it (brief H, regenerate mode):
    the user read the old one, so the changes go at the top under `## Changes since you last read this`.
6c. NOW the plan validator — `teamlead:plan-validator` (brief V), one pass (`planValidatorPasses`, default 1).
    It runs last because two of its jobs only make sense against the final plan: every claim the Fix round rewrote is
    a claim nobody has checked, and its review-axis upgrades are binding on the reviewers you are about to choose at
    step 9, with no later moment that could apply them.
    Wait: `wait_for.py --timeout 240 $RUN/plan-validation.md`.
      PLAN_VALID      → 6d
      PLAN_NEEDS_FIX  → a fresh `teamlead:planner` in Fix mode (brief F) with the validation file; wait exactly as in
                        6b. new_paths=yes and a second pass is configured → re-validate (brief V, pass 2) → 6d.
    An upgraded `input:` or `hot:` tag REPLACES the planner's for step 9. The validator may only ever move a tag from
    `no` to `yes`; a tag it moves the other way is a bug in its report, not an instruction — keep the `yes`.
6d. HOLD GATE — dispatch unless one of these is true, in which case say why and ask before going on:
      · humanReadablePlan=pause — the user asked to read the plan first, by name.
      · plan-validation.md's `Smaller:` names a cut → the scope card: header "Scope", one option per `A)`/`B)`/`C)`
        line, `label` = "<letter>: <the words before its colon>", `description` = the rest of that line, its price
        included. A taken cut is one more Fix round (brief F, `Scope decision:`), then dispatch.
      · plan-triage.md has CONFIRMED rows — the plan was wrong somewhere and has just been rewritten; the user gets
        to see what it now says.
      · complex=yes AND no design review ran — the expensive shape of task with nothing having graded its design.
    `--autopilot` skips all of these EXCEPT an explicit `humanReadablePlan=pause`. complex=yes with a clean design
    review is no longer a stop on its own: the review is the check that pause was standing in for.
7.  Dispatch a `teamlead:implementer` for every ready workstream (wave 1) in ONE message (brief I each). The briefs
    exist; there is nothing to compose. Then one wait call for the whole wave (rule 11):
    `wait_for.py --timeout 480 $RUN/implementer-ws<N>-r<M>.md …` (one path per stream; exit 1 surfaces a blocked stream early).
8.  Implementer returns its status block: done → 8a · partial/blocked → "Synthesis" · refactor request → decide.
    Spot-check: git log --oneline, git show --stat <hash>.
8a. Spawn `teamlead:verifier` (brief G); wait: `wait_for.py --timeout 120 $RUN/verifier-r<M>.md` → `OUTCOME:` line.
      PASS                          → 9
      FAIL, touched=yes/unclear     → you write briefs/impl-ws<N>-r<M+1>.md (rework brief, "Triage" below;
                                      ## Verifier output = "read $RUN/verifier-r<M>.md, the FAIL commands") →
                                      a fresh `teamlead:implementer` (brief I, round M+1) → 8.  Counts toward the cap.
      FAIL, every failure touched=no → pre-existing: treat as PASS, report to the user, → 9
      CANNOT_RUN                    → environment problem, NOT a code failure: fix the command in the brief /
                                      ask the user. Never send it to an implementer as "your tests failed".
9.  Spawn the REVIEWERS in parallel, in the same turn the PASS arrives (brief R each). `code-review` always, and
    it has no setting. Each specialist is chosen per workstream from $RUN/config.json and that stream's axis tag —
    `input:` for security, `hot:` for perf, as the validator left it (6c), not as the planner first wrote it:
      setting      tag=yes                    tag=no
      on           opus, full review          sonnet, bounded sanity pass (rule 3)
      when-needed  opus, full review          NOT SPAWNED
      off          NOT SPAWNED                NOT SPAWNED
    `when-needed` is the one row that deletes a review rather than shrinking it, so say in your between-rounds
    update which specialists did not run and on whose tag — a reviewer that found nothing and a reviewer that never
    ran are indistinguishable in a final report, and that is precisely the confusion to prevent.
    code-review gets `public:` — on `yes` it also runs the public-surface checklist (reviewer.md item 3a).
    Wait once for the whole set: `wait_for.py --timeout 480 $RUN/review-r<M>-code.md $RUN/review-r<M>-security.md …`. After a rework the set is TARGETED: code always,
    a specialist only if your triage put it in the re-review set.
10. TRIAGE — you, following references/roles/triage.md: read the review files, write $RUN/triage-r<M>.md.
      APPROVED / APPROVED_WITH_NOTES → 11
      NEEDS_REWORK → write briefs/impl-ws<N>-r<M+1>.md (rows merged, spec-growth rows demoted to Notes) →
                     a FRESH `teamlead:implementer` (brief I) — never a SendMessage resume → 8
      Rework cap: the configured cap per workstream (`reworkCap`, default 3; `run_state.py` resolves it).
                    One NEEDS_REWORK past it = STOP: the plan or the spec is wrong, not the coder.
    Dependent workstreams (wave 2+) dispatch the moment their deps are approved — in the same turn.
11. Any demoted row or deferred refactor → spawn `teamlead:writer` for the ledger (brief L,
    references/deferred-work-ledger.md) in this turn; nothing demoted or deferred → no writer.
    Write $RUN/final-report.md following references/roles/scribe.md and send its text to the user
    (+ refactor decisions, created ADRs, the ledger path and its row count, and every specialist that
    `when-needed` left unspawned, with the tag that decided it).
    codexCodeReview=on → end with the one-liner `/teamlead:codex-review <worktree>` rather than running it:
    an independent review of a finished diff is its own 10–20 minute loop with its own findings triage, and
    folding it in here would hide a second round of cost behind one command.
```

## Pointer briefs — the only prompts you write

Resolve `$RUN` and `$PLUGIN` to absolute paths in every prompt — `$PLUGIN` is the `PLUGIN_ROOT=` line the kickoff printed. Only brief R still needs it, and a resolved path is what it needs: a `${...}` written into a subagent prompt arrives literally, because a prompt is not a shell.

The six `teamlead:<role>` agents each carry their own role file, tool set and model. Do not name a role file, list tools, or pass a `model` for them — the brief is the per-run facts and nothing else. Each brief below is complete as written; add a line only for a fact that exists in no file.

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
Inputs: $RUN/plan-validation.md, $RUN/plan.md, $RUN/briefs/*.md, $RUN/repo.txt.
Scope decision (only when the user took a cut): <the chosen option line, verbatim from ## Smaller / none>
Answers (only when the user settled a question that touches the plan): <each as `n. <question, short> → <the answer, verbatim>`>
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

**I — implementer** (`teamlead:implementer`; a fresh agent every round)
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
Inputs: $RUN/briefs/impl-ws<N>-r<M>.md (## Verification commands), $RUN/implementer-ws<N>-r<M>.md (commits:), $RUN/repo.txt.
Output: write $RUN/verifier-r<M>.md, return the OUTCOME block + file line.
```

**R — reviewer** (`code-review` for code, `performance-engineer` for perf, `general-purpose` for security; opus — except a specialist with tag `no`, which runs on sonnet). The one brief that still carries a role pointer and a tools line, because these types belong to the harness, not to this plugin.
```
Role: read and follow $PLUGIN/references/roles/reviewer.md. $RUN = <abs>. Repo: <abs>.
Axis: <code|security|perf>. Workstream: WS-<N> (<name>). Round: <M>. <infix line as in G>
Inputs: $PLUGIN/references/review-standard.md (first, and again right before you write), $RUN/plan.md ## WS-<N> block only, $RUN/briefs/impl-ws<N>-r<M>.md, $RUN/implementer-ws<N>-r<M>.md, $RUN/verifier-r<M>.md, $RUN/task.md, CLAUDE.md, commits: <hashes> (git show each).
<code: You own spec/ADR conformance, observable acceptance, the test plan item by item, TDD, the simplicity gate, mutation probes (two or three load-bearing criteria; the `## Probes` section reports every probe, the killed ones included, each line citing `<file>:<line>` mutated and a `killed by <file>::<test>` that resolves in the tree, and a SURVIVED line always carries a findings row); re-run the verification commands once. Planner tag for you: public surface=<yes|no> (reason under "Review axes" in the WS-<N> block) — `yes` → also run item 3a, the public-surface checklist; `no` → skip it.>
<specialist: Planner axis tag for you: input|hot=<yes|no> (reason under "Review axes" in the WS-<N> block). yes → full review on your axis; no → Sanity pass with the three required statements. Never re-run the suite or probe mutants — the verifier's PASS is your evidence.>
<settled decisions, when the round has any: Settled, do not re-open — <each decision verbatim, with the consequence that was accepted>. Still verify it against the code; a recorded justification can be false.>
<round ≥ 2: Re-review after rework — $RUN/triage-r<M-1>.md holds the previous rows. Rework commits: <hashes> — `git show` these and nothing older; re-check only your rows and these lines. Verification commands once. Rework is <test-only: no mutation probes, read the diff's `-` lines instead | production: probe only the changed lines>.>
Output: write $RUN/review-r<M>-<axis>.md in the shape review-standard.md prescribes; return the VERDICT line + file line.
Tools: Read, Grep, Glob, Bash (git show<, verification commands for code>). Write only your review file. Never edit the repo. No Skill tool, no agents.
```

**The settled-decisions line in `R` is the cheapest round you will ever save.** A reviewer holding the code and the spec but not the decision record reads a deliberate choice that looks locally wrong — a rethrow that aborts a success path, a filter that narrows a constant, an accepted inconsistency — re-derives it as a defect, and files a HIGH that is indistinguishable from a real finding until someone digs up the exchange that settled it. Its reasoning is sound; your brief simply omitted the decision. So before dispatching reviewers, list what the round has settled (`plan.md`'s `## Decisions taken`, the user's answers in `questions.md`, anything you adjudicated at a previous triage) and paste each into **every** reviewer brief verbatim, **with the consequence that was accepted** — the consequence is what makes it a decision rather than an assertion. Two follow-ons: a decision worth pinning in a brief is worth an ADR or a repo doc, because one that lives only in scrollback gets re-litigated by the next session; and a rejected finding is still worth mining, since a wrong remedy often surfaces a real gap the original decision never covered.

The return lines are **routable**: you route on `status:`, `OUTCOME:`, `VERDICT:` and open the file only when the line does not settle the decision (a `blocked` question, the rows at triage).

## Reference files

| When | File | What it holds |
|---|---|---|
| always | `references/run-directory.md` | `$RUN` layout, who writes what, the pointer-brief skeleton, the two rules (a report is a file first; nobody retypes what is on disk) |
| brief R | `references/roles/reviewer.md` | the reviewers' instruction set — the one role file your brief still names, because those types are the harness's, not this plugin's. The six `teamlead:<role>` agents load their own from `references/roles/`; you neither paste nor name those |
| step 10 | `references/roles/triage.md` | your triage procedure: worst wins, de-dup, demote spec growth, re-review set, rework brief template, cap |
| step 11 | `references/roles/scribe.md` | the final report shape (5–12 lines) |
| step 11 (if anything was demoted/deferred) | `references/deferred-work-ledger.md` | what goes in `<repo>/docs/deferred-work.md`, brief L, the append-safety rules (never `Write` over it, never commit) |
| R | `references/review-standard.md` | the report shape reviewers read for themselves; you route on its Verdict line |
| 2 / 5 / 11 | `references/adr-workflow.md` | ADR location, selection into `$RUN/adrs.md`, conflict gate, `--adr` creation (3-part test, append-only) |
| 2 (optional) | `references/understand-first.md` | read-only as-is discovery + second-agent validation before planning unfamiliar code |
| 4a (design review) | `references/roles/plan-reviewer.md` | the plan design reviewer's instruction set — carried by `teamlead:plan-reviewer`; you neither paste nor name it. Read it yourself only to triage its rows at step 5 |
| 4a / 6b (human plan) | `references/plan-human.md` | what `$RUN/plan-human.md` contains, and the `## Changes since you last read this` rule for regenerating it |
| 4a (complex) | `references/execplan-template.md` | the four living sections the writer appends to `$RUN/plan.md`, and why the plan stays out of the repo |
| refactor requests | `references/refactor-workflow.md` | Steps A–E (test agent → review → refactor → review → resume) |

## Docs as the spec — extract, carry, conform

Bringing docs into the loop fixes a specific failure: an implementer that writes clean code for the *wrong* behaviour, and a reviewer that only grades quality and never notices. The **planner** extracts a verbatim spec excerpt per workstream (source priority: a doc the user pointed to → repo design docs → PLAN.md → the user's verbatim task) and places it inline in the `## WS-<N>` block of `plan.md` and in the round-1 brief. The **implementer** builds exactly that; ambiguity → `status: blocked` with the question, never a guess. **`code-review`** is the only reviewer that grades conformance, requirement by requirement; clean code that builds the wrong thing is NEEDS_REWORK. **Specialists** get the same excerpt as context (data flow, attacker-controlled inputs, hot paths) and grade only their own axis — one conformance verdict, not three colliding ones.

Reviews are written for the next coder, not for a human: a severity-tagged findings table of what to change, no praise, no list of passes (`references/review-standard.md`). You write the human summary at the end.

## ADRs as durable constraints — read always, create on `--adr`

Architecture Decision Records are the standing record of *why* the architecture is the way it is; violating one is building the wrong thing, exactly like a spec violation. Mechanics: `references/adr-workflow.md`. Shape: resolve the location once (step 2); index titles and **select** the ADRs relevant to the task into `$RUN/adrs.md` — the planner attaches the relevant clauses per workstream like spec excerpts and `code-review` enforces them; **conflict → halt** before dispatch and ask (revise / proceed-and-supersede / override-once); **create only with `--adr`**, only for decisions that are hard to reverse AND surprising without context AND a real trade-off, via a delegated sonnet writer, `status: proposed`, file only, append-only (supersede with a new ADR, never edit an old one).

## Keeping the plan alive on complex tasks

Trigger: the planner returns `complex=yes` (≥3 workstreams or any stream rated L). `$RUN/plan.md` then continues past the planner's output as a living ExecPlan — resumable by a cold agent, auditable through its Decision Log. Structure and rationale: `references/execplan-template.md`.

**The plan never becomes a repo file.** It is a run artifact from first write to last, so a run leaves nothing untracked in the tree for the user to commit or gitignore, and there is no second copy of the spec excerpts to drift from the planner's. The only repo files this run may create are an ADR and `docs/deferred-work.md`.

1. In the same turn the planner returns (with the validator), spawn `teamlead:writer`: "Append the four living sections of your role file's execplan template to the END of `$RUN/plan.md` — a Progress checklist built from its workstreams and waves, then headed-but-empty Surprises & Discoveries, Decision Log, Outcomes & Retrospective. Change nothing the planner wrote and restate none of it."
2. Put the `$RUN/plan.md` path — and `$RUN/plan-human.md`, when it exists, as the one to actually read — in the preamble of step 6, and leave the confirmation itself to the hold gate at 6d. The gate is after the Fix rounds on purpose: a confirmation collected at step 6 approves a draft that two rounds of amendment are about to change, which is the kind of approval that looks like a gate and is not one. The user edits the plan in place; it is the same file the implementers, reviewers and codex all read, so there is no override to relay.
3. **Keep it alive**: after each synthesis and each triage, spawn a writer to tick `Progress` and append to `Decision Log` / `Surprises & Discoveries` — one section at a time, never a rewrite. A decision that lives only in this chat is invisible to the next round and the next session.

Simple tasks (1–2 workstreams, all S/M) leave `plan.md` as the planner wrote it: the four living sections buy nothing on two streams and cost a writer spawn at every stopping point. **On resume** (new session or after compaction): run `python3 $PLUGIN/scripts/run_state.py $RUN` first. It prints the step and the one next action from the file set, so you spend no turns reconstructing a transcript you no longer have; exit 1 means the next action is the user's, not yours. Then read what it points at — `$RUN/plan.md`, the latest `triage-*.md` — plus `git log` since, and take that one action. Remember every subagent died with the previous session: an expected file that is absent means spawn it again, never wait.

## Synthesis (after implementers return)

1. Route on the returned status block. `done` → spot-check and 8a. `partial` → do not send a half-stream to the verifier; re-brief a fresh implementer with a pointer to the report's "what's left" (a rework brief with one row). `blocked` → read the question in the report file: spec ambiguity or a product call → the user; "where is X / how does Y work" → answer it from the codebase or an Explore, write the rework brief with the answer, fresh implementer. Never guess on the implementer's behalf. `confidence: med|low` is an annotation, not a gate — say why in the between-rounds update and hand a checkable reason to the reviewers as a focus line.
2. Spot-check: `git log --oneline`, `git show --stat <hash>` for one or two commits per stream.
3. Conflicts between agents (X vs ¬X): surface to the user or spawn a tiebreaker; never paper over.
4. Persist to the living sections of `$RUN/plan.md` if they exist (writer, one section at a time). With `--adr`, graduate qualifying decisions (3-part test) — most will not qualify.

## Verifier gate — run the tests before you pay for review

Three opus reviewers are the most expensive step; a cheap sonnet gate first means a red suite costs one small agent instead of three large ones, and reviewers start from a known-green tree. The three outcomes are the whole point: **PASS** → review; **FAIL** on tests the change touched → rework with the verifier file as the evidence (the coder needs the traceback, which is in the file, not "tests failed"); **CANNOT_RUN** (missing binary, wrong cwd, 126/127, sandbox denial, timeout) → an *environment* fact, never a coder's failure — an implementer told its tests failed will "fix" working code round after round. In a monorepo the planner scopes the commands to the package; pre-existing failures the change did not cause go to the user, not to the implementer.

## Triage (step 10) — you, following `roles/triage.md`

You read the review files of the round and write `$RUN/triage-r<M>.md`: **worst verdict wins**; **one row per defect** (reviewers report the same bug three ways — merge, name the reviewers, keep one Fix); **demote to Notes** every row that grows the spec (input types or ranges the spec does not admit, extra hardening, a micro-benchmark on a non-hot path) with the reason next to it — the user grows the spec, not the reviewer, and if the only rows were demoted the verdict becomes APPROVED_WITH_NOTES; **decide the re-review set** for the next round with a written basis per specialist (code always; security if it raised a row or the rework touches production code on its axis; perf if it raised a row or the stream is `hot: yes`); **enforce the cap** (rework count at the configured cap → STOP with the findings history and your read: ambiguous spec? wrong decomposition? reviewer and implementer disagreeing?).

On NEEDS_REWORK write `briefs/impl-ws<N>-r<M+1>.md` from the template in `roles/triage.md`: a pointer to the previous brief and report, the merged rows verbatim, `## Verifier output` as a pointer to the verifier file when it failed, test-plan additions, the report file name. Then a **fresh** `teamlead:implementer` (brief I). Rework is never a `SendMessage` resume: the anchored coder that missed once misses the same way twice, and the files make the fresh start free — nothing has to be re-explained.

## Refactor requests — what the teamlead does

An implementer's report may include a refactor request (what / why / risk of leaving it). **Evaluate** (does it unblock the task? blast radius? real risk or aesthetics?), **decide** Reject / Defer / Approve, **append the decision** as one line to `$RUN/refactor-decisions.md`, and **surface it** to the user in your next update. Approve → `references/refactor-workflow.md` Steps A–E; never bundle test-writing, refactor and feature into one agent. The file is what the final report and the deferred-work ledger read from; a decision that exists only in your update reaches the user once and the next run never.

## Choosing subagent type & model

The six pipeline roles are plugin agents, so this is already decided for them — spawn the type and pass no `model` (rule 3). **The type is namespaced by the plugin**, exactly as the commands are (`/teamlead:delegate`): `subagent_type: "teamlead:planner"`. The bare name is not registered and fails with `Agent type 'planner' not found`; recovering from that by falling back to `general-purpose` would silently lose the pinned model and tool set, which is the whole point of the agent.


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
| Security review | `security-review`, or `general-purpose` if that type isn't registered | **opus**; **sonnet** for the sanity pass on `input: no`. Not spawned at all when `securityReview` is `off`, or is `when-needed` and the tag is `no` |
| Performance review | `performance-engineer` | **opus**; **sonnet** for the sanity pass on `hot: no`. Not spawned at all when `perfReview` is `off`, or is `when-needed` and the tag is `no` |
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

If a workstream is too coupled to split, run it as one agent — don't fake parallelism by giving two agents the same scope. **Spawn floor**: below roughly 3 files / 200 changed lines one implementer is faster than two. Never spawn an agent to "look into" something open-ended — write the question first, then decide whether it is an Explore call or a `Grep` you can run yourself.

## Parallelism rules

**Safe to parallelise**: disjoint file scopes; multiple read-only agents; multiple reviewers on the same diff; workstreams that converge on a synthesis step.

**Must serialise**: plan → implement → review for one workstream; two agents that would write the same file; a prompt that depends on another agent's findings; two agents touching the same dependency manifest or lockfile (Cargo.toml/Cargo.lock, package.json/package-lock.json, pyproject.toml/uv.lock, go.mod/go.sum) — concurrent writes there corrupt silently; serialise, or let one agent own the manifest. Parallel implementers share one tree: the brief tells each to stage only its own files by path.

## Sanity-check before each launch

- Could a single `Bash` / `Read` / `Grep` answer it? Then do it directly.
- Does the prompt name the absolute `$RUN`, the input files, the output file — and, for a reviewer, its role file?
- Did I add only facts that are in no file (flags, axis tag, commits, re-review set) — and nothing that is?
- For parallel calls: are scopes truly disjoint?
- A `teamlead:<role>` agent: no `model`, no role file, no tools line. A reviewer or ad-hoc agent: right `subagent_type`, right `model` (opus for thinking, sonnet for reading), tools line present with "no Skill tool, no agents"?

## Output to the user

Between rounds, 1–3 sentences: "Plan: 3 workstreams (A, B, C); A and B parallel, C depends on A. Validator: PLAN_VALID. Two open questions below." · "A+B landed, verifier PASS, reviewers running (code+security+perf)." · "Triage: 2 rows (code-review, security) → rework 1, fresh implementer." End of task: the text of `$RUN/final-report.md` (5–12 lines: delivered, commits, who did what, manual checks, Notes, deferred).

## Anti-patterns

- **Writing repo code yourself "just this once"** — breaks the contract.
- **Retyping a file into a prompt** — the spec excerpt, the plan, a report tail, the verifier output. Name the file. Every retyped kilobyte is a minute on the critical path and a copy in your context.
- **Reading a report file when the return line already routes** — open `implementer-*.md` only for `blocked`/`partial`, review files only at triage.
- **Resuming an implementer with `SendMessage` for a rework** — always a fresh `teamlead:implementer` with the rework brief.
- **Passing a `model` to a `teamlead:<role>` agent** — it pins its own, and yours would override it silently.
- **Using opus for code or sonnet for planning** in the agents you do choose — the assignment is fixed.
- **Sequential delegation when parallel is possible**; **skipping review because the implementer said it works**; **treating "all green" as evidence** — the verifier exists because the author is the least reliable witness.
- **Feeding CANNOT_RUN back as "tests failed"** — environment, not code.
- **Unbounded rework loops** — the configured cap of reworks per stream (default 3), then STOP and escalate.
- **Dropping reviewers' Notes** — relay them; **inflating Notes into gates** — only a named, verifiable defect blocks.
- **Forwarding a spec-growth row to a coder** — demote it to a Note; the user grows the spec.
- **Silently absorbing scope drift** — out-of-brief edits are a row demanding a revert.
- **Letting an implementer refactor on its own**, or **approving refactors silently**.
- **Paraphrasing the user's complaint or the spec** — pass verbatim; wording carries intent.
- **Relaying the open questions as one prose block, or an option whose label is a bare letter** — the user cannot answer "C" without scrolling back to decode it. One card per question, every option labelled with its own words (step 6).
- **Claiming visible/runtime success without manual checks** — tests can't see UI, audio, feel.
- **Adding the living ExecPlan sections to a trivial task's plan**; **dispatching past the hold gate at 6d**; **writing a `PLAN.md` into the repo** — the plan is a run artifact and a run must leave no untracked plan behind.
- **Reading the flag text or this transcript for a run option** — `$RUN/config.json` is the record, and it is the only one that survives a compaction.
- **Waiting on the Codex plan review, or letting it block dispatch** — it is a background call whose notification returns to you, and a Codex that is unavailable, failed or timed out is reported and stepped over.
- **Reviewing the plan yourself instead of triaging the review** — an independent read is the whole product; your job on the way back is that no row is lost and no row is rejected without evidence.
- **Spending the second plan Fix round on design** — 6b folds every CONFIRMED row and every answer at once, and the round after it belongs to the validator's factual corrections.
- **Letting a `when-needed` skip go unmentioned** — a reviewer that never ran reads exactly like one that found nothing.
- **Barreling past an ADR conflict**; **editing an existing ADR**; **creating an ADR without `--adr`**; **committing a created ADR or the deferred-work ledger**.
- **Letting a demotion or a `defer` end in a chat message** — both are decisions about the repo; they go in `docs/deferred-work.md` or the next run re-litigates them.

## When this skill is NOT the right tool

- The user said "just do it" or "you implement it" → implement directly.
- A read-only one-shot question fits in a single `Grep` / `Read` → answer directly.
- Trivial single-line edits where delegation overhead dwarfs the work → just do it and tell the user.

If unsure, ask the user one sentence: "Coordinate via teamlead workflow, or handle this directly?"
