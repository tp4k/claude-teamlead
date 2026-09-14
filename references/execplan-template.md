# Living ExecPlan — the tail of `$RUN/plan.md`

On complex tasks `$RUN/plan.md` does not stop at the planner's output: a sonnet writer appends four living sections to it and keeps them current as work proceeds (the trigger is in SKILL.md "Keeping the plan alive").

**It lives in the run directory, not the repo.** An earlier version of this plugin copied `plan.md` into a `<repo>/PLAN.md` that the user then had to commit or gitignore. That bought nothing the run directory does not already give — and it cost a faithful-transcription step, a file the writer could clobber, and machine-specific detail leaking toward a committed file. One file, one copy: the planner writes its head, the writer extends its tail.

**Why a living document and not a one-shot dump.** A static plan goes stale the instant an implementer diverges, and the *reasons* behind each choice evaporate when the session ends — so the next round (or the next session, or the user editing between sessions) is flying blind. A living ExecPlan fixes three things at once:

- **Resumability** — a cold agent (or you, days later) can restart from *only this file* with no prior context. That is the bar: self-contained.
- **Auditability** — the `Decision Log` records *why* a path was chosen, so "trust but verify" has something durable to verify against.
- **State** — `Progress` always reflects the real current state, so nobody re-does landed work or skips remaining work.

This is the same discipline that makes spec-driven workspaces and their ExecPlans produce restartable, reviewable plans instead of throwaway notes.

## When to use it

Same trigger as before: **≥3 workstreams OR any workstream rated complexity L.** For simple tasks (1–2 streams, all S/M) `plan.md` stays as the planner wrote it — the cost being avoided is not disk space but the writer spawn after every synthesis and triage, which is real overhead on a two-stream task and leverage on a six-stream one.

## Hard requirements

1. **Self-contained.** Assume the reader knows nothing but the working tree and `plan.md`. Name files by full repo-relative path. Define any term of art in plain language. Never write "as decided above" without the decision also being in the `Decision Log`.
2. **Living.** Update it at every stopping point — after each implementer round, each reviewer round, each decision. A stopping point that leaves `Progress` stale is a process failure.
3. **Prose-first.** Narrative sections are sentences, not bullet salad. The **only** place checkboxes are mandatory is `Progress`.

## Skeleton

The planner already wrote the head of `plan.md` — `## Goal`, `## Workstreams`, the per-stream blocks with their inline spec excerpts and observable acceptance, the DAG, `## Decisions taken`, forbiddens, anti-scope. **Do not restate any of it**; a second copy of a spec excerpt is a second copy to drift.

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

Keep each update **minimal and targeted** — a writer agent editing one section at a time, not a full rewrite. A full rewrite risks dropping earlier `Decision Log` / `Surprises` history, which is the whole point of the file, and here it would also take the planner's head of `plan.md` with it.
