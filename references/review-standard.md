# Review standard

Every reviewer reads this file itself — once before starting the review and once more right before writing the report (`roles/reviewer.md` says when). Nobody pastes it into a prompt. It is the contract between the reviewer and the two agents that consume the review: triage, which routes on the verdict without reading further, and the coder, which executes the rows without judgement. Everything here exists because one of those two misread a review at some point and it cost a round.

---

REVIEW STANDARD — the shape and the bar of your report.

Shape, in this order, nothing else:
1. **Verdict** — one line: `APPROVED` / `APPROVED_WITH_NOTES` / `NEEDS_REWORK`. The teamlead routes on this word alone.
2. **Coverage** — code-review only, one line: which requirements you checked ("REQ-1..5 checked; failures in table"). Never list the passes.
2a. **Probes** — code-review only, round 1 only (in a rework round, only if the rework changed a probed line). One line per load-bearing criterion, two or three lines in all, in the form `criterion → mutation at <file>:<line> → killed by <file>::<test_name> | SURVIVED`. **Both references must resolve** — the line you edited, and a test that exists in the tree, copied from the runner's output; a line whose citation cannot be followed is read as a probe that did not happen, and is better omitted than written. `roles/reviewer.md` says how to choose the mutation and why a deleted clause asks a sharper question than a swapped operator. **Write the killed lines too** — this is the only section where the passes belong, because a report without it is indistinguishable from a review that never probed, and a survivor is only worth acting on from a reviewer whose misses are also on the page. A `SURVIVED` line always has a matching findings row; a section that is all `killed by` is the normal outcome and takes three lines.
3. **Findings** — a table, one row per fix, highest severity first. Empty table if none.
4. **Notes** — optional, ≤ 5 lines. Observations that are not defects.
5. **Verification** — first line, always: `per $RUN/verifier-r<M>.md: PASS` (or `FAIL`). That one line is how triage and the next reviewer know your green came from the gate and not from a suite run of your own — two eval runs lost this assertion because "skip the passes" was read as "skip the section". Code axis then adds only the commands it ran itself that FAILED, with the error. Never list passing commands.

No praise, no restating the spec, no "what's correct" section, no non-issues. Your reader is a coder agent about to fix things, not a human deciding whether to trust you. Terse beats thorough-looking.

The verdict/row contract — the teamlead does not read your rows before routing, so:
- any row ⇒ `NEEDS_REWORK`. A row you didn't mean as a gate still becomes one.
- `APPROVED_WITH_NOTES` ⇒ **zero** rows. "Should fix but not a ship-blocker" is a Note.

What earns a row: a defect in the behaviour the spec asks for, or a problem that is **exploitable or measurable at the data shape and inputs the spec describes** — "exploitable" means you can write the input that triggers it; "measurable" means it moves a number the spec or the user cares about.

**A working repro is not, by itself, a row.** A repro proves a capability exists; the acceptance criterion your brief gave you is what says whether that capability is *this change's* problem. Two axes once reproduced the same shell line and correctly disagreed — code graded it against the accepted finding's criterion and filed a HIGH, security asked "is this a regression this PR introduces", proved the identical payload executes on the untouched path, and demoted it to a Note. Both were right. So run the counterfactual before you file: **does the pre-change code do this too?** If it does, the row is about pre-existing behaviour and belongs in Notes unless your criterion names it. And make the probe recreate what the call site actually guarantees — a probe of a hook run outside the hook, without the staged-path guarantee the hook always has, "confirmed" the wrong mechanism and would have hardened four harmless routes while missing the live one. List what the inputs are guaranteed to be, satisfy every item, then run it through the real entry point. Hardening or generalising past the spec (rejecting input types the spec doesn't admit, guarding degenerate constructor arguments, micro-optimising a path the spec doesn't call hot) is a Note even when you'd personally add it: growing the spec is the user's decision, and a row makes it the coder's, silently.

Row anatomy: `| Sev | Location | Req/Concern | Problem → Fix |`, Sev ∈ CRITICAL / HIGH / MEDIUM / LOW, Location is `file:line`. The Fix half is an instruction the coder can execute **without judgement** — it names the exact edit and it names what must stay. Two rules that come from rounds that were lost:
- **Show the proof, not the opinion.** "mutant `>=`→`>` at limiter.py:41 survives 6/6" or "input `'a'*10_000` takes 4 s" — the coder's re-check is then mechanical: does that mutant die, does that input finish.
- **Coverage rows are additive.** A row asking for a stronger test says "add …" and names the assertions that stay. A coder reads "record `LIMIT` requests and assert `count == 0`" as *replace*, deletes the partial-fill assertion the test already had, and you meet the same file again next round with a different hole. The rework diff for a coverage row should be almost all `+` lines.

  | | example |
  |---|---|
  | bad | `count` test too weak → record LIMIT requests and assert count == 0 |
  | good | `while`→`if` mutant at `_expire` survives 6/6 → ADD to `test_count_excludes_expired…`: record `LIMIT` requests, `advance(WINDOW_S)`, `assert count("k") == 0`; KEEP the existing `== 1` partial-fill assert and the unknown-key assert |

Re-review after a rework: re-check only the rows you raised and the lines the rework changed. Do not reopen round-1 Notes. For a test-only rework, read the diff's `-` lines first: a removed assertion is a regression until proven subsumed.

Sanity pass (specialists only, when your brief says so): the planner found no {attacker-controlled input | hot path} in this workstream. Read the changed files once and run nothing. The report has its own, shorter shape — **whole file ≤ 15 lines**, no Coverage, no Findings table:
1. Verdict line: `APPROVED — sanity pass; tag: <the planner's tag verbatim>`.
2. One line: the spec line or code path the tag rests on, cited.
3. One line: `the diff confirms the planner's no` — with the one fact that settles it.
4. Notes — optional, ≤ 5 lines.
5. The Verification line from item 5.
If the diff proves the planner wrong — a request or file value reaches this code, or it sits on a loop the spec calls hot — say `contradicts` in the first line instead and write the full shape above. Ten reasoned paragraphs on a pure function carry the same information as these three lines and cost triage a read to skip.
