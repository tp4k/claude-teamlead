# Triage regression cases

Each directory under `cases/` is one recorded triage round. It holds the input triage saw and what the round should have produced. The expectations come from what happened afterwards, not from the triage file itself:

- A demotion that **Codex or a later round raised again** is an overturn. The finding becomes an `in_rows` check, and usually the verdict flips to `NEEDS_REWORK`.
- A demotion that went to the deferred-work ledger and **was never raised again** is upheld. It becomes a `not_in_rows` check.
- A round with no HIGH problem gets a `not_in_rows` check on `| HIGH |` to keep severity calibrated.

Checks only look inside `## Rows`. A demoted finding still appears in the file under `## Demoted to Notes`, so a whole-file match would score a demotion as a promotion.

## Add a case after an overturn

Overturns are rare, and each one is the most useful case this directory can hold. When a Codex review or a later round raises something triage demoted:

1. Make `cases/<run-slug>-<ws|all>-r<N>/`, named after the round that demoted it.
2. Copy that round's inputs into `input.md`: the `plan.md` excerpt, every `review-*` and `verifier-*` report for the round, and the previous round's triage file if there is one. Copy them now: `prune_runs.py` deletes the run later. Replace other projects' run paths and any secrets with placeholders.
3. Write `case.json`:

   ```json
   {
     "round": 2,
     "workstream": "ws1",
     "source": "<project>/<run-dir-name>",
     "verdict": ["NEEDS_REWORK"],
     "in_rows": ["[Uu][Tt][Ff]-?8|[Dd]ecod"],
     "not_in_rows": ["SIGHUP"],
     "recorded": "miss",
     "note": "What was demoted, who raised it later, and the fixing commit."
   }
   ```

   Patterns are Python regexes. Put case-insensitivity in the character classes, as above, not in an inline `(?i)` flag.
4. Grade the triage file that actually ran: `python3 scripts/triage_cases.py grade evals/triage/cases/<id> <run>/triage-….md`. An overturn case must fail here (`recorded: "miss"`), and every check other than the overturned one must pass. If a check you expected to pass fails, the expectation is wrong. Fix it before a model ever sees the case.

Check first that triage actually saw the finding. A later Codex HIGH that no review or verifier report in the round mentioned is a reviewer miss, and triage was right to approve. `red-freeze-cleanup-followup-ws1-r2` is that situation, and it is kept as an approve case.

## Gate a `triage.md` edit

```sh
python3 scripts/triage_cases.py replay --out /tmp/before --samples 3 --role <old triage.md>
python3 scripts/triage_cases.py replay --out /tmp/after  --samples 3
python3 scripts/triage_cases.py compare /tmp/before/results.json /tmp/after/results.json
```

`baseline-2026-10-16.json` is the frozen `before` for `triage.md` at f435407 (Sonnet, three samples). Every case is `recorded: "pass"`: the runs so far contain no triage overturn, so the set is a regression floor and not yet a target. Every check passes 3/3 except one. `retro-fixes-ws1-r1` promotes the demoted SIGHUP item in 1 of 3 samples, so one sample can't tell an edit's effect from that variation.

`compare` exits 1 if any check's pass rate dropped. Once a `recorded: "miss"` case exists, a role edit should turn it into a pass without dropping anything else. With one sample a run is noise, so use three or more. Keep one frozen `before` result rather than re-running it on every edit; a baseline that moves hides the trend.

Replay is a single prompt with no tools, so it measures the decisions triage makes and not its file handling. Each call runs in a temp directory with `--no-session-persistence`, so it leaves nothing under `~/.claude/projects`.
