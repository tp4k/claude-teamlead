# Refactor requests from implementers

Implementers request refactors instead of performing them independently. The coordinator must decide each request and record its result.

## Procedure

### 1. Evaluate the request

- Does it unblock the task or merely change style?
- Which files, callers, and tests would change?
- Would deferral cause incorrect behavior or block a required feature? Distinguish those risks from mild duplication or code smells.

### 2. Decide one of three outcomes

- **Reject:** explain how to continue without the refactor. If the implementer stopped, give the workaround to a fresh instance.
- **Defer:** record the future work and continue the task.
- **Approve:** perform the separate workflow below before or alongside the task, as dependencies permit.

Append `<reject|defer|approve> — <proposed change> — <reason> (<files/symbols>)` to `$RUN/refactor-decisions.md`. Report the decision in the next update. The final report needs this durable record. The ledger writer copies defer entries to `docs/deferred-work.md`.

### 3. If approved — run a dedicated refactor workflow

Keep characterization tests, refactor, and feature work in separate agent invocations. Use these five steps:

#### Step A — Test agent (sonnet)

Dispatch a sonnet implementer to write characterization or regression tests for current behavior. Permit no production changes. Require the tests to pass against existing code. This is coverage of existing behavior and can use one tests-only commit rather than a new behavioral RED. Report hashes and covered behavior.

#### Step B — Review tests (opus)

Dispatch code review on opus. Check that the tests exercise and preserve meaningful behavior rather than only basic execution.

#### Step C — Refactor agent (sonnet)

Dispatch a fresh sonnet agent with the exact refactor scope. Permit no feature work, behavior changes, or unrelated edits. Require the full suite and Step A tests to pass without changing those tests.

#### Step D — Review refactor (opus)

Dispatch code review on opus. Check the refactor and confirm Step A tests remain intact.

#### Step E — Resume original work

Dispatch a fresh implementer for the original task with updated context.

### 4. Never bundle

Do not assign tests, refactor, and feature implementation to one agent session.

### 5. Surface to the user

Report every request's decision and reason in the next update. Keep the identical decision in `refactor-decisions.md` so later reporting can use it.
