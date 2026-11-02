The agreed new recovery comparison completed in **eight fresh agent calls**. The follow-up revision corrected the erroneous frozen test and completed review with **APPROVED_WITH_NOTES**. The current instructions also reached approval, but only after turning the recommended helper into a production requirement. Passing verification and making the correct requirement decision are separate outcomes.

| Check | Current instructions | Follow-up revision |
| --- | --- | --- |
| Initial review | Calls the suggested helper a requirement despite acknowledging the task does not require it. | Identifies the erroneous test and its supporting import; authorizes a subsequent correction. |
| Triage / rework | Rewrites correct production code to call the helper. | Changes only test_labels.py; leaves correct production code alone. |
| Requirement provenance | Carried, but recommendation promoted into a requirement. | Authority and unresolved assumption carried; mechanism remains discretionary. |
| Actual verification | 2 tests PASS; 2 probes killed; CLEAN at recorded HEAD. | 3 tests PASS; 3 probes killed; CLEAN at recorded HEAD. |
| Freeze | RED_FROZEN, 13 lines intact. | RED_CHANGED, 6 lines authorized by the preceding finding; 7 retained, including behavioral coverage. |
| Final review | APPROVED_WITH_NOTES | APPROVED_WITH_NOTES |
| Intended recovery decision | FAIL | PASS |
| Workflow closure | PASS | PASS |

The decisive current quote is “only the reuse requirement is unmet.” Its review simultaneously acknowledges that task.md does not name the helper. The follow-up instead says “a recommendation is not authority,” identifies the test as the defect, and checks the six changed frozen lines against that finding at final review.

Both final reviewers actually inspected the checkout HEAD and Git status. They had the complete verifier report, actual failing tests under each proposed mutation, the probe file, and explicit attribution of the harness-applied commit. This closes the missing-evidence issue in the earlier exercise. It does not change that earlier exercise's verdicts retroactively.

No explicit task-constraint, file-scope, or freeze violation was observed. Both chains retained the unresolved non-string assumption and the source of the behavior requirement. The follow-up implementer correctly reported partial status before the harness executed its proposal; the final reviewer distinguished that earlier proposal from subsequent verified execution.

Remaining observations: the follow-up's initial report incorrectly said no probes file was supplied even though an empty list existed. The final reviewer read the actual probe files and corrected the bookkeeping. The harness's generic commit message omitted a finding ID requested by triage; the review accepted the traceable finding → proposal → commit → verifier record with a note. A compound read command was denied once per version; permitted reads and successful HEAD/status checks supplied the required evidence. None of these observations was used to revise fixtures or rerun calls.

Settings: Claude Code 2.1.314, requested sonnet alias, observed **claude-sonnet-5-5 for all eight calls**, explicit high effort, fresh sessions, two parallel chains, no retries or fallbacks. Elapsed agent-chain time: **130.9 seconds**. Fixtures, expectations, instruction snapshots, and runner were hashed before execution. Expected answers were excluded from prompts; transcript inspection found reads only of the intended checkout and artifacts. Manual scoring was not blinded to version. This is one paired recovery, with all roles on the same model and harness-applied edits; it is not a complete production-router or production-model-allocation test.

I recommend the follow-up revision on this evidence. The original 28/35 versus 35/35 result still belongs to the earlier frozen revisions, and must not be relabeled as a fresh 70-trial score for this follow-up. The additional corrections to explicit-mechanism tests, status reporting, and evidence claims have deterministic validation, but this recovery pair does not separately prove every one of those corrections behaviorally.

Files here include the frozen protocol, fixture, expectations and manifest, scored outcomes, both final reviews, and an evidence archive containing all transcripts, instruction snapshots, actual repositories, command results, and runner. `evidence.sha256` records archive integrity.
