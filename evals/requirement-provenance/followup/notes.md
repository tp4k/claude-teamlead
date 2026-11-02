The tested revision improved two things: keeping authority and unresolved assumptions in Spec, and stopping unresolved user/contract conflicts. The recovery pair additionally showed a useful decision change: the tested revision corrected the erroneous frozen test, while current instructions forced correct production code to match a recommendation. Five targeted scenarios tied; their results do not establish improvement.

No paired primary-outcome regression was observed. The test revision nevertheless produced collateral errors: an overbroad claim that tests cannot distinguish a mandated helper call, one draft `status: done` despite pending verification, an incorrect discriminating-input claim, and a spurious absence claim based on abbreviated source. Some other errors, notably invented LIST_GAP counts and claims of searches without tools, appeared in both versions. These observations justify narrow corrections; they do not establish a reliable worsening rate.

This follow-up changes the following instructions:

- Planner and implementer may require/test a helper interaction when applicable authority explicitly mandates it. The output also needs coverage. This removes the old categorical prohibition, which conflicted with explicit-mechanism requirements.
- Implementers compare required and wrong outputs on the exact test input before making a discrimination claim, then confirm it with a probe. Draft reports with unexecuted verification remain partial. Freeze evidence must cover every actual changed line, including renamed definitions and removed setup.
- Reviewers establish LIST_GAP from the actual list and patches. They retain independently demonstrated behavioral findings without inventing list omissions or counts.
- Planners attribute supplied facts to their source. Validators distinguish incomplete excerpts from evidence that something is absent.
- The generated Codex rubric carries the explicit-mechanism testing exception.

These changes are implemented, but **the original 35/35 score applies to the earlier frozen revision, not this follow-up**. The original fixtures, expectations, scores, report and evidence archive remain unchanged. After this note was drafted, the user authorized one new paired recovery exercise: eight fresh agent calls. It is now complete; the original 70-trial dataset remains unchanged.

The recovery evidence collector is repaired and deterministically tested. It verifies an existing recovery commit in a fresh clone, records canonical tree/CLEAN and full HEAD evidence, attributes the applied commit to the original harness, writes the agents' probe patches, runs the existing mutation gate, and captures the named tests that actually fail under those patches. It preserves the source repository and refuses missing probes, dirty/stale source snapshots, and output inside the source. A surviving probe produces FAIL.

Four new harness tests pass. Review-package, plan-review-package, brief-inheritance/outcomes, skill-validity, Python-floor, skill-creator quick validation, Ruff and whitespace checks also pass. The original unrelated deferred-work edit remains byte-identical.

Supplementary verification of the two original recovery outputs now shows:

| Original recovery output | Suite | Snapshot | Mutation evidence | Freeze |
| --- | --- | --- | --- | --- |
| Current | PASS | CLEAN, recorded HEAD | 2 proposed probes killed, named failing tests captured | 13/13 frozen lines retained |
| Tested revision | PASS | CLEAN, recorded HEAD | 1 proposed probe killed, named failing tests captured | Exactly 5 previously authorized lines changed; 8 retained |

The current probes were transcribed directly from the original implementer's proposed old/new expressions; the revised probe was its exact JSON. This is additional deterministic evidence from the existing outputs, not a new agent trial or a retroactive change to the old final-review verdicts. That supplement alone did not prove that fresh agents would close the workflow. The separately authorized recovery exercise below now provides that narrower evidence.

The authorized paired recovery exercise is complete. Both final reviewers returned APPROVED_WITH_NOTES after checking actual HEAD, clean status, passing tests, and mutation evidence. Current instructions still forced the recommended helper into production; the follow-up preserved correct production code and corrected the erroneous test under its preceding finding. All six removed frozen lines were authorized; the seven remaining lines included the unchanged first-seen assertion. The follow-up's three probes were killed. Recovery-decision score: current FAIL, follow-up PASS. Workflow-closure score: both PASS. No explicit-constraint, scope, or freeze violation was observed.

This was exactly eight fresh calls, all observed as claude-sonnet-5-5 at requested high effort, taking 130.9 seconds. Expected decisions, role snapshots, fixture, and runner were frozen before execution. Reviewers had read-only repository access; the harness applied proposed files and performed verification. One compound read command was denied per version; successful permitted reads supplied the necessary evidence. The follow-up still made one initial inaccurate claim that no probes file was supplied, and the harness commit message omitted the requested finding ID; neither blocked the final review because the actual artifacts and authorization were traceable.

I recommend retaining the follow-up revision. This one recovery pair supports the intended behavior and closes the earlier evidence gap; it does not remeasure the seven original scenarios or prove all collateral issues fixed. A future compatible-but-unsupported helper fixture could isolate authority from behavioral correctness more clearly, but no additional trials are required or authorized by this checkpoint.

See recovery-run/report.md and recovery-run/evidence.tar.gz for the new exercise, and verification.json / verification-evidence.tar.gz for the separate supplementary verification of old outputs. Original scores and archives remain preserved. The unrelated deferred-work edit is unchanged.
