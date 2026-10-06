# Review standard

Read this file before reviewing and again immediately before writing the report. Do not paste it into prompts. Triage routes on its verdict. The implementer executes its findings without deciding what you meant.

## Report order

1. **Verdict:** one line containing APPROVED, APPROVED_WITH_NOTES, or NEEDS_REWORK.
2. **Coverage:** code axis only. Give one line identifying checked requirements and referring to failures in the table. Do not enumerate passes.
3. **Probes:** code axis only. Include executed round-1 probes. In rework, include probes only when production lines requiring probes changed.
4. **Findings:** one row per fix, highest severity first. Use an empty table when no findings exist.
5. **Notes:** optional, at most five lines, for observations that are not blocking defects.
6. **Verification:** always begin with `per $RUN/verifier-r<M>.md: PASS` or FAIL. Use the workstream filename when applicable. Code review then lists only its own failed commands and errors. Do not list passing commands.

The Verification line identifies the independent gate as suite evidence. Two evaluation runs omitted it after interpreting "skip passes" as "skip Verification".

Do not add praise, repeated spec text, passing requirements, or non-issues. The report gives the next implementer executable changes.

## Probe records

Start Probes with `list: <n> brief + <n> added; off-list clauses: <n>; LIST_GAP: <n>`.

For each executed probe, use `criterion → mutation at <file>:<line> → killed by <file>::<test_name> | SURVIVED`. Add `[off-list]` after a criterion absent from the shared list.

Cite the actual mutated line. For a kill, copy the existing test name from runner output. Both references must resolve. An unresolvable citation cannot establish an executed probe.

Include killed probes as well as survivors. Without this section, a reader cannot distinguish a clean review from one that never probed. Every SURVIVED record needs a corresponding findings row. Use LIST_GAP for an off-list survivor. All-killed outcomes are normal.

Follow `roles/reviewer.md` for mutation selection and fixture reachability.

## Verdict and findings

Any findings row requires NEEDS_REWORK. APPROVED_WITH_NOTES requires zero findings. Put optional improvements in Notes instead of accidentally making them gates.

A row requires a defect in specified behavior or an exploitable/measurable problem under the specified inputs and data shape. "Exploitable" requires an input that triggers it. "Measurable" requires a change to a quantity relevant to the spec or user.

A working reproduction alone does not establish this change's responsibility. Compare it with the acceptance criterion and the pre-change code. Pre-existing behavior belongs in Notes unless the criterion explicitly requires its correction.

Two reviews once reproduced the same shell payload and correctly reached different conclusions. Code review checked the accepted finding's criterion and filed HIGH. Security established that the untouched route also executed it and recorded a Note.

Reproduce the actual caller guarantees. List guaranteed input properties, satisfy each, and use the real entry point. A hook tested outside its staged-path guarantee can suggest an incorrect mechanism. One such probe would have hardened four harmless routes while missing the actual route.

Treat additional input hardening, degenerate arguments, and non-hot-path micro-optimization as Notes when the spec does not require them. The user decides scope additions.

## Findings rows

Use `| Sev | Location | Req/Concern | Problem → Fix |`. Severity is CRITICAL, HIGH, MEDIUM, or LOW. Location is `file:line`.

The fix must name the exact change and what must remain. The implementer must not need to infer your intended result.

- Give observed proof, such as a surviving `>=` to `>` mutation at `limiter.py:41` or an input taking four seconds.
- Make coverage fixes additive. Name the new assertion and every existing assertion to preserve. The resulting diff should contain almost entirely additions.

| Example | Problem → Fix |
|---|---|
| Incomplete | `count` test too weak → record LIMIT requests and assert count == 0 |
| Executable | `while`→`if` mutant at `_expire` survives 6/6 → ADD LIMIT requests, `advance(WINDOW_S)`, and `assert count("k") == 0` to `test_count_excludes_expired…`. KEEP the existing partial-fill `== 1` assertion and unknown-key assertion. |

In an earlier round, a replacement-shaped request removed partial-fill coverage and caused another gap. State additions explicitly.

## Re-review

Check only your previous findings and changed rework lines. Do not reopen round-1 Notes. For test-only changes, inspect removed assertions first. Treat removal as a regression until you establish stronger coverage.

## Specialist sanity pass

Use this shape only when the brief supplies an axis tag of `no`. Read changed files once and run nothing. Keep the report within 15 lines:

1. `APPROVED — sanity pass; tag: <the planner's tag verbatim>`.
2. Cite the spec line or code path supporting the tag.
3. State `the diff confirms the planner's no` with the decisive fact.
4. Include optional Notes, at most five lines.
5. Include the required verifier-based Verification line.

If the diff disproves the tag, state `contradicts` in the first line and use the full report format. Examples include a reaching request/file value or a loop identified as hot by the spec.
