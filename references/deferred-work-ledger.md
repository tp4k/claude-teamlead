# The deferred-work ledger

Triage can defer requests that expand scope. The coordinator can also defer refactors after considering their impact. Without a durable record, later runs can repeat those decisions.

When a run defers an item, delegate its append to `<repo>/docs/deferred-work.md` using the sonnet writer and brief L. The coordinator does not edit the repository.

## When it runs

At step 11, append only if triage has a demoted row or `refactor-decisions.md` has a `defer` line. Otherwise dispatch no writer and create no ledger.

Exclude rejected refactors, undecided Notes, pre-existing failures, and open questions. Put these in the final report. The ledger records deliberately postponed work.

## What goes in

One row per item:

```
| Date | Run | Item | Why deferred | Source |
|---|---|---|---|---|
| 2026-09-03 | ratelimit-a1b2 | reject negative burst sizes | spec admits no negative input; hardening beyond spec | triage-r2 |
| 2026-09-03 | ratelimit-a1b2 | extract the window arithmetic from Limiter | works as-is; touches 3 callers outside scope | refactor request |
```

Set Run to the basename of `$RUN`. Copy each ledger-ready triage line verbatim. Do not change the wording of the recorded decision.

## Appending safely matters more than the ledger does

The file accumulates across runs and it belongs to the repo, not to this run:

- **`Read` it first.** If it exists, append with `Edit`: `old_string` is the current last row copied verbatim, `new_string` is that row plus the new ones. **Never `Write` over a file that exists** — a whole-file write silently drops every earlier run's rows, and this file has no other copy.
- Only when the read proves it absent do you `Write` it: a `# Deferred work` heading, one line saying `/teamlead` runs append here, the table header, then the rows.
- `mkdir -p <repo>/docs` if needed.
- **Never stage or commit.** Leave the ledger in the working tree. The user decides whether to commit it, as with a generated ADR.

## Brief L — ledger writer (`teamlead:writer`)

```
$RUN = <abs>. Repo: <abs>.
Inputs: $RUN/triage-*.md (the ## Demoted to Notes lines), $RUN/refactor-decisions.md (the `defer` lines, if the file exists), $RUN/repo.txt.
Output: append the rows to <repo>/docs/deferred-work.md following the append-safety rules; return `LEDGER rows=<n> file=<path>`.
```

Dispatch the ledger writer while preparing the final report. The writer does not depend on the report. Use its returned `rows=<n>` count in the report's Deferred line. Wait for the writer's completion before sending that count. Appends normally finish in under a minute. If using `wait_for.py` on an existing ledger, require a rewrite and the dispatch baseline. File existence alone does not establish completion.
