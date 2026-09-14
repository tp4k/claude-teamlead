# Refactor requests from implementers

Implementers are forbidden from refactoring on their own (see SKILL.md hard rule 9). When one returns a refactor request, **you (the teamlead) decide** — do not silently approve or ignore.

## Procedure

### 1. Evaluate the request

- Does it actually unblock the original task, or is it aesthetic?
- What's the blast radius (files, callers, tests)?
- Is the risk of leaving it as-is real (incorrect behaviour, blocked feature) or aesthetic (code smell, mild duplication)?

### 2. Decide one of three outcomes

- **Reject** — the original code is fine as-is. Reply to the implementer: "Proceed without the refactor; here's how to work around it: …" Spawn a fresh implementer with the workaround spelled out if the original one already stopped.
- **Defer** — worth doing, but not now. Continue current work without it.
- **Approve** — needed before/alongside the current task. Go to step 3.

**Record every decision in `$RUN/refactor-decisions.md`** — append one line per request: `<reject|defer|approve> — <what would change> — <your reason> (<files/symbols>)`. This costs a line and it is the only durable trace: your between-rounds message reaches the user once, and the final report cannot state a decision it has no file for. A `defer` line is also what the ledger writer copies into `<repo>/docs/deferred-work.md` (`references/deferred-work-ledger.md`), so a deferred refactor survives the run instead of being re-requested by the next implementer that trips over the same code.

### 3. If approved — run a dedicated refactor workflow

**Never bundle into a feature agent.** Hard split into four sub-steps:

#### Step A — Test agent (sonnet)
Spawn a sonnet implementer whose ONLY job is to write characterisation/regression tests covering the current behaviour of the code about to be refactored. No production-code changes.

Verification: tests must pass on current code (red commit is "tests for existing behaviour", green is current code already satisfies them — these may be a single commit since they describe pre-existing behaviour).

Report back: commit hashes and what's covered.

#### Step B — Review tests (opus)
Spawn `code-review` opus to confirm coverage is meaningful (not just smoke tests) and pins the behaviour that matters.

#### Step C — Refactor agent (sonnet)
Spawn a fresh sonnet with strict scope = "refactor X to Y; do not change behaviour; tests from step A must stay green".

Forbidden: any feature work, any new behaviour, any changes outside the refactor target.

Verification: full test suite + the characterisation tests from step A must remain green **without modification**.

#### Step D — Review refactor (opus)
Standard `code-review` opus. Confirm tests from A were not weakened to make the refactor pass.

#### Step E — Resume original work
Spawn a **fresh** implementer (NOT the same one) for the original task, now that the refactor has landed. Pass updated context.

### 4. Never bundle

Never let one agent write tests + refactor + feature in one session. Hard split.

### 5. Surface to the user

Every refactor decision must appear in your between-rounds update **and** in `$RUN/refactor-decisions.md`:

> "Implementer A asked to refactor Z; approved/deferred/rejected because …"

This keeps the user in the loop on architectural drift before it accumulates.
