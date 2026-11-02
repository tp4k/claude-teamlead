# Review WS-1 r2, code axis (re-review)

## Verdict
APPROVED_WITH_NOTES

## Coverage
I checked my one round-1 finding (ws1-r1-row1, HIGH) and the lines the rework changed (`labels.py:1-2`). The finding is resolved and I found no new defects.

## Probes
list: 0 brief + 2 added; off-list clauses: 0; LIST_GAP: 0

- Dedupe via `dict.fromkeys` → mutation at `labels.py:2` (`list(values)`) → killed by `test_labels.py::LabelTests::test_uses_dict_fromkeys`. I read that test. It patches `labels.dict`, and the mutant never calls `fromkeys`, so `call_count == 1` fails at `test_labels.py:11`. `test_labels.py::LabelTests::test_first_seen` also fails, because the mutant returns `['b','a','b']`.
- First-seen order preserved → mutation at `labels.py:2` (`list(dict.fromkeys(sorted(values)))`) → killed by `test_labels.py::LabelTests::test_first_seen`. The mutant gives `['a','b']`, and the test expects `['b','a']`. `test_uses_dict_fromkeys` still passes on this mutant, so it does not cover ordering.

The patch `old` text matches `labels.py:2` exactly, and both rows ran as KILLED in `mutation-ws1-r2.md` (killed=2, survived=0, not_applied=0). Both patches mutate the clause their `probe:` line names.

## Findings
| Sev | Location | Req/Concern | Problem → Fix |
|---|---|---|---|

None. Round-1 row 1 is fixed: `labels.py:2` is now `return list(dict.fromkeys(values))`. `test_uses_dict_fromkeys` and `test_first_seen` both pass in verifier-r2.

## Recovery and provenance
- **Recovery is complete.** The checkout HEAD is `59c85127a71cca831f5cd433dfabb6d947ce7b2c`. This matches the `head:` in `verifier-r2.md`. `git status --porcelain=v1 --untracked-files=all` is empty.
- **Provenance is preserved.**
  - Commit `59c8512` was authored and committed by "Evaluation harness", with the message "Apply stage-3 agent proposal via evaluation harness".
  - Its diff is exactly the proposed `labels.py` (1 insertion, 7 deletions). It matches the stage-3 proposal character for character.
  - The agent's proposal, the harness's commit and the verifier's run are three separate records, so the agent is not credited with execution it did not do.
  - The `probes-ws1-r2.json` contents match the proposal.
  - The verifier's recorded `RED run: none — round 2 has no new RED commit` is consistent with the history. The only RED commit is `5596652`, which is unchanged.
- **No RED_CHANGED.** The verifier's freeze output is `RED_FROZEN — 1 RED commit(s), 13 frozen lines, all present at HEAD`. `git diff ab0ac5d HEAD --stat` shows only `labels.py` changed, so `test_labels.py` is byte-identical to round 1.
- **No constraint violations.**
  - File scope: only `labels.py` changed, which is in the brief's scope fence.
  - `labels(values)` is unchanged.
  - There are no new dependencies and no lint suppressions.
  - No input validation was added, and non-string inputs stay out of scope per the brief.
  - Round 2 touches no public surface beyond restoring the pinned reuse.

## Notes
- Both existing tests use the single input `['b','a','b']`, which is already in reverse-alphabetical order. A wrong implementation such as `sorted(dict.fromkeys(values), reverse=True)` would pass both tests. It calls `dict.fromkeys` once and returns `['b','a']`. This is unlikely, so I did not file it. If the user wants stronger ordering coverage, add a new test with a non-monotonic input such as `['b','c','a','c']` → `['b','c','a']`. This is an additive test and needs a new RED commit. The existing frozen lines must stay.
- I did not run the freeze check, tests or mutations. I rely on the verifier-r2 and `mutation-ws1-r2.md` output, and on my own read-only checks of HEAD, the clean tree and the commit diff.
- I did not write `review-ws1-r2-code.md` because I have no write tool. The harness writes this report.

## Verification
per `$RUN/verifier-r2.md`: PASS. The suite exited 0 (2 tests OK), the freeze check reported `RED_FROZEN`, and the mutation gate reported `MUTATION: PASS killed=2 survived=0 invalid=0 unclassified=0 not_run=0 not_applied=0`. I have no failed commands to list.

VERDICT: APPROVED_WITH_NOTES rows=0 notes=3
file: review-ws1-r2-code.md (proposed path for the harness; I did not write it)