# Understand-first — read-only as-is discovery before planning

Use this optional discovery pass at delegate step 2 when an incorrect understanding could invalidate the plan. Discover current behavior before choosing the decomposition.

## Why it exists

A guessed model can propagate through planning and implementation until review discovers the mistake. By then the run has spent a planner, implementers, and reviewers. A read-only trace followed by independent validation can identify the error earlier. Skip discovery when the mechanism is already clear.

## When to run it

Run when at least two conditions hold:

- Existing behavior changes and nobody explained the mechanism in this session.
- The interaction spans components, files, or services and is unclear.
- A false assumption, such as synchronous execution versus queueing, would invalidate the plan.
- The request asks how something works before changing it, or asks why behavior occurs.

Skip localized changes with an understood mechanism.

## Two flavours

1. **Lightweight:** an opus tracer returns a concise explanation of current behavior.
2. **Diagrammed:** add one to three diagrams when requested or when a complex interaction benefits from a visual. Avoid rendering work for a flow explainable in two sentences.

Both require a different agent to validate the trace. An unchecked explanation retains the original factual risk.

## Step 1 — Tracer (read-only, opus)

Subagent: `Explore` or `general-purpose`, model **opus**. Read-only.

```
You are explaining how a piece of the system works TODAY in {repo path}. READ-ONLY — do not edit or change state. Do not propose changes or a redesign; this is an as-is explanation only.

MUST READ FIRST: CLAUDE.md (project + user-global).

The question to answer (verbatim from the user): "{user question / task}"

Trace the current behaviour end to end for ONLY the slice that question is about:
- Name the entry point(s) and follow the real control/data flow through the code.
- Cite concrete locations (file:line) for every claim.
- Separate clearly: what is CONFIRMED in code (with citation), what is INFERRED (and why), and what is UNCLEAR / you couldn't determine.
- Note the key data structures, external calls, async/queue boundaries, transactions, and error/edge handling on this path.
- Keep it scoped to the question — no whole-system dump.

Deliverable: a concise as-is explanation (prose-first), with a CONFIRMED / INFERRED / UNCLEAR split and file:line citations. {If diagrammed: plus one to three focused diagrams showing only what's relevant — sequence for time-ordered flow, flowchart for branching.}
```

## Step 2 — Validator (read-only, opus, fresh agent)

A **different** opus agent validates the trace against the code — the tracer cannot catch its own mistakes.

```
You are validating an as-is explanation against the real code in {repo path}. READ-ONLY.

Original question the explanation must answer (verbatim): "{user question}"

The explanation to validate (verbatim):
{tracer output, including its CONFIRMED/INFERRED/UNCLEAR split and any diagrams}

Check every claim against the code:
- Does each cited file:line actually say what the explanation claims?
- Is anything marked CONFIRMED that is really inferred or wrong? Flag it.
- Is any important step on this path missing or misordered?
- {If diagrams: does each diagrammed interaction match the code? Flag inaccuracies and unsupported steps.}

Report: VALID / NEEDS_FIX, plus a findings list (claim → reality file:line → correction). Only report problems. If accurate, say so in one line.
```

For NEEDS_FIX, correct the explanation using the findings. Redispatch the tracer or correct the explanation inline. Continue until code supports it or remaining uncertainty is explicit.

## Step 3 — Feed it into planning

Provide the validated explanation to the planner as current-behavior context. Keep CONFIRMED, INFERRED, and UNCLEAR distinctions. UNCLEAR items can become open questions. INFERRED items require cautious claims. Prefer an input artifact path when one exists, following the pointer-brief rule.

Keep the artifact concise unless the user requests a durable report. Establish correct understanding before planning.
