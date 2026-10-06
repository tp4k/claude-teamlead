# ADR workflow — read always, create on `--adr`

## Contents
- Locating ADRs — config resolution
- Read — selection pool and slicing
- Conflict — when the task contradicts an ADR
- Create — only with `--adr`, gated by the 3-part test
- Where this plugs into the coordination loop

Architecture Decision Records preserve architecture decisions and their reasons. They are append-only constraints.

- **Read:** always select relevant ADRs. The planner quotes their clauses, implementers follow them, and code review checks conformance.
- **Create:** write new ADRs only when requested and the decision meets the three-part test below.

Reading constraints is inexpensive. Creating records changes a shared architecture store and requires the user's request.

## Locating ADRs — config resolution

Resolve the location once before planning. Use the first valid existing location:

1. `<repo>/.teamlead.json` supplies `adrPath` and optional `adrSubdir`.
2. `$TEAMLEAD_HOME/config.json` supplies global defaults. The default home is `~/.teamlead`.
3. `<repo>/docs/adr/` supplies the local fallback if it exists.
4. Otherwise skip all ADR work without an error or configuration prompt.

If a configured directory is absent, continue to the next tier. A stale path must not disable an available local store.

```json
{ "adrPath": "/Users/you/repos/arch-decisions", "adrSubdir": "my-service", "reworkCap": 3 }
```

`reworkCap` is separate from ADRs. It limits reworks per workstream with repository-then-global precedence. Default is 3. A non-positive or non-integer value uses the default.

`adrPath` names the store root, which can be a separate repository. If `adrSubdir` is absent, use the working repository root's basename. Inspect config and directories through fast read-only commands.

## Read — selection pool and slicing

For a configured store, consider both `<adrPath>/<adrSubdir>/*.md` and root `<adrPath>/*.md`. Project records take precedence over conflicting organization-wide records. For a local store, use the flat `<repo>/docs/adr/*.md` directory.

1. List filenames. Conventional `NNNN-kebab-title.md` names provide a title index.
2. Select records relevant to the task's files, modules, or topics. Search bodies for service, table, or feature names when titles are unclear.
3. Read the selected records in full. A small store may be read entirely.
4. Write selected text to `$RUN/adrs.md` under `# SELECTED ADRs`. Give the planner this path. Quote relevant clauses inside each governed workstream.

Implementers follow the clauses. Code review checks them. Security and performance use them as context.

## Conflict — when the task contradicts an ADR

Do not dispatch implementers when selection or planning identifies a conflict. For example, a service-local cache conflicts with an ADR prohibiting one.

Name every conflicting record and quote its specific clause. Explain the task's contradiction. Ask the user to select a real option:

- Revise the task to follow the ADR.
- Proceed because the ADR is obsolete or inappropriate here. If the user requests ADR creation, create a new superseding record.
- Override the decision for this task without changing the record.

An ADR can be obsolete, so the user owns the resolution. Do not silently bypass it or provide only a vague conflict warning.

## Create — only with `--adr`, gated by the 3-part test

Enable creation only for `--adr`, its resolved configuration setting, or an explicit natural-language request. Consider decisions actually recorded in the synthesis Decision Log. Require all three conditions:

1. Reversal would have meaningful cost.
2. A future reader would need context to understand the choice.
3. The choice involved real alternatives and reasons.

Otherwise retain the decision in the plan. An enabled run can produce zero ADRs.

### Materialising a created ADR

Delegate the file to the sonnet writer. Its brief must specify:

1. **Folder:** `<adrPath>/<adrSubdir>` for a configured store, or `<repo>/docs/adr/` for a local store. New task decisions are project-specific and do not belong at the organization-wide root.
2. **Number:** highest existing NNNN plus one. Use the title's kebab-case slug. Existing 0006 implies new `0007-<slug>.md`.
3. **Format:** read one or two target-folder ADRs and match their structure and frontmatter. If the folder is empty, check root records. Use the skeleton below only when the whole store is empty.
4. **Status:** always `status: proposed`. The user can accept the record when committing. Never draft it as accepted.
5. **Date:** read the actual current date.
6. **Content:** use the qualifying entry's context, decision, alternatives, and consequences.
7. **Supersession:** when the user selects proceeding with an outdated ADR and the resolved setting enables creation, add `supersedes: NNNN`. Cite the old record in Context. Never edit it. Tell the user they can mark it superseded manually when committing.

### Git — none

Write the new file and report its path and proposed status. Do not stage, commit, branch, or push in the ADR store. The user decides those actions, especially in an organization-wide repository.

### MADR fallback skeleton (only if the store is empty)

```markdown
---
status: proposed
date: <today>
---

# NNNN. <Title>

## Context
<the forces and constraints that made a decision necessary>

## Decision
<what was decided>

## Alternatives considered
<the options that were rejected, and why>

## Consequences
<what becomes easier / harder as a result>
```

## Where this plugs into the coordination loop

- Before planning, resolve the store. Skip ADR work if no store exists.
- During planning, supply selected records through `$RUN/adrs.md`. The planner quotes relevant clauses and identifies task conflicts.
- Before dispatch, obtain the user's resolution for any conflict.
- During review, code review checks conformance. Specialists use clauses as context.
- During synthesis, create requested ADRs only for qualifying decisions. Report each generated path at completion.
