# The deferred-work ledger

Triage already does the hard part — deciding that a findings row grows the spec rather than fixes a defect — and refactor decisions already weigh blast radius against risk. Then both die in a chat message. The next run's reviewer raises the same row, triage demotes it again, and the next implementer trips over the same code and files the same refactor request, because nothing in the repo records that either was already settled.

So a run that demoted or deferred anything appends it to `<repo>/docs/deferred-work.md` through a delegated sonnet writer (brief **L**), the same way an ADR is written: the coordinator never writes the repo itself.

## When it runs

At step 11, **only if** there is at least one row to add: a `## Demoted to Notes` line in any `triage-*.md`, or a `defer` line in `$RUN/refactor-decisions.md`. Nothing to add → no writer, no file. An empty ledger created "for next time" is a file the user has to delete.

Rejected refactors, Notes the user must decide on, pre-existing test failures and open questions do **not** go in — they belong in the final report, which the user reads once and acts on. The ledger is only for work that was consciously postponed.

## What goes in

One row per item:

```
| Date | Run | Item | Why deferred | Source |
|---|---|---|---|---|
| 2026-09-03 | ratelimit-a1b2 | reject negative burst sizes | spec admits no negative input; hardening beyond spec | triage-r2 |
| 2026-09-03 | ratelimit-a1b2 | extract the window arithmetic from Limiter | works as-is; touches 3 callers outside scope | refactor request |
```

`Run` is the basename of `$RUN`. Copy the triage lines **verbatim** — triage writes them ledger-ready (`<what would change> — <why> (<location>)`) precisely so nobody rephrases a decision into something subtly different from what was decided.

## Appending safely matters more than the ledger does

The file accumulates across runs and it belongs to the repo, not to this run:

- **`Read` it first.** If it exists, append with `Edit`: `old_string` is the current last row copied verbatim, `new_string` is that row plus the new ones. **Never `Write` over a file that exists** — a whole-file write silently drops every earlier run's rows, and this file has no other copy.
- Only when the read proves it absent do you `Write` it: a `# Deferred work` heading, one line saying `/teamlead` runs append here, the table header, then the rows.
- `mkdir -p <repo>/docs` if needed.
- **Never `git add`, never commit.** Same rule as a created ADR: the file lands in the working tree and the user commits it when they choose. A run that commits on the user's behalf has made a decision that was not delegated to it.

## Brief L — ledger writer (`teamlead:writer`)

```
$RUN = <abs>. Repo: <abs>.
Inputs: $RUN/triage-*.md (the ## Demoted to Notes lines), $RUN/refactor-decisions.md (the `defer` lines, if the file exists), $RUN/repo.txt.
Output: append the rows to <repo>/docs/deferred-work.md following the append-safety rules; return `LEDGER rows=<n> file=<path>`.
```

Spawn it in the same turn you write the final report — it has no dependency on the report, and its `rows=<n>` is the number the report's Deferred line cites. Wait with the report's own turn (`wait_for.py --timeout 120 <repo>/docs/deferred-work.md`); it is a one-file append, so it returns in well under a minute.
