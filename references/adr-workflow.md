# ADR workflow — read always, create on `--adr`

Architecture Decision Records are durable, append-only records of *why* the architecture is the way it is. For teamlead they play two roles:

- **Read (always on).** ADRs are a first-class spec source. A change that violates a documented decision is building the wrong thing just as surely as one that violates a written spec — so relevant ADRs flow through the pipeline as constraints: the planner extracts them, implementers obey them, `code-review` enforces them.
- **Create (only with `--adr`).** When a coordination round produces a genuinely architectural decision, teamlead can persist it as a new ADR — but only when the user opted in, and only for decisions that clear a deliberately high bar.

The reason these are split: reading is cheap, always-valuable, and risk-free. Creating mutates a shared, often org-wide record, so it stays opt-in and tightly gated.

## Locating ADRs — config resolution

Resolve the ADR location **once, before planning**, in this order. Stop at the first hit:

1. **`<repo>/.teamlead.json`** → `adrPath` (per-repo override always wins). May also set `adrSubdir` to override the project-folder name.
2. **`~/.teamlead/config.json`** → `adrPath` (global default — the org-wide separate ADR repo, set once; `$TEAMLEAD_HOME` moves it, see `scripts/paths.py`).
3. **`<cwd>/docs/adr/`** if that directory exists (co-located fallback — common single-repo layout).
4. **None of the above** → **skip the ADR step entirely.** Read nothing, never offer to create, behave exactly as the pre-ADR skill. Do *not* error or nag about missing config — silence is correct when no ADRs exist.

A configured `adrPath` (cases 1–2) whose directory **does not exist on disk** is treated as *not resolved* — fall through to the next option rather than reading nothing or erroring. A stale path in config must never silently disable ADR reading when a co-located `docs/adr/` is right there.

`.teamlead.json` and `config.json` shape:

```json
{ "adrPath": "/Users/you/repos/arch-decisions", "adrSubdir": "my-service", "reworkCap": 3 }
```

`reworkCap` is unrelated to ADRs and is documented here only because this is where the file's shape is written down: it is the number of rework rounds a workstream gets before triage must `STOP` (default 3, same repo-then-global precedence). Anything that is not a positive integer falls back to the default rather than erroring.

`adrPath` points at the **root** of the ADR store (which may be a separate repo). `adrSubdir` is optional; when absent, derive it from the **basename of the working repo root** (e.g. working in `…/my-service` → subdir `my-service`).

Inspect config with read-only `Bash` (`cat <repo>/.teamlead.json`, `cat ~/.teamlead/config.json`, `ls <cwd>/docs/adr`) — this is exactly the fast read-only inspection hard rule 2 permits.

## Read — selection pool and slicing

Once `adrPath` is resolved (cases 1–3), build the **selection pool**:

- **Configured separate repo (cases 1–2):** pool = `<adrPath>/<adrSubdir>/*.md` (project-specific) **+** `<adrPath>/*.md` at the root (org-wide / system-wide decisions that apply to everything). Both tiers are in play; **project-specific wins** if two ADRs ever conflict on the same topic.
- **Co-located fallback (case 3):** pool = `<cwd>/docs/adr/*.md`, flat — a local `docs/adr` is already project-scoped, so there is no subfolder/root split.

Then **slice, don't dump** — the same discipline teamlead applies to specs (never hand every agent the whole doc):

1. **Index.** List filenames in the pool. ADRs are conventionally `NNNN-kebab-title.md`, so the titles alone are a cheap catalog.
2. **Select relevant.** Pick the ADRs whose subject touches the files / modules / topic this task changes. Titles can be vague, so also `grep` the bodies for the task's key nouns (service names, table names, the feature) to catch poorly-titled ones.
3. **Read only those.** Pull the full text of the selected ADRs — not the whole pool.
4. **Attach inline per workstream.** Hand each selected ADR to the planner as a constraint to fold into the workstream(s) it governs — quoted verbatim, inline with the workstream, exactly like a spec excerpt. Implementers obey it; `code-review` enforces it; `security-review` / `performance-engineer` get it as context.

If the pool is small (a handful of ADRs), reading all of them is fine — the index→select step exists to keep a large org ADR repo from blowing context, not to add ceremony to a tiny one.

## Conflict — when the task contradicts an ADR

