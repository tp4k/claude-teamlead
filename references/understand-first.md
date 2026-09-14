# Understand-first — read-only as-is discovery before planning

An **optional** Step 0 (loop step 2b). Run it when the task touches code you don't yet understand and a wrong mental model would be expensive to discover later. It produces a grounded as-is picture *before* the planner commits to a decomposition.

## Why it exists

The teamlead's default loop jumps straight from the user's request to the planner. That's fine when the change is in well-understood code. It's a trap when it isn't: the planner builds a decomposition on a guessed mental model, implementers build on the plan, and the misunderstanding only surfaces at the review round — the most expensive place to find it. By then you've spent a planning agent, one or more implementers, and a reviewer, and you have to unwind all of it.

An explicit understanding pass is cheap insurance: a read-only agent traces how the relevant slice actually works today, a second agent validates that trace against the code, and only then does the planner run — now grounded in verified reality instead of assumption. This is a de-risking tool, not a tax: skip it for code you already understand.

## When to run it

Run it when **two or more** of these hold:
- The task is a change to existing behaviour in code neither you nor the user has explained in this session.
- The flow spans several components/files/services and the interaction isn't obvious.
- A wrong assumption about current behaviour would invalidate the plan (e.g. "it's synchronous" vs "it's actually queued").
- The user's request itself is framed as "figure out how X works, then change it" or "why does Y happen".

Skip it when the change is localised and the mechanism is already clear — don't pay for discovery you don't need.

## Two flavours

1. **Lightweight (default):** one read-only opus tracer returns a prose as-is explanation. Good enough for most "I need to understand this before changing it" cases.
2. **Diagrammed (on request / genuinely complex flows):** the tracer also produces diagram(s) of the flow. Use only when the interaction is hard to follow in prose and the user would benefit from a visual, or when the user explicitly asks. Don't over-invest in rendering for a flow that two sentences would capture.

Either way, the **validation pass is mandatory** — an unverified as-is description is exactly the hallucination risk this step is meant to remove.

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

If the validator returns NEEDS_FIX, correct the explanation (re-spawn the tracer with the findings, or fix inline) until it's consistent with the code or the remaining uncertainty is stated explicitly.

## Step 3 — Feed it into planning

The validated as-is becomes context for the planner: paste it into the planner prompt as "verified current behaviour" so the decomposition is grounded. The `CONFIRMED / INFERRED / UNCLEAR` split is especially valuable — `UNCLEAR` items often become the planner's open questions for the user, and `INFERRED` items are where the plan should stay cautious.

Keep the artifact lightweight unless the user wants a durable report. The goal is a correct mental model before planning, not a polished document.
