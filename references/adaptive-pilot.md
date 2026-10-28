# Adaptive workflow pilot

Default: `workflowProfile: "standard"`. Opt in per run with
`--workflow-profile=adaptive`, or set the matching repository/user config key.
The opt-in selects an assessment, not an unconditional shortcut. Keep existing
defaults until outcome evidence supports changing them.

## Eligibility and routing

The planner identifies the consumer, affected callers, storage/protocol boundary,
existing library, and executable acceptance before prescribing tests. Consolidate
compatible small work into one stream. Planning, configured design review,
validation, user decisions, and explicit holds keep their current behavior.

After writing a valid plan-validation report, the validator can record this
assessment in `$RUN/workflow-assessment.json`. Replace the evidence placeholders
with actual paths, caller traces, commands, and results. Every risk needs an
explicit false; absent or uncertain facts retain the standard workflow.

```json
{
  "fingerprint": "output of workflow_profile.py RUN --fingerprint",
  "bounded": true,
  "risks": {
    "uncertain": false,
    "storage": false,
    "protocol": false,
    "security": false,
    "concurrency": false,
    "migration": false
  },
  "evidence": {
    "consumer": "the actual consumer and its requirement",
    "callers": "affected callers and why their contracts remain intact",
    "boundary": "trace showing no storage or protocol behavior changes",
    "library": "existing helper/library and installed version when relevant",
    "verification": "executable acceptance and available harness evidence"
  }
}
```

Get the fingerprint with:

```sh
python3 "$PLUGIN/scripts/workflow_profile.py" "$RUN" --fingerprint
```

Only one S-sized stream with explicit file scope, all three review-axis tags
`no`, an enabled scope fence, and an enabled independent final review qualifies.
Explicit `securityReview=on` or `perfReview=on` retains standard stages. The
fingerprint covers the plan, questions, validator report, and initial briefs.
Edits invalidate the assessment; do not refresh it without rechecking the facts.
Every rework round uses standard stages. Missing assessments require no extra
approval or waiting: run the standard workflow.

For an eligible first round, `next.py` still runs the baseline, implementation,
verification, RED/freeze and mutation checks. It checks snapshot freshness before
skipping per-stream reviewers and triage. The independent cumulative final gate
and its triage still run; gate verification must be COMPLETE. Execution blockers
and rework caps keep their existing behavior. Never equate eligibility with
approval or a zero-mutant PASS with measured coverage.

For shared resource-heavy database verification, place
`verification resource: shared-database` in each affected initial brief. Baseline
batches containing such a stream run one verifier at a time. All post-change
verifiers already run serially because RED and mutation checks alter the shared
tree. Implementer checks need isolated databases or coordinator serialization.

## Current briefs and decisions

The router generates `briefs/current-ws<N>-r<M>.md` from the current authored
brief plus the nearest inherited scope, specification, acceptance, rules, and
verification sections. It retains source paths. Read this view first, then the
previous report and relevant findings; use older files for unresolved context.
Authored briefs remain the scope hook's authority and the audit trail.

Use the `decision-records` block described in [triage.md](roles/triage.md) for
explicit fix/decline/defer choices. Stable IDs and increasing revisions preserve
choices across rounds. Omission does not delete a choice. Conflicting records
at the same revision halt instead of silently choosing one. Current decisions
reach implementation, review, triage, and the independent final review package.

## Measurements

Keep raw PR reviews, transcripts, replay responses, metrics, and pilot manifests
under private `$RUN` directories outside the public repository. Only sanitized
evaluation inputs belong in `evals/generated-pr-outcomes/`.

The coordinator is the sole metrics writer; run manual measurement commands between router calls. `next.py` writes `$RUN/metrics.json`. Phase durations measure dispatch to observed
completion, including coordinator delay. A retry preserves the first start;
unfinished phases have null duration. Do not call this pure model execution time.
Record planning stages similarly around their dispatch/wait:

```sh
python3 "$PLUGIN/scripts/run_metrics.py" start "$RUN" planning
# dispatch planner and wait for its artifacts
python3 "$PLUGIN/scripts/run_metrics.py" finish "$RUN" planning
```

The router imports available `turn.completed` usage from successful Codex gate event logs. Other provider usage and planning measurements require the commands below. When provider usage is available, record its actual fields and source. Cached
input, uncached input, and output are separate. Do not assume a provider's input
field excludes cached input. Omit unavailable fields; the file records null and
the source/reason. Never estimate tokens from text length or fill missing values
with zero.

```sh
python3 "$PLUGIN/scripts/run_metrics.py" usage "$RUN" planning \
  --cached 1200 --uncached 350 --output 400 --source 'provider usage event path'
```

Record rework causes with evidence. The router records one event per rework
round; verification distinguishes mutation and command failures. Review briefs
should attribute planning assumptions, incomplete fixes, weak tests,
reviewer-induced regressions, or implementation defects. Unknown attribution
must remain explicit.

After the PR is reviewed, record only confirmed findings: an accepted correction
or executable reproduction, not every reviewer suggestion. Record the observation
date and review coverage even when there are no findings. Until then the defect
count is unavailable, not zero.

```sh
python3 "$PLUGIN/scripts/run_metrics.py" event "$RUN" finding-1 \
  --kind confirmed-pr-finding --cause 'incomplete fallback fix' \
  --source 'private review path and confirmed reproduction'
python3 "$PLUGIN/scripts/run_metrics.py" observe "$RUN" \
  --source 'reviewed on YYYY-MM-DD; review/reproduction evidence path'
```

## Replay, then ten tasks

First run the deterministic suites, including `scripts/test_outcomes.py`.
Replay every sanitized case in `evals/generated-pr-outcomes/cases.json` using
the updated planner/reviewer/triage instructions. Give the evaluator only the
case and instructions, not `expected.json` or previous conclusions. Record its
action, reasoning, evidence, and proposed verification privately. Compare with
the expected action **and manually check the reasoning**: matching a label or
phrase is not evidence of good judgment. In particular, an assertion change
must identify authorized behavior, and a storage test must reach persistence.
Fix missed cases and replay before enrolling live tasks.

The live pilot is opt-in and requires ten actual tasks; do not invent completed
tasks or execute unrelated work to fill the sample. Before each run, record its
scope, risk, repository, effective profile, and a comparable historical task.
Match task type, size, affected boundaries, environment, and available review
coverage. Historical tasks must have comparable measurements; report missing
data rather than reconstructing imagined timings or tokens.

Compare paired runs after comparable post-run review windows:

```sh
python3 "$PLUGIN/scripts/run_metrics.py" compare \
  /private/baseline-1 /private/pilot-1 /private/baseline-2 /private/pilot-2
```

Report elapsed phase time, each token category, rework and its causes, confirmed
post-run defects and severity, unavailable values, and actual eligibility rate.
The comparison prints available pair counts and paired median deltas. Inspect
case severity and causes separately; a lower defect count cannot offset a more
serious regression. Ten selected tasks are a small, nonrandom sample and do not
establish causality. Internal approval counts and test totals are not outcome
quality measures. Change no default solely because the pilot is faster.
