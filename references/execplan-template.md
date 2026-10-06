# Living ExecPlan — the tail of `$RUN/plan.md`

For complex tasks, a sonnet writer appends four living sections to `$RUN/plan.md`. It updates them as work proceeds. The delegate skill defines the trigger under "Keeping the plan alive".

Keep the plan in the run directory. Earlier versions copied it into repository PLAN.md, adding transcription work, overwrite risk, and machine-specific content near committed files. Keep one copy. The planner writes its main sections, and the writer updates only the living sections.

A static plan can become stale after implementation diverges. Unrecorded reasons disappear when the session ends. Living sections retain progress and decisions for the next round, session, or user edit.

- **Resumability** — a cold agent (or you, days later) can restart from *only this file* with no prior context. That is the bar: self-contained.
- **Auditability** — the `Decision Log` records *why* a path was chosen, so "trust but verify" has something durable to verify against.
- **State** — `Progress` always reflects the real current state, so nobody re-does landed work or skips remaining work.

This is the same discipline that makes spec-driven workspaces and their ExecPlans produce restartable, reviewable plans instead of throwaway notes.

## When to use it

Use these sections for at least three workstreams or any L-rated stream. For one or two S/M streams, retain the planner's original plan. This avoids writer dispatches after every synthesis and triage when they add little value.

## Hard requirements

1. **Self-contained.** Assume the reader knows nothing but the working tree and `plan.md`. Name files by full repo-relative path. Define any term of art in plain language. Never write "as decided above" without the decision also being in the `Decision Log`.
2. **Living.** Update it at every stopping point — after each implementer round, each reviewer round, each decision. A stopping point that leaves `Progress` stale is a process failure.
3. **Prose-first.** Narrative sections are sentences, not bullet salad. The **only** place checkboxes are mandatory is `Progress`.

## Skeleton

Preserve the planner's Goal, Workstreams, specs, acceptance, DAG, Decisions taken, project rules, and anti-scope. Do not restate them. Duplicate spec text can diverge.

Append exactly these four sections to the end of the file (via a sonnet writer — the teamlead never writes files itself):

```
## Progress

Checkboxes ONLY here. Every stopping point updates this — split a partially done
item into done vs remaining rather than leaving it ambiguous. Timestamp entries so
rate of progress is visible.

- [x] (2026-06-05 14:00Z) Example completed step.
- [ ] Example remaining step.
- [ ] Example partial step (done: X; remaining: Y).

## Surprises & Discoveries

Unexpected behaviour, bugs, constraints, or insights found while working, each with
a one-line evidence snippet (a file:line, a command output). Empty at first; grows.

- Observation: ...
  Evidence: ...

## Decision Log

Every non-trivial decision, in the format below. This is what makes the plan
auditable — a reviewer or the next session can see WHY, not just WHAT.

- Decision: ...
  Rationale: ...
  Date/Author: ...

## Outcomes & Retrospective

Filled at each milestone and at completion: what was achieved, what remains, lessons.
Compare the result against the plan's `## Goal`.
```

## How the teamlead keeps it alive

- **At plan time:** the sonnet writer appends the four headings, filling `Progress` with a checklist derived from the planner's workstreams and waves. `Surprises`, `Decision Log`, and `Outcomes` start as headed-but-empty sections — they are not optional placeholders, they are where the next updates land.
- **After each synthesis** (see SKILL.md "Synthesis"): spawn a writer to append resolved conflicts and discoveries to `Decision Log` / `Surprises & Discoveries`, and tick `Progress`. This is R7 — decisions live in the durable artifact, not only in the chat that disappears.
- **After each reviewer round:** update `Progress` (what passed, what's reworking) and log any course-correction in `Decision Log`.
- **At completion:** write the `Outcomes & Retrospective` entry before declaring done.

Have the writer update one section per invocation. Avoid full rewrites. They can erase earlier decisions, discoveries, and the planner's main sections.