The highest-value moment of always-on reading: the requested change would **violate** a documented decision (e.g. the task adds a service-local cache, but `0002-no-service-local-cache` forbids exactly that).

When the planner (or you, during selection) detects this, **do not dispatch implementers.** Halt and surface it to the user:

- Name **each** conflicting ADR (`NNNN-title`) and **quote the specific clause** it violates.
- State plainly how the requested task contradicts it.
- Ask the user how to proceed. Offer the real options:
  - **Revise the task** to comply with the ADR.
  - **Proceed anyway** — the ADR is outdated/wrong for this case. (If `--adr` is on and the user wants the record updated, this means writing a *new* superseding ADR — see below. ADRs are append-only; you never edit the old one.)
  - **Override just this once** without touching the record.

This mirrors the plan confirmation pause: teamlead doesn't silently barrel through a documented decision, and it doesn't hard-block either — the user is the architect and an ADR can be stale. Surfacing *which* ADR and *which clause* is the point; a vague "this might conflict" is useless.

## Create — only with `--adr`, gated by the 3-part test

ADR creation is **off unless the user passed `--adr`** (or asked for an ADR in natural language). Even then, teamlead does **not** write an ADR for every decision. It draws candidates from the synthesis **Decision Log** (the decisions a round actually made) and promotes one only if it passes **all three** tests:

1. **Hard to reverse** — the cost of changing your mind later is meaningful.
2. **Surprising without context** — a future reader will wonder "why did they do it this way?"
3. **The result of a real trade-off** — there were genuine alternatives and one was chosen for specific reasons.

If any of the three is missing, the decision **stays in the plan's Decision Log and does not become an ADR.** A flagged task may legitimately produce **zero** ADRs if nothing architectural happened. This keeps ADRs scarce and meaningful — the whole value of the artifact.

### Materialising a created ADR

Teamlead is a coordinator (hard rule 1) — it delegates the write to a **sonnet writer**, then surfaces the result. The writer's brief:

1. **Target folder** = `<adrPath>/<adrSubdir>` (a created ADR is project-specific by construction — it came from *this* task — so it goes in the project subfolder, never the org-wide root; in co-located mode, `docs/adr/`).
2. **Number** = highest existing `NNNN` in the target folder **+ 1** (e.g. `0006` present → new file `0007-<slug>.md`). Slug = kebab-case of the title.
3. **Format** = **learn from the repo.** Read 1–2 existing ADRs in the target folder (or the org root if the subfolder is empty) and match their structure and frontmatter *exactly* — a created ADR must be indistinguishable from a hand-written one. Only if the whole store is empty, fall back to the MADR-style skeleton below.
4. **`status: proposed`** — always. A machine-drafted ADR the user hasn't ratified is `proposed`; the user flips it to `accepted` when they commit. Never write `accepted`.
5. **`date`** = today's real date (read it; don't guess).
6. **Content** = filled from the qualifying Decision Log entry: the context that forced the decision, the decision itself, the alternatives that were on the table, and the consequences.
7. **Supersession** (only when the user chose "proceed, the old ADR is outdated" *and* `--adr` is on): write a **new** ADR with a `supersedes: NNNN` field and a Context line pointing back to the one it replaces. **Never edit the superseded file** — ADRs are append-only. Tell the user they may want to mark the old one superseded by hand at commit time.

### Git — none

The writer **writes the file and stops.** No `git add`, no commit, no branch, no push — the ADR store is often a separate, org-shared repo, and any outward git action there is the user's call. Surface the path: *"Wrote `0007-centralized-config-service.md` (status: proposed) to `<adrPath>/<adrSubdir>` — commit when ready."*

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

- **Before planning:** resolve `adrPath` (config resolution above). If none → skip everything ADR.
- **Planning:** the coordinator writes the selected ADRs' text to `$RUN/adrs.md` under `# SELECTED ADRs`; the planner treats them as a spec source — extracting relevant excerpts inline per workstream in `plan.md` and flagging any task-vs-ADR conflict. See `references/roles/planner.md`.
- **Conflict → pause** before dispatch (above), like the plan confirmation pause.
- **Review:** `code-review` enforces ADR conformance alongside spec conformance; specialists get ADRs as context. See `references/roles/reviewer.md`.
- **Synthesis (Step 8), only with `--adr`:** scan the Decision Log for entries passing the 3-part test; for each, spawn the writer above. Report created ADR paths in the end-of-task summary.
