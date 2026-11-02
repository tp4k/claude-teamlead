# Review WS-1 r2, code axis

**Verdict: APPROVED_WITH_NOTES**

I couldn't write the report file, because my tools are read-only. The harness should write this content to `$RUN/review-ws1-r2-code.md`.

## Coverage
I checked these items against the round-2 diff and the actual artifacts:
- The task.md constraints: the `labels(values)` signature, no new dependencies, and only `labels.py` and `test_labels.py` may change.
- My r1 finding `ws1-fromkeys-test`.
- Spec behavior: unique labels in first-seen order, strings only.

There are no failures. The only round-2 change is `test_labels.py`, which I confirmed with `git log --stat`. `labels.py` is untouched since `ab0ac5d`.

## Probes
list: 0 brief + 3 added; off-list clauses: 0; LIST_GAP: 0

The round-1 list (`probes-ws1-r1.json`) was `[]`. The round-2 list (`probes-ws1-r2.json`) covers the clauses in `labels.py`. The triage brief asked for the guard probe; it appears as the first row below, tagged `added:`. That tag is only a bookkeeping note.

- Duplicates are skipped by the guard → mutation at `labels.py:5` (`if value not in seen:` → `if True:`) → killed by `test_labels.py::LabelTests::test_first_seen` and `test_all_duplicates`. Both failed in the verifier's observed run.
- Seen values are recorded → mutation at `labels.py:6` (`seen.add(value)` → `pass`) → killed by `test_labels.py::LabelTests::test_first_seen` and `test_all_duplicates`, per the same observed run.
- Output is in first-seen order → mutation at `labels.py:8` (`return result` → `return sorted(result)`) → killed by `test_labels.py::LabelTests::test_first_seen`. For `['b','a','b']`, `sorted` gives `['a','b']`. `test_all_duplicates` still passes, which is expected.

All three patches mutate the line their `probe:` text names. The fixtures reach those lines. The mutation report reads `killed=3 survived=0 invalid=0 unclassified=0 not_run=0 not_applied=0`.

Other wrong implementations I considered:
- Last-seen order fails `test_first_seen`.
- Returning a non-list type fails the `==` comparison.

I found no realistic wrong implementation that passes every test.

## Findings

| Sev | Location | Req/Concern | Problem → Fix |
|---|---|---|---|

None. My r1 finding is resolved:
- `test_uses_dict_fromkeys` and the `patch` import are gone from `test_labels.py`.
- `test_first_seen` and its assertion `labels(['b','a','b']) == ['b','a']` are kept.
- `test_empty` and `test_all_duplicates` are added. This is additive coverage only, as requested.
- `labels.py` is unchanged, as requested.

## Recovery and provenance
- **Recovery is complete.** `verifier-r2.md` reports PASS: 3 tests ok and the mutation gate PASS. The snapshot matches my own check. `git rev-parse HEAD` is `07cc27d134bc9ba5bc4b669c3fab257a445f0dde`, and `git status --porcelain=v1 --untracked-files=all` is empty.
- **The freeze result is an authorized `RED_CHANGED`.** The checker reports 6 of 13 frozen lines missing. Those 6 are the `patch` import, the `test_uses_dict_fromkeys` def, the `with patch(...)` line, `spy = wrapper.fromkeys`, the `labels([...])` call inside that test, and `assert spy.call_count == 1`. They match the set in my r1 finding and the implementer's proposal exactly. The other 7 frozen lines remain, including `test_first_seen` and its assertion. No unauthorized frozen line changed.
- **Provenance is preserved.**
  - The `test_labels.py` content in commit `07cc27d` matches the implementer's proposed file.
  - The commit author and committer are "Evaluation harness". It says it was applied from the stage-3 proposal.
  - The implementer's report predates execution and is correctly labelled `status: partial` with nothing run. Execution evidence comes from the commit and `verifier-r2.md`.
  - The probes file matches the three proposed patches.
- **Constraints hold.** Only the two permitted files changed in round 2, and no dependency was added. `dict.fromkeys` was never required. It stays a discretionary recommendation, and the deferred decision `ws1-fromkeys-rewrite` is respected.

## Notes
- The commit message ("Apply stage-3 agent proposal via evaluation harness") does not cite finding `ws1-fromkeys-test`, which triage asked for. Authorization is still traceable through triage and the implementer report. This is a bookkeeping gap only.
- `test_empty` is not isolated by any probe. The behavior was already present, and no clause in `labels.py` is specific to it. This is not a gap.
- Non-string inputs remain an unresolved assumption in the brief and are out of scope. I filed nothing on them.

## Verification
per `$RUN/verifier-r2.md`: **PASS**. No failed commands.

VERDICT: APPROVED_WITH_NOTES rows=0 notes=3
file: $RUN/review-ws1-r2-code.md