# The deferred-work ledger

Triage can defer requests that expand scope. The coordinator can also defer refactors after considering their impact. Without a durable record, later runs can repeat those decisions.

During the run the writer collects these items as rows in `$RUN/deferred-rows.md`, outside the repository. At close, `ledger.py apply` puts them into `<repo>/docs/deferred-work.md`. The repo tree stays untouched until then, and the coordinator never edits the repository itself.

## When it runs

At step 11, dispatch the writer only if triage has a demoted row or `refactor-decisions.md` has a `defer` line. Otherwise dispatch no writer, create no rows file, and create no ledger.

Exclude rejected refactors, undecided Notes, pre-existing failures, and open questions. Put these in the final report. The ledger records deliberately postponed work. A demoted row is never dropped: it becomes a row here or a line in the final report.

## What goes in

`$RUN/deferred-rows.md` holds rows only. It has no heading and no table header: `ledger.py` adds them. One row per item, in this shape:

```
| 2026-09-03 | ratelimit-a1b2 | reject negative burst sizes | spec admits no negative input; hardening beyond spec | triage-r2 |
| 2026-09-03 | ratelimit-a1b2 | extract the window arithmetic from Limiter | works as-is; touches 3 callers outside scope | refactor request |
```

The columns are Date, Run, Item, Why deferred and Source. Set Run to the basename of `$RUN`. Copy each ledger-ready triage line verbatim. Do not change the wording of the recorded decision.

The writer reads `$RUN/deferred-rows.md` first and writes it fresh, or appends with `Edit` if it already exists. Never edit `<repo>/docs/deferred-work.md` itself: that is the script's job.

## Applying at close

After the final report's facts are known, the coordinator runs:

```
python3 <plugin>/scripts/ledger.py apply $RUN --ledger <repo>/docs/deferred-work.md
```

It prints `LEDGER rows=<n> file=<path>`. Use that count in the report's Deferred line.

- Each row's id is `<basename $RUN>-<n>`, where n counts from 1 in file order. The row is inserted at a position derived from a hash of that id, among the ledger's existing rows. Existing lines are never rewritten, so parallel branches rarely touch the same line and no migration is needed.
- A missing ledger is created with a `# Deferred work` heading, one line saying `/teamlead` runs append here, and the table header. `docs/` is created if needed.
- **Never stage or commit.** Leave the ledger in the working tree. The user decides whether to commit it, as with a generated ADR.
- **Never `Write` over an existing ledger by hand.** A whole-file write silently drops every earlier run's rows, and the file has no other copy.

## Brief L — ledger writer (`teamlead:writer`)

```
$RUN = <abs>. Repo: <abs>.
Inputs: $RUN/triage-*.md (the ## Demoted to Notes lines), $RUN/refactor-decisions.md (the `defer` lines, if the file exists), $RUN/repo.txt.
Output: write the rows to $RUN/deferred-rows.md (rows only, no header); return `LEDGER rows=<n> file=<path of that file>`. Do not touch the repo.
```

Dispatch the ledger writer while preparing the final report. Its rows file must exist before `ledger.py apply` runs. If using `wait_for.py` on an existing rows file, require a rewrite and the dispatch baseline. File existence alone does not establish completion.
