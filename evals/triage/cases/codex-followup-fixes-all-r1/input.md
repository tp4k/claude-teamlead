===== plan.md (excerpt) =====
# Plan

## Goal

Fix the six verified findings of the Codex review of the snapshot-granularity change: four code
defects (`run_codex_review.py` rows 1, 2 and the code half of 5, `review_package.py` row 3,
`corpus_ab.py` row 4) and two plan defects (rows 5 and 6) that are amended in the **previous
run's** `plan.md` and in the round-6 evidence record. The fix run starts from `04a626e`, not from
the base `77238c8`.

## Reviewer items

The task **is** the review: `task.md` `## Findings to fix`, six rows, already triaged in
`/Users/g.evdokimov/.teamlead/runs/teamlead-snapshot-granularity/2026-09-14-1513-snapshot-granularity/codex-triage-r1.md`
(`CONFIRMED 3 · PLAN-DEFECT 2 · OUT-OF-SCOPE 0 · PRE-EXISTING 1 (1 in rewritten subsystems) ·
WRONG 0 · OPEN 0`). Rows are in the task's own order.

| # | item (trimmed to its claim) | disposition | where it went |
| --- | --- | --- | --- |
| 1 | "`is_valid_loose_object()` ignores `decompressor.unused_data`, so appending garbage to a valid loose object leaves the object "valid" and produces no warning even though `git fsck` fails." | accepted | WS-1 |
| 2 | "The staged snapshot stores one value per pathname, collapsing Git's conflict stages 1–3 and allowing a change to an earlier stage to go unreported." | accepted | WS-1 |
| 3 | "The fence opener accepts a backtick inside a backtick fence's info string, so literal Markdown can swallow genuine plan sections and falsely reject the plan." | accepted | WS-2 — accepted as a defect to fix even though the triage verdict is `PRE-EXISTING-SUBSYSTEM-REWRITTEN`, on the task's own reasoning that the rewrite "now owns it" |
| 4 | "An empty manifest is accepted as a successful zero-drift calibration, making the new evidence command vacuous." | accepted | WS-3, together with the row's own "related and already known" half (`read_manifest` outside the `CorpusRefused` guard) |
| 5 | "[plan.md:185] requires `git cat-file --batch-all-objects`, while [plan.md:826] excludes changes inside borrowed alternate stores." | accepted | split: the code change (local-object-only inventory) is WS-1, the `plan.md:185` amendment is WS-4. Codex offered two remedies; the task takes the first, so the second — bringing alternate-store availability into scope — is **declined by the user's own decision**, recorded in `## Decisions taken` 1 |
| 6 | "[plan.md:298] promises a reproducible A/B replay, but [plan.md:711] preserves only hashes and mutable absolute paths." | accepted | WS-4, reword only. Codex's first remedy (store immutable corpus copies) is declined by the task: "do not copy 133 plans into the evidence directory" |

accepted 6 · corrected 0 · declined 0

(The two "declined" clauses above are declined *alternative remedies inside an accepted row*, not
declined rows. No row is declined, and none was found stale: `grep -n 'unused_data'
scripts/run_codex_review.py` still exits 1 with no matches, `:364` still keys `staged` on the path
alone, `corpus_ab.py:158` still sits above the `try:`, and all four cited lines of the previous
`plan.md` — 185, 298, 711, 826 — were read and match the task's quotes.)

## Workstreams

| id | name | complexity | depends on | files/scopes | attacker-controlled input | hot path | public surface |
| --- | --- | --- | --- | --- | --- | --- | --- |
| WS-1 | Snapshot fidelity: trailing zlib data, index stages, local-only object inventory (rows 1, 2, 5-code) | L | none | `scripts/run_codex_review.py`, `scripts/test_run_codex_review.py`, `skills/codex-review/SKILL.md` (the one sentence at `:90-91`) | yes | no | yes |
| WS-2 | CommonMark info string: no backtick in a backtick fence's opener (row 3) | M | none | `scripts/review_package.py`, `scripts/test_review_package.py` | yes | no | yes |
| WS-3 | An empty corpus is a refusal, not a zero-drift pass (row 4) | S | none | `scripts/corpus_ab.py`, `scripts/test_corpus_ab.py` | yes | no | yes |
| WS-4 | Amend the plan and the evidence record (rows 5-plan, 6) | S | WS-1 | `/Users/g.evdokimov/.teamlead/runs/teamlead-snapshot-granularity/2026-09-14-1513-snapshot-granularity/plan.md`, `/Users/g.evdokimov/.teamlead/runs/claude-teamlead/2026-09-14-publish-review-r6/evidence/corpus-ab.md` | no | no | no |

Rows 1, 2 and 5-code are **one** workstream on purpose: all three land in
`scripts/run_codex_review.py:tree_state` and its suite, so as separate streams they could not run
in the same wave anyway, and three serial implementer rounds over one file buys nothing over one
round with three named deliverables.

## WS-1 — Snapshot fidelity: trailing zlib data, index stages, local-only object inventory

### Spec excerpt

From `$RUN/task.md` `## Findings to fix` (the task is the source of truth; there is no in-repo spec
doc and no ADR store). Row 1, verbatim:

> ### 1 — HIGH, `scripts/run_codex_review.py:238` (verdict: CONFIRMED)
>
> > `is_valid_loose_object()` ignores `decompressor.unused_data`, so appending garbage to a valid
> > loose object leaves the object "valid" and produces no warning even though `git fsck` fails.
>
> Reviewer's falsifier, as they ran it: *"Append `b"garbage"` to a committed blob's loose-object
> file; observed `is_valid_loose_object=True`, `git fsck` exit 3, equal object-ID sets, and
> `tree_warnings=[]`."* Tags `F2`, `INTEGRITY`, `TEST-GAP`.
>
> **Lines read.** `:238-239` is the only terminality check:
>
> ```
>             if not decompressor.eof:
>                 return False
> ```
>
> `grep -n 'unused_data' scripts/run_codex_review.py` exits **1 with no matches** — the attribute is
> consulted nowhere in the file. The loop at `:222-232` feeds back `decompressor.unconsumed_tail`,
> which is the *max_length* backlog and empties when the stream terminates; bytes appended after the
> stream land in `unused_data` instead, so they never reach `digest.update()` and never fail the
> `:242` comparison `digest.hexdigest() == oid`.
>
> This is the residual of **F2**, which this change existed to fix: an object whose *content* is
> intact but whose *file* has been altered must not read as valid. Note the run's own recorded
> constraint on writing such a test — git writes loose objects `0444`, so corrupting one requires
> clearing that mode bit first (the same bit F4 is about).

Row 2, verbatim:

> ### 2 — HIGH, `scripts/run_codex_review.py:364` (verdict: CONFIRMED)
>
> > The staged snapshot stores one value per pathname, collapsing Git's conflict stages 1–3 and
> > allowing a change to an earlier stage to go unreported.
>
> Reviewer's falsifier, as they ran it: *"Create three `git update-index --index-info` entries for
> `a.txt`, then change only stage 1 while stage 3 remains fixed; observed raw `ls-files --stage`
> output changed, `before.staged == after.staged`, and `tree_warnings=[]`."* Tags `F3`,
> `NON-INJECTIVE`, `TEST-GAP`.
>
> **Lines read.** `:362-364`:
>
> ```
>         meta, separator, path = record.partition(b"\t")
>         if separator:
>             staged[os.fsdecode(path)] = meta.decode("ascii")
> ```
>
> The record format is `mode oid stage\tpath`. The dict is keyed on the **path alone** while the
> stage number sits inside `meta`, so three records for one path overwrite each other and only the
> last survives. […]
>
> This is the residual of **F3**. The original fix deliberately kept the index and suppressed only
> the demonstrably redundant stat-cache signal; collapsing the stages discards real state for a
> second time, by a different mechanism. Keep the stat-cache suppression intact when fixing this —
> `case_a_reverted_change_is_reported_too` is the test that went red when it was absent.

Row 5, the code half, verbatim:

> **Decision taken (2026-09-15): take the first of Codex's two remedies — a local-object-only
> inventory, while continuing to digest the `objects/info/alternates` pointer.** That honours both
> plan lines at once: the pointer change is still caught, which is what F2 requires, and a change
> inside the borrowed store no longer produces a warning about something declared outside the threat
> model. Do **not** take the second remedy; bringing alternate-store availability into scope reopens
> a boundary the acceptance criteria closed deliberately.
>
> **Why this matters more than its severity suggests.** The symptom is a **false alarm**, which is
> exactly the defect class (F1) this whole workstream existed to remove.

The standing acceptance-criteria clause this stream must not violate, quoted from
`/Users/g.evdokimov/.teamlead/runs/teamlead-snapshot-granularity/2026-09-14-1513-snapshot-granularity/plan.md:826-829`:

> **Following external hooks or alternate object stores.** A `core.hooksPath` already pointing
> outside the repository, and the borrowed store an alternates file points at, remain out of the
> threat model. Changing the *pointer* must be caught (that is F2); following it is not this
> change's business.

The shipped sentence that states this tool's object-warning contract in prose, and that this stream
therefore amends in the same round (user decision of 2026-09-15, `questions.md` `## Answers` 2),
verbatim from `skills/codex-review/SKILL.md:90-91`:

> An object warning is judged by which object IDs the repository can still serve, not by
> storage layout, so a `git repack` or `git gc` that keeps every object produces none.

After this stream the inventory is local-only, so "which object IDs the repository can still serve"
stops being true for objects reachable only through `objects/info/alternates`. That one sentence is
reworded to state the local-object meaning — the repository's **own** object store (local loose
objects plus local pack indexes), with a change *inside* a borrowed alternate store producing no
object warning while a change to the `objects/info/alternates` **pointer** still does — and the
`git repack` / `git gc` clause it ends with survives unchanged, because a repack that keeps every
object still produces no warning. No other sentence in `SKILL.md` is touched.

### Observable acceptance

1. **Row 1.** Append `b"garbage"` to a committed blob's loose-object file (after `chmod 0o644`,
   because git writes loose objects `0444`): `is_valid_loose_object(path, oid)` returns `False`,
   `git fsck` exits non-zero, and `tree_warnings(before, after, isolated=True)` contains a
   `WARNING: worktree-shared object storage changed` line naming `objects/<oid[:2]>/<oid[2:]>`.
   Test `case_trailing_garbage_after_a_loose_object_stream_is_caught` fails before, passes after.
2. **Row 2.** Write three `git update-index --index-info` stage entries for one path, snapshot,
   then change **only stage 1** while stage 3 stays fixed: `before.staged != after.staged` and
   `tree_warnings` contains `a staged-only change moved independently of the worktree: a.txt`.
   Test `case_a_change_to_an_earlier_index_stage_is_reported` fails before, passes after.
3. **Row 5-code.** With `objects/info/alternates` pointing at a second repository's `objects`
   directory, write a new object **into that borrowed store** between the two snapshots:
   `tree_warnings(before, after, isolated=True) == []`. Test
   `case_a_change_inside_a_borrowed_alternate_store_is_not_reported` fails before, passes after.
4. **Row 5-code, the other direction.** After `git repack -ad` the local inventory is non-empty and
   unchanged — `before.object_ids == after.object_ids and len(after.object_ids) > 0` — so a fix
   that simply returns an empty set is caught. Test
   `case_the_local_inventory_survives_a_repack_without_emptying` fails before (it cannot fail on an
   empty-set mutant that does not exist yet, so it is written against the post-fix function and must
   be shown red on a deliberately emptied inventory), passes after.
5. **The shipped contract sentence matches the shipped code.** After the edit,
   `grep -c "its own object store" skills/codex-review/SKILL.md` prints `1` (the amended sentence
   names the repository's own object store), `grep -c "keeps every object produces none"
   skills/codex-review/SKILL.md` still prints `1` (the `git repack` / `git gc` clause survives), and
   the amended sentence says a change inside a store reached through `objects/info/alternates`
   produces no object warning while a change to the pointer file itself still does.
   `git diff --stat skills/codex-review/SKILL.md` shows one hunk, inside the paragraph at `:80-101`,
   and the file keeps its existing wrap width (that paragraph wraps under 90 columns).
6. Whole suite: `python3 scripts/test_run_codex_review.py` prints `=== 50 passed, 0 failed` (46
   today plus the four new cases).

### Test plan

existing (all 46 cases in `scripts/test_run_codex_review.py` must stay green; these are the
load-bearing ones):

- `case_a_reverted_change_is_reported_too` — the test the task names as the one that went red when
  the stat-cache suppression was absent.
- `case_a_checkout_does_not_duplicate_a_filesystem_warning` — the stat-cache suppression itself.
- `case_a_staged_only_change_is_reported` — the single-stage path must keep working.
- `case_a_repack_that_keeps_every_object_warns_about_nothing` — forces the local inventory to
  enumerate **packed** objects, not just loose ones.
- `case_objects_pruned_from_the_disposable_tree_are_caught` — a local deletion must still warn.
- `case_an_object_added_to_the_shared_store_is_reported` — a local addition must still warn.
- `case_a_rewritten_alternates_file_is_caught` — the *pointer* change stays caught (F2).
- `case_a_truncated_loose_object_is_caught`,
  `case_a_loose_object_swapped_for_a_valid_stream_of_other_content_is_caught`,
  `case_equal_size_loose_object_corruption_is_caught`,
  `case_an_oversized_loose_object_is_refused_by_the_cap` — the other terminality/validity paths the
  row-1 edit sits beside.
- `case_a_non_utf8_tracked_path_does_not_break_the_snapshot`,
  `case_two_non_utf8_status_paths_stay_distinct` — the row-2 edit must keep the decode injective.
- `scripts/test_python_floor.py` — every shipped module must still parse at Python 3.9 and evaluate
  no PEP 604 annotation at runtime.

new:

- `scripts/test_run_codex_review.py::case_trailing_garbage_after_a_loose_object_stream_is_caught` —
  bytes appended after a valid loose object's zlib stream make the object invalid and produce a
  shared-object-storage warning naming the object path.
- `scripts/test_run_codex_review.py::case_a_change_to_an_earlier_index_stage_is_reported` — with
  three conflict stages for one path, changing only stage 1 changes `staged` and warns.
- `scripts/test_run_codex_review.py::case_a_change_inside_a_borrowed_alternate_store_is_not_reported`
  — writing an object into the store `objects/info/alternates` points at produces no warning at all.
- `scripts/test_run_codex_review.py::case_the_local_inventory_survives_a_repack_without_emptying` —
  the local inventory is non-empty after `git repack -ad`, so the quiet repack is quiet because the
  sets match, not because both are empty.
- no test for acceptance 5 — `skills/codex-review/SKILL.md` is prose the runner never parses
  (`grep -rn 'SKILL.md' scripts/` matches only a docstring, `test_run_state.py:250`), so a test
  asserting a sentence is present would measure nothing about behaviour. The two `grep -c` checks in
  `### Verification commands` are that criterion's check, run by the verifier.

### Reuse and scope

reuse: `scripts/run_codex_review.py:is_valid_loose_object` (`:200-242`) — add the trailing-data
terminality check beside the existing `if not decompressor.eof` at `:238-239`, same function, same
fail-closed `return False`; `:tree_state`'s existing `for path in sorted(common.rglob("*"))` loop
(`:392-433`) together with `:loose_object_oid` (`:194-197`), which already parses every local loose
object's OID out of its own path, so the local inventory needs no second directory walk;
`scripts/test_run_codex_review.py:make_repo` / `:git` / `:check` for fixtures, and
`case_a_loose_object_swapped_for_a_valid_stream_of_other_content_is_caught` (`:963-994`) as the
shape for the row-1 case (it already does the `chmod(0o644)`-then-rewrite dance).

do not reuse: `git cat-file --batch-all-objects --batch-check=%(objectname)`
(`run_codex_review.py:365-378`) as the object inventory. Confirmed against the installed git
(2.55.0) via `git cat-file -h`: there is no local-only switch on that command, and it enumerates
the borrowed store row 5 puts out of scope. Build the inventory from the **local** store instead —
loose OIDs under `<common>/objects/??/`, which the `rglob` loop above already yields, plus the OIDs
in each local pack index, for which `git show-index` is the documented reader (`git show-index -h`:
`usage: git show-index [--object-format=<hash-algorithm>] < <pack-idx-file>`, i.e. the `.idx` on
stdin, one local pack at a time). Do not invent a flag for either command.

do not reuse: the pathname alone as the `staged` dict key (`:364`). In git's index a key is
`(path, stage)`, not a path — one path legitimately carries stages 1, 2 and 3 at once. Keep the
dict **keyed on the path** so `tree_warnings:555-564` still names a path in its warning, and make
the *value* carry every stage's record, in stage order, joined so that the join is injective
(`mode oid stage` is fixed-shape ASCII). Do **not** widen that value with stat data: mode + OID and
nothing else is precisely what makes a `git checkout` stat-cache refresh invisible, which is the
suppression `case_a_checkout_does_not_duplicate_a_filesystem_warning` and
`case_a_reverted_change_is_reported_too` pin, and which the task says to keep intact.

do not reuse: `objects/info/alternates` handling as a place to *follow* the pointer. The file stays
byte-digested by the existing rule (b) branch at `:412-427` — that is what catches a changed
pointer — and nothing in this stream reads the borrowed store's contents for comparison.

do not reuse: `skills/codex-review/SKILL.md:100-101`'s dangling "that map" sentence as a second
edit site, or the file as a place to describe the new mechanism at length. It is a known-deferred
item in `## Anti-scope` and stays exactly as it is; this stream rewords **one** sentence, the
contract statement at `:90-91`, and nothing else in that file.

keep because: `task.md` `## Findings to fix` rows 1, 2 and 5 each name `scripts/run_codex_review.py`
by line and call the fix out explicitly; the `SKILL.md:90-91` sentence is in this stream because the
user decided it there (`questions.md` `## Answers` 2 — "the branch already edits this file, it is
one sentence, and it keeps the shipped doc true rather than leaving a contract statement the code no
longer honours").

### Review axes

attacker-controlled input: yes — every byte this code reads is written by a Codex reviewer running
with `workspace-write` in a shared git common directory: loose-object bytes, index records, and the
alternates pointer all originate outside this process.
hot path: no — `tree_state` runs exactly twice per review, once before and once after; the existing
`LOOSE_OBJECT_MAX_BYTES` cap and chunked reads are the memory bound, and no benchmark or perf test
calls this path hot.
public surface: yes — the `WARNING:` lines are the runner's contract with the coordinator that greps
them, and `TreeState`'s fields are read by the suite; changing what `object_ids` means changes what
the tool promises to detect, which is why the sentence stating that promise in
`skills/codex-review/SKILL.md:90-91` is reworded in this same stream rather than left behind.

### Verification commands

cwd: `/Users/g.evdokimov/.claude/skills/teamlead-snapshot-granularity`

```
python3 scripts/test_run_codex_review.py
python3 scripts/test_python_floor.py
ruff check scripts/run_codex_review.py scripts/test_run_codex_review.py
grep -c "its own object store" skills/codex-review/SKILL.md
grep -c "keeps every object produces none" skills/codex-review/SKILL.md
git diff --stat skills/codex-review/SKILL.md
```

expected: the two suites pass, `ruff check` is silent, both `grep -c` commands print `1`, and the
`git diff --stat` shows `skills/codex-review/SKILL.md` with a single small hunk.

## WS-2 — CommonMark info string: no backtick in a backtick fence's opener

### Spec excerpt

From `$RUN/task.md` `## Findings to fix`, row 3, verbatim:

> ### 3 — MEDIUM, `scripts/review_package.py:121` (verdict: PRE-EXISTING-SUBSYSTEM-REWRITTEN)
>
> > The fence opener accepts a backtick inside a backtick fence's info string, so literal Markdown
> > can swallow genuine plan sections and falsely reject the plan.
>
> Reviewer's falsifier, as they ran it: *"Pass a plan containing an opener such as ` ```bad`info `
> followed by the required sections and a bare closer; observed all four workstream sections
> reported missing. CommonMark explicitly disallows backticks in such info strings."*
> [CommonMark §4.5](https://spec.commonmark.org/0.31.2/#fenced-code-blocks). Tags
> `SUBSYSTEM-REWRITTEN`, `COMMONMARK`, `TEST-GAP`.
>
> **Why this verdict and not CONFIRMED.** The permissiveness predates the change. […] The info
> string is `\S[^\n]*` in **both**: `[^\n]*` admits a backtick either way. But the change replaced
> the expression wholesale and now owns it, and the rewrite already closed an adjacent member of
> the same class — the `(?!` + backtick + `)` lookahead exists precisely to stop a four-backtick
> opener masquerading as a three-backtick one with a stray backtick glued to its info string (see
> the comment at `:117-119` and commit `04a626e`). Finishing the class is therefore consistent with
> what this subsystem was just rebuilt to do, not a new scope.
>
> **Consequence to preserve in a test.** The failure direction matters: this strips *too much*,
> swallowing genuine plan sections and producing a false rejection of a valid plan. `:106-107` at the
> base states the original design rule — *"stripping too little … while too much invents a false
> rejection of a real plan"* — so a fix here must not reintroduce under-stripping.

The head expression this stream edits, verbatim from
`scripts/review_package.py:120-125`, heading `FENCE_RE`:

```
FENCE_RE = re.compile(
    r"^ {0,3}(?:(`{3,})(?!`)|(~{3,})(?!~))[ \t]*\S[^\n]*\n"
    r".*?"
    r"^ {0,3}(?(1)\1`*|\2~*)[ \t]*$",
    re.MULTILINE | re.DOTALL,
)
```

### Observable acceptance

1. A plan document whose body opens with an info string containing a backtick — e.g. a line reading
   ```` ```bad`info ```` — followed by the four workstream sections and a bare ``` closer, gives
   `missing_plan_sections(text) == []` and `plan_is_structured(text) is True`. Test
   `case_a_backtick_in_a_backtick_info_string_is_not_a_fence` fails before (today all four sections
   are reported missing), passes after.
2. The same document written with `~~~` instead of backticks **is** still a fence and is still
   stripped, because CommonMark forbids backticks only in a *backtick* fence's info string: the
   template inside it does not count as a real section. Test
   `case_a_backtick_in_a_tilde_info_string_is_still_a_fence` passes before and after, and goes red
   if the fix strips the backtick class from the tilde branch as well.
3. Whole suite: `python3 scripts/test_review_package.py` prints `=== 27 passed, 0 failed` (25 today
   plus the two new cases).
4. **The drift over real plans is measured once, ad hoc** (user decision of 2026-09-15,
   `questions.md` `## Answers` 1: "re-run ad-hoc, numbers in the round-1 report only"). The A/B in
   `### Verification commands` below runs `04a626e`'s `review_package.py` against the edited one
   over every `plan.md` under `/Users/g.evdokimov/.teamlead`, and its three figures — `corpus size:`,
   `newly rejected:`, `newly accepted:` — are quoted in `implementer-ws2-r1.md`. Expected
   `newly rejected: 0` and `newly accepted: 0`. A non-zero figure is not a stop condition, but the
   report must name it together with the plan paths that flipped verdict, because a narrowing that
   flips a real plan is the "false rejection of a real plan" direction row 3 is about.

### Test plan

existing (all 25 cases in `scripts/test_review_package.py` must stay green; these are the ones that
pin "do not reintroduce under-stripping"):

- `case_a_template_shown_in_a_labelled_fence_does_not_count`
- `case_a_four_backtick_template_fence_is_still_stripped`
- `case_a_fence_closed_by_a_longer_delimiter_is_stripped`
- `case_an_opener_of_four_backticks_is_not_closed_by_three`
- `case_indented_backticks_are_not_a_fence`
- `case_a_fence_indented_three_spaces_is_still_stripped`
- `case_a_spec_quote_containing_code_keeps_its_headings`
- `case_a_bare_fence_left_open_in_a_quote_does_not_pair_across_a_heading`
- `scripts/test_python_floor.py` — every shipped module still parses at the 3.9 floor.

new:

- `scripts/test_review_package.py::case_a_backtick_in_a_backtick_info_string_is_not_a_fence` — an
  opener whose info string contains a backtick opens no fence, so the genuine sections after it
  survive and the plan is not falsely rejected.
- `scripts/test_review_package.py::case_a_backtick_in_a_tilde_info_string_is_still_a_fence` — the
  same info string after `~~~` is legal CommonMark, still opens a fence, and still strips the
  quoted template.

### Reuse and scope

reuse: `scripts/review_package.py:FENCE_RE` (`:120-125`) — one expression, edited in place. The
`(?!` backtick `)` / `(?!~)` lookaheads and the conditional closer `(?(1)\1`*|\2~*)` already there
stay exactly as they are; only the opener's info-string class changes, and the explanatory comment
at `:98-119` is extended with the CommonMark §4.5 reason. `without_fenced_blocks` (`:136-150`),
`missing_plan_sections` (`:176`) and `plan_is_structured` (`:212-223`) are untouched callers.

do not reuse: the single shared info-string class `[ \t]*\S[^\n]*` for both branches — that shared
tail is exactly what admits a backtick after a backtick opener. The two branches now differ:
CommonMark §4.5 forbids backticks in a **backtick** fence's info string and permits them in a
tilde fence's, so the tilde branch keeps `[^\n]*` and only the backtick branch is narrowed. A fix
that narrows both is over-correction and case 2 above is the test that says so.

keep because: `task.md` `## Findings to fix` row 3, with the task's own reasoning that the
wholesale rewrite at `:120-125` "now owns it" and that "finishing the class is therefore consistent
with what this subsystem was just rebuilt to do, not a new scope".

### Review axes

attacker-controlled input: yes — the text is an arbitrary `plan.md` from any run directory, written
by another agent, and this regex has `re.DOTALL` backtracking over it.
hot path: no — called once per review package build, over documents of a few hundred KB.
public surface: yes — `plan_is_structured` is the cross-module contract `corpus_ab.py:119-120`
calls by name on two revisions at once, and the announcement it drives is what the reviewer prompt
promises.

### Verification commands

cwd: `/Users/g.evdokimov/.claude/skills/teamlead-snapshot-granularity`

```
python3 scripts/test_review_package.py
python3 scripts/test_python_floor.py
ruff check scripts/review_package.py scripts/test_review_package.py
```

Plus the one ad-hoc corpus A/B acceptance 4 requires, cwd
`/Users/g.evdokimov/.claude/skills/teamlead-snapshot-granularity/scripts`. The manifest **must be
generated fresh**: the recorded `…/publish-review-r6/evidence/corpus-manifest.txt` hard-refuses on
any entry whose bytes changed (`corpus_ab.py:98`), and WS-4 edits entry 133 — the previous run's
`plan.md` — itself, so the recorded manifest cannot be replayed. Generate to `/tmp`, not into the
evidence directory; no evidence file is created or regenerated by this stream.

```
git show 04a626e:scripts/review_package.py > /tmp/corpus-ab-ws2-base-review_package.py
find /Users/g.evdokimov/.teamlead -name plan.md | sort | while read -r f; do h=$(shasum -a 256 "$f" | awk '{print $1}'); printf '%s  %s\n' "$h" "$f"; done > /tmp/corpus-manifest-ws2.txt
python3 corpus_ab.py --before /tmp/corpus-ab-ws2-base-review_package.py --after review_package.py --manifest /tmp/corpus-manifest-ws2.txt ; echo "EXIT=$?"
```

expected: `corpus size: <n>` with n ≈ 130, `newly rejected: 0`, `newly accepted: 0`, `EXIT=0`. The
generator loop is the one `…/publish-review-r6/evidence/corpus-ab.md` records under "To re-measure
deliberately"; `corpus_ab.py`'s four flags are as `python3 scripts/corpus_ab.py --help` prints them
(`--before`, `--after`, `--manifest`, `--allow-missing`) — do not pass `--allow-missing` here, a
freshly generated manifest has nothing missing and a refusal means the tree moved mid-run.

## WS-3 — An empty corpus is a refusal, not a zero-drift pass

### Spec excerpt

From `$RUN/task.md` `## Findings to fix`, row 4, verbatim:

> ### 4 — MEDIUM, `scripts/corpus_ab.py:158` (verdict: CONFIRMED)
>
> > An empty manifest is accepted as a successful zero-drift calibration, making the new evidence
> > command vacuous.
>
> Reviewer's falsifier, re-executed during triage in `scripts/`:
>
> ```
> : > /tmp/empty-corpus-manifest.txt
> python3 corpus_ab.py --before review_package.py --after review_package.py --manifest /tmp/empty-corpus-manifest.txt
> ```
>
> Real output:
>
> ```
> corpus size: 0
> newly rejected: 0
> newly accepted: 0
> EXIT=0
> ```
>
> Tags `NEW-PUBLIC-CLI`, `VACUOUS-EVIDENCE`.
>
> **Lines read.** `:158` `manifest = read_manifest(args.manifest)` sits **above** the `try:` at
> `:159`, and `resolve_corpus` imposes no floor on corpus size, so zero entries is a success path
> rather than a refusal. `corpus_ab.py` is new in this range (`ab2a568`, +186 lines), so nothing
> about it is pre-existing. This is the command the change offers as its reproducible evidence for
> **F8**; a zero-size corpus reporting zero drift and exiting 0 is the one result that must never
> read as a pass.
>
> Related and already known, worth fixing in the same edit if it is cheap: `read_manifest` sitting
> outside the `CorpusRefused` guard means a manifest read failure raises rather than refusing
> cleanly.

The refusal channel this stream extends, verbatim from `scripts/corpus_ab.py:40-41` and `:156-163`:

```
class CorpusRefused(Exception):
    """The corpus cannot be measured as recorded; the message says why."""
```

```
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = read_manifest(args.manifest)
    try:
        plans, missing = resolve_corpus(manifest, args.allow_missing)
    except CorpusRefused as exc:
        print(str(exc), file=sys.stderr)
        return 1
```

### Observable acceptance

1. The reviewer's falsifier, re-run verbatim from `scripts/`, now refuses:

   ```
   : > /tmp/empty-corpus-manifest.txt
   python3 corpus_ab.py --before review_package.py --after review_package.py --manifest /tmp/empty-corpus-manifest.txt
   ```

   exits **1**, prints a refusal on **stderr** naming the empty corpus, and prints **no**
   `corpus size: 0` / `newly rejected: 0` / `newly accepted: 0` block on stdout. Test
   `case_an_empty_manifest_is_refused_not_a_zero_drift_pass` fails before, passes after.
2. `--manifest /nonexistent/path.txt` exits 1 with the same one-line refusal shape and **no
   traceback**. Test `case_an_unreadable_manifest_refuses_instead_of_raising` fails before (today it
   raises `FileNotFoundError` out of `main`), passes after.
3. `--allow-missing` over a manifest whose entries have all vanished still exits 1: the survivors
   are an empty corpus, and a partial re-run with nothing left in it is the same vacuous pass by
   another route. Test `case_allow_missing_with_no_survivors_is_still_refused` fails before, passes
   after.
4. A **one**-entry corpus still measures and exits 0 — the floor is "more than zero", not "more than
   one"; `case_the_ab_reports_zero_drift_on_an_unchanged_module` is the existing test that pins it.
5. Whole suite: `python3 scripts/test_corpus_ab.py` prints `=== 7 passed, 0 failed` (4 today plus
   the three new cases).

### Test plan

existing (all four cases in `scripts/test_corpus_ab.py` must stay green):

- `case_the_ab_reports_zero_drift_on_an_unchanged_module` — the small-but-non-empty corpus still
  passes, which is what stops the floor being set too high.
- `case_a_newly_rejected_plan_is_counted_and_named`
- `case_a_manifest_entry_whose_file_changed_is_refused` — the existing hard-refusal path and its
  message shape.
- `case_a_vanished_manifest_entry_is_reported_as_missing` — `--allow-missing` must still measure the
  survivors when there *are* survivors.
- `scripts/test_python_floor.py` — the module still parses at the 3.9 floor.

new:

- `scripts/test_corpus_ab.py::case_an_empty_manifest_is_refused_not_a_zero_drift_pass` — a
  zero-entry manifest exits 1 with a stderr refusal and prints no drift figures.
- `scripts/test_corpus_ab.py::case_an_unreadable_manifest_refuses_instead_of_raising` — a manifest
  path that cannot be read exits 1 through `CorpusRefused` rather than propagating `OSError`.
- `scripts/test_corpus_ab.py::case_allow_missing_with_no_survivors_is_still_refused` —
  `--allow-missing` over an all-vanished manifest exits 1 instead of reporting a partial re-run of
  nothing.

### Reuse and scope

reuse: `scripts/corpus_ab.py:CorpusRefused` (`:40-41`) and its single handler in `main`
(`:159-163`), which already turns a refusal into `return 1` plus a stderr line — the floor and the
manifest-read failure both raise that same exception, so no new exit path, no new output channel and
no new message convention is introduced. `resolve_corpus` (`:76-108`) is where the existing refusals
live and is the natural home for the floor; `scripts/test_corpus_ab.py:write_manifest` / `:run_ab` /
`:check` are the fixtures for the new cases.

do not reuse: `main`'s current placement of `read_manifest` at `:158`, above the `try:` — the row's
own "related and already known" half is that this is what makes an unreadable manifest raise instead
of refusing. Move the call inside the guard and raise `CorpusRefused` from the read failure.

do not reuse: the `missing` counter (`:102-107`) as the emptiness check. "Entries vanished" and "the
corpus is empty" are different facts with different messages — a manifest that never had entries has
`missing == 0` — and an `--allow-missing` run can reach an empty corpus with a non-zero `missing`.
Both must refuse, by two distinct messages a reader can act on.

keep because: `task.md` `## Findings to fix` row 4 — "This is the command the change offers as its
reproducible evidence for **F8**; a zero-size corpus reporting zero drift and exiting 0 is the one
result that must never read as a pass."

### Review axes

attacker-controlled input: yes — the manifest is a file path and free-form text supplied on the
command line, and its lines are split into a digest and a path that is then opened.
hot path: no — run by hand, once, as an evidence command.
public surface: yes — the task tags the row `NEW-PUBLIC-CLI`: exit code, stdout lines and stderr
refusal text are the documented contract of the evidence command, quoted in
`…/publish-review-r6/evidence/corpus-ab.md`.

### Verification commands

cwd: `/Users/g.evdokimov/.claude/skills/teamlead-snapshot-granularity`

```
python3 scripts/test_corpus_ab.py
python3 scripts/test_python_floor.py
ruff check scripts/corpus_ab.py scripts/test_corpus_ab.py
```

Plus the reviewer's own falsifier, cwd `/Users/g.evdokimov/.claude/skills/teamlead-snapshot-granularity/scripts`:

```
: > /tmp/empty-corpus-manifest.txt
python3 corpus_ab.py --before review_package.py --after review_package.py --manifest /tmp/empty-corpus-manifest.txt ; echo "EXIT=$?"
```

expected: a refusal line on stderr, no `corpus size:` line, `EXIT=1`.

## WS-4 — Amend the plan and the evidence record

### Spec excerpt

From `$RUN/task.md` `## Findings to fix`, row 5, the plan half, verbatim:

> **Why this matters more than its severity suggests.** The symptom is a **false alarm**, which is
> exactly the defect class (F1) this whole workstream existed to remove. Amend `plan.md:185` to state
> the local-only inventory so the plan and the code agree afterwards.

Row 6, verbatim:

> ### 6 — PLAN DEFECT, `plan.md:298` vs `plan.md:711` (verdict: PLAN-DEFECT — reword, no code)
>
> > [plan.md:298](../plan.md) promises a reproducible A/B replay, but [plan.md:711](../plan.md)
> > preserves only hashes and mutable absolute paths. The exact recorded command now refuses because
> > one manifested plan changed on disk. The plan should have stored immutable corpus copies in the
> > user-selected uncommitted evidence directory, or described the artifact as an auditable
> > point-in-time record rather than reproducible evidence.
>
> **Decision taken (2026-09-15): reword, do not copy the corpus.** Take Codex's second remedy —
> describe the artifact as an **auditable point-in-time record**, not reproducible evidence, which is
> what `plan.md:711` already says correctly. Amend `plan.md:298` and the corresponding wording in
> `…/publish-review-r6/evidence/corpus-ab.md` so the claim matches the artifact. **No code change,
> and do not copy 133 plans into the evidence directory** — the run already decided against
> committing the corpus, and `:711` is the line that is right.

The three lines to amend, read from disk and verbatim.

`/Users/g.evdokimov/.teamlead/runs/teamlead-snapshot-granularity/2026-09-14-1513-snapshot-granularity/plan.md:185-188`
(inside WS-1's `do not reuse:` block; `batch-all-objects` occurs exactly once in that file, at
`:186`):

> Split the two meanings: (a) compare the set of object IDs the repository can
> actually serve (one `git cat-file --batch-all-objects --batch-check` per snapshot) and warn only
> when that set changes; (b) byte-digest every path under `objects/` that is neither a valid
> content-addressed loose object **nor derived storage layout**. Derived layout is never digested,

The sentence to rewrite ends on `:188` at "**nor derived storage layout**." — rewrite it whole,
through the end of clause (b), rather than stopping at `:187`. The clause that begins in the same
line 188 and runs on (`Derived layout is never digested, because a semantics-preserving `git repack
-ad` rewrites all of it while the object-ID set is unchanged: …`, `:188-191`) is still correct after
the narrowing and stays as it is.

`…/2026-09-14-1513-snapshot-granularity/plan.md:298-306`:

> - Reproducible A/B: `python3 corpus_ab.py --before <base review_package.py> --after
>   <worktree review_package.py> --manifest
>   /Users/g.evdokimov/.teamlead/runs/claude-teamlead/2026-09-14-publish-review-r6/evidence/corpus-manifest.txt`
>   prints the corpus size, `newly rejected: 0` and `newly accepted: 0`.
>   `…/2026-09-14-publish-review-r6/evidence/corpus-ab.md` carries the exact command, the manifest
>   path and that result; `…/evidence/corpus-manifest.txt` carries one `<sha256>  <absolute path>`
>   line per plan. Both files live in the round-6 run directory, not in the repository
>   (`## Decisions taken` 10), so the A/B command is written with **absolute** paths on both sides of
>   `--manifest` and the repository gains no `evidence/` directory.

The line that is right and that the amendments must agree with,
`…/2026-09-14-1513-snapshot-granularity/plan.md:711-716`:

> 9. **The corpus is recorded as a point-in-time measurement; it is not copied into the repo.**
>    The plans live under `/Users/g.evdokimov/.teamlead/runs/`, which `scripts/prune_runs.py` deletes
>    by age policy — `maxAgeDays: 30`, `keepLastPerRepo: 5` (`scripts/paths.py:24-29`, read at
>    `prune_runs.py:32-33`) — so most of today's ~107 entries are gone within 30 days and a
>    sha-strict harness would refuse to run, which is F8's own defect ("unreproducible by
>    construction") reproduced by another mechanism.

`/Users/g.evdokimov/.teamlead/runs/claude-teamlead/2026-09-14-publish-review-r6/evidence/corpus-ab.md`,
heading `## Result`:

> Zero drift: every one of the 133 plans reachable at manifest-generation time
> gets the same `plan_is_structured` verdict from the pre-fix and post-fix
> `review_package.py`. This is the re-run the F5 finding required before the
> fence-regex change could be considered safe.

### Observable acceptance

1. `grep -n "batch-all-objects" <previous plan.md>` returns **no match**: the line-185 sentence now
   describes a local-object-only inventory (local loose objects plus local pack indexes), and says
   in the same breath that `objects/info/alternates` remains digested by rule (b) so the pointer
   change is still caught. A reader comparing it with
   `run_codex_review.py` after WS-1 lands sees the same mechanism described in both.
2. `grep -n "Reproducible A/B" <previous plan.md>` returns **no match**; the bullet now reads as an
   auditable point-in-time record and names the reason (the corpus lives under a pruned, mutable
   directory), consistent with `:711`.
3. `grep -c "amended 2026-09-15" <previous plan.md>` returns **2** — each amended passage carries a
   dated marker, so the previous run's artifact is not silently rewritten.
4. `grep -n "point-in-time" <corpus-ab.md>` returns at least one match **above** the `## Command`
   heading: the headline claim, not only the `## Durability` section at the bottom, now says what
   the artifact is.
5. The amended plan is still a structured plan — the edit changes wording, not shape. From
   `/Users/g.evdokimov/.claude/skills/teamlead-snapshot-granularity`:

   ```
   PYTHONPATH=/Users/g.evdokimov/.claude/skills/teamlead-snapshot-granularity/scripts python3 -c "
   import importlib.util, pathlib
   s = importlib.util.spec_from_file_location('rp', 'scripts/review_package.py')
   m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
   t = pathlib.Path('/Users/g.evdokimov/.teamlead/runs/teamlead-snapshot-granularity/2026-09-14-1513-snapshot-granularity/plan.md').read_text()
   print('structured:', m.plan_is_structured(t), 'missing:', m.missing_plan_sections(t))
   "
   ```

   prints `structured: True missing: []` — as it does today (run before the edit, confirmed).

### Test plan

existing: none relevant — this stream touches no Python and no repository file. The two suites that
could notice it are `test_review_package.py` (synthetic fixtures only, never the real corpus) and
`test_corpus_ab.py` (synthetic plans in a `TemporaryDirectory`, likewise); both stay green
untouched, and acceptance item 5 above is the check that the amended plan still classifies as
structured.

new: none — the deliverable is prose in two files outside the repository, and a test asserting the
presence of a sentence would measure nothing about behaviour. Acceptance items 1–5 are grep and
classifier checks run by the verifier instead.

### Reuse and scope

reuse: the wording already correct at `…/2026-09-14-1513-snapshot-granularity/plan.md:711-716` and
in `corpus-ab.md`'s `## Durability — the corpus is expected to shrink` section — both already
describe a point-in-time, prunable record. The amendment lifts that language up to the two claim
sites rather than inventing a new formulation.

do not reuse: the WS-2 workstream **title** "Fence regex in both directions + reproducible corpus
A/B" at `plan.md:34`, `:236` and `:866` as a third amendment site. Leave those three byte-identical:
they are the record of what was dispatched and what the checklist ticked, and rewriting a landed
workstream's name rewrites the run's history rather than correcting a claim. The distinction the
amended `:298` states explicitly instead: the **harness** is reproducible (`corpus_ab.py` plus a
recorded manifest and command re-run deterministically, and refuse loudly when they cannot), while
the **corpus** is a point-in-time record that will shrink and drift.

do not reuse: the evidence directory as a place to copy plans into. The task is explicit — "do not
copy 133 plans into the evidence directory" — and `plan.md:716-719` gives the reason (other runs'
plans, full of absolute home paths and other repositories' contents, in a repo being prepared for a
first public tag).

keep because: `task.md` row 5 — "Amend `plan.md:185` to state the local-only inventory so the plan
and the code agree afterwards" — and row 6 — "Amend `plan.md:298` and the corresponding wording in
`…/publish-review-r6/evidence/corpus-ab.md` so the claim matches the artifact."

### Review axes

attacker-controlled input: no — two Markdown files edited by hand; nothing in them is parsed by
code that makes a decision, beyond the plan classifier that acceptance item 5 re-runs.
hot path: no — prose in a run directory, read by humans and by one grep.
public surface: no — both files live under `/Users/g.evdokimov/.teamlead/runs/`, outside the
repository and outside anything the plugin ships. One side effect worth stating rather than
discovering: the amended `plan.md` **is** entry 133 of `…/evidence/corpus-manifest.txt` (verified —
its recorded sha256 `405d83ce…48c1` still matches the file today), so editing it makes that entry
mismatch and the recorded A/B command refuse on it. That is not a regression; it is the very
phenomenon row 6 describes, and the amended text must say so instead of pretending otherwise.

### Verification commands

cwd: `/Users/g.evdokimov/.claude/skills/teamlead-snapshot-granularity`

```
grep -n "batch-all-objects" /Users/g.evdokimov/.teamlead/runs/teamlead-snapshot-granularity/2026-09-14-1513-snapshot-granularity/plan.md
grep -n "Reproducible A/B" /Users/g.evdokimov/.teamlead/runs/teamlead-snapshot-granularity/2026-09-14-1513-snapshot-granularity/plan.md
grep -c "amended 2026-09-15" /Users/g.evdokimov/.teamlead/runs/teamlead-snapshot-granularity/2026-09-14-1513-snapshot-granularity/plan.md
grep -n "point-in-time" /Users/g.evdokimov/.teamlead/runs/claude-teamlead/2026-09-14-publish-review-r6/evidence/corpus-ab.md
PYTHONPATH=/Users/g.evdokimov/.claude/skills/teamlead-snapshot-granularity/scripts python3 -c "import importlib.util, pathlib; s = importlib.util.spec_from_file_location('rp', 'scripts/review_package.py'); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); t = pathlib.Path('/Users/g.evdokimov/.teamlead/runs/teamlead-snapshot-granularity/2026-09-14-1513-snapshot-granularity/plan.md').read_text(); print('structured:', m.plan_is_structured(t), 'missing:', m.missing_plan_sections(t))"
```

expected: the first two grep commands exit 1 with no output; the third prints `2`; the fourth prints
at least one match; the fifth prints `structured: True missing: []`.

## Dependency DAG / waves

```
WS-1 ──► WS-4
WS-2
WS-3
```

- **Wave 1 (parallel):** WS-1, WS-2, WS-3. Their file scopes are disjoint — `run_codex_review.py`,
  `review_package.py`, `corpus_ab.py` and their three suites — and the repository has no dependency
  manifest of any kind (no `pyproject.toml`, no `requirements.txt`, no lockfile; the suites run on
  bare `python3`), so there is no shared manifest to serialise on.
- **Wave 2:** WS-4. It depends on WS-1 only so that the amended `plan.md:185` describes the
  inventory mechanism that actually shipped; it shares no file with any other stream.

## Decisions taken

1. **Row 5 is fixed by narrowing the inventory, not by following the alternates pointer.** The
   user's decision is already in the task: *"take the first of Codex's two remedies — a
   local-object-only inventory, while continuing to digest the `objects/info/alternates` pointer"*
   (`$RUN/task.md`, row 5). Evidence that it is also the only remedy consistent with the standing
   acceptance criteria: `…/2026-09-14-1513-snapshot-granularity/plan.md:826-829`.
2. **The local inventory is built from local loose objects plus local pack indexes.**
   `git cat-file` has no local-only switch — checked with `git cat-file -h` against git 2.55.0, the
   installed version — so the inventory cannot be narrowed by a flag. `git show-index` reads a
   single `.idx` from stdin (`git show-index -h`: `usage: git show-index
   [--object-format=<hash-algorithm>] < <pack-idx-file>`), which is inherently per-pack and
   therefore local, and `run_codex_review.py:392-419` already walks the common directory and parses
   each loose object's OID out of its path via `loose_object_oid` (`:194-197`). Packed objects must
   be enumerated, not skipped: `case_a_repack_that_keeps_every_object_warns_about_nothing`
   (`test_run_codex_review.py:867`) is green only if a repack's objects are still in the set.
3. **Rows 1, 2 and 5-code are one workstream.** All three edit `scripts/run_codex_review.py:tree_state`
   and its suite (`:200-242`, `:353-364`, `:365-378`), so as separate streams they would have to
   serialise on the same two files anyway.
4. **The empty-corpus floor is "more than zero", not "more than one".**
   `test_corpus_ab.py:CASES` includes `case_the_ab_reports_zero_drift_on_an_unchanged_module`, which
   measures a corpus of one; a higher floor would turn that existing green case red.
5. **`read_manifest` moves inside the `CorpusRefused` guard in the same edit.** The task marks it
   "worth fixing in the same edit if it is cheap"; it is one line moved into the existing `try:` at
   `corpus_ab.py:159` plus one `raise CorpusRefused`, with the handler at `:161-163` already in
   place.
6. **The amendments are made in place, each carrying a dated `amended 2026-09-15` marker.** The
   files are a previous run's artifacts; an unmarked in-place edit would rewrite the record of what
   that run decided, and the marker is what keeps the artifact auditable — which is the very
   property row 6 asks the wording to claim.
7. **The WS-2 title in the previous plan (`:34`, `:236`, `:866`) is not amended.** Row 6 names
   `plan.md:298` and `corpus-ab.md`; the titles are the dispatch record and the checklist. The
   amended `:298` carries the distinction instead: the harness is reproducible, the corpus is a
   point-in-time record.
8. **No ADR work.** No `.teamlead.json`, no `~/.teamlead/config.json`, no `<repo>/docs/` — the
   coordinator confirmed no ADR store exists for this repo, so there is no ADR to attach and no
   conflict to check.
9. **No `docs/deferred-work.md` row is owed.** `codex-triage-r1.md:45-46`: *"`VALID-OUT-OF-SCOPE` is
   empty, so no `docs/deferred-work.md` row is owed. The repo has no `docs/` directory."*
10. **`skills/codex-review/SKILL.md:90-91` is amended inside WS-1, not left describing the
    pre-narrowing meaning.** User decision of 2026-09-15 (`questions.md` `## Answers` 2), taken on
    `plan-validation.md`'s MINOR row 1, which recorded the contradiction: the plan asserted both
    "this changes what the tool promises" and "the file that states the promise stays untouched".
    The stated basis is the user's: the branch already edits this file, it is one sentence, and it
    keeps the shipped doc true rather than leaving a contract statement the code no longer honours.
    Scope is exactly that sentence — `SKILL.md:90-91`, today *"An object warning is judged by which
    object IDs the repository can still serve, not by storage layout, so a `git repack` or `git gc`
    that keeps every object produces none."* — reworded to the local-object meaning, with the
    `repack`/`gc` clause kept.
11. **WS-2's fence narrowing is measured by one ad-hoc corpus A/B, reported and not recorded.**
    User decision of 2026-09-15 (`questions.md` `## Answers` 1): "re-run ad-hoc, numbers in the
    round-1 report only". The re-run needs a **freshly generated** manifest — the recorded
    `…/publish-review-r6/evidence/corpus-manifest.txt` is a hard refusal on any entry whose bytes
    changed (`corpus_ab.py:91-99`), and WS-4 edits entry 133, the previous run's `plan.md`, itself
    (its recorded sha256 `405d83ce…48c1` matches the file today and will not afterwards). The fresh
    manifest is written to `/tmp`, so no evidence artifact is created and WS-4's file scope is
    unchanged.

## Project forbiddens

The repository has **no** `CLAUDE.md` of its own (checked). These are verbatim from the user-global
`/Users/g.evdokimov/.claude/CLAUDE.md` and from `/Users/g.evdokimov/.claude/rules/python.md`, which
applies to every `.py` in this task:

From `CLAUDE.md`:

> - Never invent CLI flags — confirm via `--help` first.

> - Targeted tests while iterating; full suite once before calling a multi-file change done. Fix until green — never report partial progress as complete.
> - Never weaken linters (no ignore/disable for prettier/eslint/ruff/checkstyle).
> - Don't touch env vars, tool installs, or configs I've set up. Ask before changing JAVA_HOME, PATH, or any system-level config.

> - When fixing a calculation, show expected vs actual for ≥2 edge cases before applying the fix.

From `~/.claude/rules/python.md`:

> - **Never use `Any`** — it violates ANN401. Use specific types: `dict[str, str]`,
>   `list[int]`, `Sequence[Path]`, or a concrete class. If a type is genuinely
>   open, model it (`TypeVar`, `Protocol`, a union) rather than erasing it.
> - Never weaken the linter to make types pass: no `# noqa`, no `ruff` ignore
>   sections, no loosening `pyproject.toml`. Fix the annotation instead.

Repo-intrinsic constraints, not from CLAUDE.md but enforced by this repo's CI and its own suites —
break one and the build goes red:

- **ruff 0.0.292, pinned, `ruff check .` over the whole tree** (`.github/workflows/ci.yml`, with the
  comment "Pinned on purpose. ruff's *default* rule set changes between releases"). Default select
  is `E` + `F`, so **E501 at 88 columns is enforced** — commit `5a0e5c2` on this branch exists only
  to re-wrap a line for it.
- **Python floor 3.9**, across a 3.9–3.13 CI matrix, enforced by `scripts/test_python_floor.py`:
  every shipped `.py` must `ast.parse` at `feature_version=(3, 9)`, and any PEP 604 `X | Y` in a
  runtime-evaluated annotation needs `from __future__ import annotations` in that module.
- **No pytest and no third-party dependency.** Every suite is a plain script: `case_*` functions, a
  `CASES` list, a `check(name, ok, detail)` helper, `python3 scripts/test_*.py` exiting non-zero on
  failure. "No pytest dependency — the skill's scripts run with bare python3."
- **No `sys.path` edits.** Cross-module loading goes through
  `importlib.util.spec_from_file_location`, because a `sys.path` edit forces the E402 the house
  linter refuses to have silenced (`corpus_ab.py:47-49`, `test_run_codex_review.py:40-42`).

## Anti-scope

Task-wide, verbatim from `$RUN/task.md` `## Not in scope` (abbreviated to the claims; the section is
the authority):

- **Pushing anything, creating or moving `main`, or touching remotes.** "Unchanged and absolute. […]
  only the squashed orphan root on `main` may ever be pushed, and that is a separate authorised
  step, never part of a fix run."
- **Following external hooks or alternate object stores** — "remains out of the threat model,
  exactly as before. Row 5 is fixed by *narrowing the inventory*, not by following the pointer."
- **The WS-4 evidence-record defect** at `…/publish-review-r6/evidence/round-6-corrected.md:228-230`
  — "Closed `APPROVED_WITH_NOTES` by explicit user decision at the rework cap. […] Do not reopen it
  here."
- **`review_package.py`'s `referenced_inputs` skipping a task-referenced file in a different run
  directory** — "genuinely unfixed — but it was not among Codex's rows and adding it would widen
  this run's scope on the coordinator's authority rather than the user's."
- **Other known-deferred items**, all named in the task: "`wait_for.py`'s stale routing line;
  `object_ids` ignoring `git cat-file`'s exit code; the plan-authorised blind spots
  (`objects/pack/*`, the commit-graph, `DERIVED_STATE_FILES`); the uncapped created-object warning
  loop; a legitimate object >1 GiB reported `deleted`; `SKILL.md:100-101`'s dangling "that map";
  `prune_runs.py` being unable to prune `runs/claude-teamlead/*`; `prune_runs.py:32`'s pyright
  diagnostic".
- **Windows behaviour, an actual 3.9 interpreter, pack-internal corruption, and running a live
  Codex review** as part of the fix.
- No new `docs/` directory and no `docs/deferred-work.md` row — zero rows are owed
  (`codex-triage-r1.md:45-46`).
- **Creating or regenerating any evidence artifact.** WS-2 *does* run the corpus A/B once, ad hoc
  (`## Decisions taken` 11), but into `/tmp`: no file under
  `…/2026-09-14-publish-review-r6/evidence/` is created, regenerated or replaced — not
  `corpus-manifest.txt`, not a new dated record — and WS-4's scope fence is unchanged. The numbers
  live in `implementer-ws2-r1.md` only.
- No file outside each workstream's own scope. In particular `scripts/prune_runs.py`,
  `scripts/wait_for.py`, `scripts/paths.py`, `scripts/run_state.py` and every other file in the
  branch's eight-file diff stay untouched. `skills/codex-review/SKILL.md` is in scope for **WS-1
  alone and only for the one sentence at `:90-91`** (`## Decisions taken` 10); the rest of that file,
  including `:100-101`'s dangling "that map", stays byte-identical.

===== review-r1-code.md =====
# Review — code axis — round 1 (WS-1, WS-2, WS-3, shared worktree at `4caa4ea`)

NEEDS_REWORK

## Coverage

task.md rows 1, 2, 3, 4, 5-code, 5-doc and 6 checked against plan.md's WS-1/WS-2/WS-3 acceptance
lists item by item; TDD pairing of all nine commits; scope (7 files, +389/−35, no file outside the
three briefs, no test line deleted across `04a626e..HEAD`); simplicity gate; item 3a public-surface
checklist for all three streams (planner tag `public surface: yes` ×3). Failures in the table.

## Probes

- WS-1 row 1, trailing bytes after the zlib stream → deleted `if decompressor.unused_data: return False` at `scripts/run_codex_review.py:243-244` → killed by `scripts/test_run_codex_review.py::case_trailing_garbage_after_a_loose_object_stream_is_caught`
- WS-1 row 2, every index stage kept → reverted the accumulation to `staged[key] = entry` at `scripts/run_codex_review.py:407` → killed by `scripts/test_run_codex_review.py::case_a_change_to_an_earlier_index_stage_is_reported`
- WS-1 row 5-code, the pack half of the inventory → `object_ids = frozenset(loose_oids)` at `scripts/run_codex_review.py:476` → killed by `scripts/test_run_codex_review.py::case_the_local_inventory_survives_a_repack_without_emptying` (and by `…::case_a_repack_that_keeps_every_object_warns_about_nothing`)
- WS-1 row 5-code, the local-only restriction → restored the `git cat-file --batch-all-objects` inventory at `scripts/run_codex_review.py:476` → killed by `scripts/test_run_codex_review.py::case_a_change_inside_a_borrowed_alternate_store_is_not_reported`
- WS-2 row 3, backtick branch narrowed → restored the shared `[ \t]*\S[^\n]*` class at `scripts/review_package.py:127` → killed by `scripts/test_review_package.py::case_a_backtick_in_a_backtick_info_string_is_not_a_fence`
- WS-2 row 3, tilde branch NOT narrowed (over-correction guard) → applied `[^\s~][^\n~]*` at `scripts/review_package.py:128` → killed by `scripts/test_review_package.py::case_a_backtick_in_a_tilde_info_string_is_still_a_fence`
- WS-3 row 4, empty-corpus floor → deleted `if not manifest: raise CorpusRefused(...)` at `scripts/corpus_ab.py:103-107` → killed by `scripts/test_corpus_ab.py::case_an_empty_manifest_is_refused_not_a_zero_drift_pass`
- WS-3 row 4, no-survivors floor distinct from empty → deleted `if not present: raise CorpusRefused(...)` at `scripts/corpus_ab.py:127-132` → killed by `scripts/test_corpus_ab.py::case_allow_missing_with_no_survivors_is_still_refused`
- WS-3 row 4, unreadable manifest refuses instead of raising → removed the `try/except OSError` around `path.read_text()` at `scripts/corpus_ab.py:71-74` → killed by `scripts/test_corpus_ab.py::case_an_unreadable_manifest_refuses_instead_of_raising` (kills by aborting the run with the raw `FileNotFoundError`, not by a `FAIL` line — see Notes)

All probes run against a copy of `scripts/` in the session scratchpad, never the repo; the control
run there was `=== 50 passed, 0 failed` / `27` / `7` before each mutation. No survivors.

## Findings

| Sev | Location | Req/Concern | Problem → Fix |
| --- | --- | --- | --- |
| HIGH | `scripts/run_codex_review.py:264` | WS-1 · row 5-code; the detector must not go quiet on an attacker-reachable input | `index_path.open("rb")` carries no `except OSError`, unlike every other read in the same subsystem (`:464-469` records `unreadable` and keeps walking, with a comment saying a file "that this process may not read, is recorded as unreadable rather than skipped"). Measured on this HEAD: `chmod 0000` on the repo's only `.idx` makes `tree_state(repo)` raise `PermissionError [Errno 13]`. At `:970` (`before = tree_state(repo)`) that escapes unguarded; at `:1026-1037` the `except (OSError, ValueError)` catches it but **replaces the whole `changes` list** with one generic `WARNING: could not compare the original worktree after the review: …`, discarding every HEAD / ref / hook / config warning the same comparison would have produced, and `worktree_changed` is then computed from that single line. Counterfactual on `04a626e` with the identical fixture: no raise, and three loud `WARNING: worktree-shared object storage changed: objects/…: deleted during the review` lines. So this diff converts a loud detection into either a traceback or one generic line. → Wrap the `with index_path.open("rb") as handle:` block in `try: … except OSError: continue`, so an unreadable `.idx` merely drops that pack's OIDs from the local inventory (which is what produced the base's loud `deleted` warnings). KEEP the `git show-index` invocation, the `fields[1]` parse, the `sorted(pack_dir.glob("*.idx"))` order and the local-only restriction exactly as they are. ADD to `scripts/test_run_codex_review.py` a case that `chmod(0o000)`s the only `.idx` between the two snapshots and asserts (a) `tree_state` does not raise and (b) a `deleted during the review` warning naming a packed OID is emitted; KEEP all four cases added in `7f70d97`/`788a181`/`54b0bad` unchanged. |
| MEDIUM | `scripts/run_codex_review.py:55-58` | WS-1 · row 5-doc; item 3a "documented where callers look" | The `TreeState` docstring still states `object_ids` is "the set of object IDs the repository can actually serve" — the exact claim the user had WS-1 reword out of `SKILL.md:90-91` precisely because the narrowing makes it false ("it keeps the shipped doc true rather than leaving a contract statement the code no longer honours"). `:631-633` repeats it next to the warning loop ("an object the repository could serve before and cannot serve now, however it was stored"), which is now wrong in the other direction as well: an object dropped from the local store but still reachable through an alternate is reported `deleted`. This file is WS-1's own scope — the brief's "one sentence only" fence applies to `SKILL.md`, not here. → Reword `:55-58` so `object_ids` is the set of IDs the repository serves **from its own object store** (local loose objects plus local pack indexes), not counting a store reached through `objects/info/alternates`, and reword `:631-633` to "an object this repository's own store held before and does not hold now". KEEP the repack sentence's point (a semantics-preserving repack does not shrink the set), the `head`/`entries`/`staged`/`shared`/`config` paragraphs, and `tree_state`'s bullets at `:345-353` as they are. Docstring/comment only — no code change, no test change. |
| LOW | `skills/codex-review/SKILL.md:91`, `:100` | WS-1 · plan WS-1 acceptance 5 ("the file keeps its existing wrap width — that paragraph wraps under 90 columns") | The reflowed paragraph ships a 93-column line (`:91`) and a 92-column one (`:100`); the pre-image's longest line anywhere in `:80-103` was 90. → Re-wrap `:90-103` to ≤ 90 columns. KEEP the phrases `its own object store` and `keeps every object produces none` each unsplit on a single line and re-run both `grep -c` acceptance commands afterwards (a re-wrap that split the first phrase already failed that check once during implementation — see the WS-1 report's compromises section); keep the sentence's meaning and every other line of the file byte-identical. |

## Notes

- `pack_index_oids` ignores `git show-index`'s exit code (`:265-271` reads `listed.stdout` only), so a reader that fails for any other reason yields a silently short inventory. Same class as the deferred `git cat-file` exit-code item the brief's anti-scope names, so not a row — but it is now in newly written code, and the HIGH row's fix is the natural place to consider it.
- TDD granularity: `94e82f3`/`cc27388` is one red/green pair covering three separate concerns (empty manifest, no survivors, unreadable manifest), and `54b0bad` bundles a red case with an already-green discriminator case (the WS-1 report discloses this and proves the discriminator by monkey-patch). The plugin asks for a pair per concern; every red commit is test-file-only and every green production-only, so this is granularity, not a TDD miss.
- `scripts/test_corpus_ab.py::run_ab` calls `ab.main(argv)` with no exception guard, so a regression that raises aborts the entire suite instead of failing one case — that is how probe 9 was killed (a `FileNotFoundError` traceback, no `FAIL` line, no `=== N passed` summary). Consider catching `BaseException` there and recording it as a failure detail.
- Still true after this run, both outside rows 4 and 6 as written: `corpus_ab.sha256_of` can raise `OSError` past `main`'s `except CorpusRefused` (a manifest entry that exists but is unreadable), and `build_parser`'s description still says "over a recorded, reproducible corpus" while row 6 rewords the artifact.
- `cac1371` is the only one of the nine commits without the `Co-Authored-By` trailer the other eight carry.

## Verification

per $RUN/verifier-r1.md: PASS


===== review-r1-perf.md =====
# Review — round 1 — perf — WS-1, WS-2, WS-3

VERDICT: APPROVED — sanity pass; tag: hot path: no (all three streams)

Tag rests on: WS-1 — `tree_state` runs exactly twice per review, cap+chunked reads bound memory,
no perf test calls it hot (`plan.md` WS-1 Review axes). WS-2 — called once per review-package
build over a few-hundred-KB doc (WS-2 Review axes). WS-3 — run by hand once as an evidence
command (WS-3 Review axes).

The diff confirms the planner's no: none of the three diffs adds a loop keyed on request or input
volume — WS-1's new `pack_index_oids` (`a464c13`, `run_codex_review.py:250-277`) reuses the
existing `rglob` walk for loose OIDs (zero new directory passes) and spawns `git show-index` once
per local `.idx` file, still inside `tree_state`'s existing twice-per-review call; WS-2's
`FENCE_RE` edit (`68a4231`) only narrows a character class, no new repetition/backtracking shape;
WS-3's new checks (`cc27388`) are O(1) guards in `resolve_corpus`/`main`.

Notes:
- The one thing worth a genuine look — WS-1's local-object inventory is bounded sensibly on a
  large repo. Subprocess count scales with the **number of local pack files**, not object count
  (typically 1-3 after `git gc --auto`), and the OID text volume parsed in Python per review is
  the same order as before: one line per object either way (`cat-file --batch-check` before, one
  `show-index` line per local object now) — no new asymptotic order, only a per-pack `exec`
  constant, still paid twice per review, not per request. A repo carrying many un-repacked packs
  pays proportionally more `exec` overhead, but that is a pre-existing repo-hygiene condition, not
  a regression this diff introduces.

per $RUN/verifier-r1.md: PASS


===== review-r1-security.md =====
# Review — round 1 — security axis (WS-1, WS-2, WS-3, shared worktree)

NEEDS_REWORK

## Findings

| Sev | Location | Req/Concern | Problem → Fix |
| --- | --- | --- | --- |
| MEDIUM | `scripts/run_codex_review.py:263-270` (WS-1) | row 5-code; attacker-controlled bytes in the shared common dir | `pack_index_oids` `open("rb")`s **every** `glob("*.idx")` hit with no type guard and no `try`. `objects/pack/*` is never digested and never `stat`ed by the walk (`is_derived_object_layout` `continue`s at `:447-448`), so the reviewer can drop anything there under any name. Two inputs I can write: (a) `mkfifo <common>/objects/pack/a.idx` — `open("rb")` on a FIFO with no writer blocks in the kernel forever, there is no `timeout=`, and the call site at `:1027` is inside the `finally`, so the runner hangs unattended and **no** accumulated warning is ever printed (`:1048`); (b) `mkdir <common>/objects/pack/a.idx` (or `chmod 000` an existing one) — `IsADirectoryError`/`PermissionError` escapes `tree_state`, and at `:1029` the whole comparison collapses into the single generic `could not compare the original worktree after the review` line, so every specific `staged`/`shared`/object warning for that same review is lost; the before-snapshot at `:970` is not guarded at all and dies with a traceback. → In `pack_index_oids`, INSERT as the first two lines of the `for` body at `:264`: `if not index_path.is_file():` / `    continue`, and wrap the existing `with index_path.open("rb") as handle:` block in `try:` / `except OSError:` / `    continue`. KEEP the `git -C str(repo) show-index` invocation (`-C repo` is what supplies `extensions.objectFormat`), the `sorted(...)` iteration order, and the `fields[1]` parse. ADD `scripts/test_run_codex_review.py::case_a_non_regular_file_named_idx_does_not_break_the_snapshot`: build the repo, `git repack -ad`, `(common/"objects"/"pack"/"a.idx").mkdir()`, then assert `runner.tree_state(repo).object_ids` still equals the pre-`mkdir` set and is non-empty. Use a directory, not a FIFO, in the test — a FIFO fixture hangs the suite instead of failing it. KEEP `case_the_local_inventory_survives_a_repack_without_emptying` and `case_a_change_inside_a_borrowed_alternate_store_is_not_reported` unchanged. |
| LOW | `scripts/corpus_ab.py:71-74` (WS-3) | row 4's "related and already known" half; acceptance 2 ("exits 1 … and **no traceback**") | `read_manifest` now catches only `OSError`, but `Path.read_text()` on a non-UTF-8 manifest raises `UnicodeDecodeError`, which is a `ValueError`, not an `OSError` — it sails past the new guard, past `main`'s `except CorpusRefused` at `:186`, and out as a traceback. The docstring at `:68-69` ("An absent or unreadable manifest raises `CorpusRefused`") is false for it. Reachable without crafting: the documented generator (`find … -name plan.md \| … shasum`) emits raw path bytes, so one non-UTF-8 byte anywhere in a corpus path produces such a manifest; minimal repro `printf 'abc  /tmp/\xff.md\n' > m.txt`. → At `:73` change `except OSError as exc:` to `except (OSError, UnicodeDecodeError) as exc:`. KEEP the message shape `f"cannot read manifest {path}: {exc}"`, the `from exc` chaining, and the `try:`/`text =` split. ADD to `scripts/test_corpus_ab.py::case_an_unreadable_manifest_refuses_instead_of_raising` a second manifest written with `manifest.write_bytes(b"abc  /tmp/\xff.md\n")` and assert `rc != 0 and "cannot read manifest" in err and "Traceback" not in err`; KEEP the existing absent-path assertions in that case. |

## Notes

- `pack_index_oids` ignores `listed.returncode`, so a pack whose `.idx` `git show-index` rejects contributes zero OIDs silently, where the old `cat-file --batch-all-objects` failed loudly for the whole snapshot. Not filed: I cannot write an `.idx` that `show-index` rejects and the object layer accepts, so the excluded OIDs are genuinely unservable — and the deferred "`object_ids` ignores the exit code" item is anti-scope.
- One subprocess per `.idx` is new fan-out on an attacker-writable directory (was one `cat-file` call regardless of pack count). Bounded in practice by `sorted(common.rglob("*"))` already being O(files), so it is an amplification, not a new class.
- Verified, not filed: the `objects/info/alternates` **pointer** is still byte-digested (`:446-455` never matches `LOOSE_OBJECT_RE` for it), and a symlinked `objects/pack` is caught by `:437-442` before `pack_index_oids` could follow it into the borrowed store.
- WS-2's narrowed opener is linear — `[^\s`][^\n`]*\n` backtracks at most once per line — so `re.DOTALL` gains no new blow-up over a hostile `plan.md`; the `(`{3,})(?!`)` quadratic on a long backtick run is unchanged from `04a626e`.
- `resolve_corpus`'s `sha256_of(file_path)` (`:114`) still lets an `OSError` from the TOCTOU window after `is_file()` escape as a traceback — pre-existing and outside row 4's named half, so Note only.

## Verification

per $RUN/verifier-r1.md: PASS


===== verifier-r1.md =====
# Verifier — round 1 (WS-1, WS-2, WS-3 — shared worktree)

OUTCOME: PASS

HEAD confirmed at `4caa4ea` before running anything (`git log --oneline -20`), which includes, in
order, WS-3's `94e82f3`/`cc27388`, WS-2's `cac1371`/`68a4231`, and WS-1's
`7f70d97`/`861f168`/`788a181`/`cae7703`/`54b0bad`/`a464c13`/`4caa4ea` — every commit each
implementer report listed. `git status --porcelain` is empty (clean tree, nothing uncommitted).

## Commands

### WS-1 (cwd: `/Users/g.evdokimov/.claude/skills/teamlead-snapshot-granularity`)

`python3 scripts/test_run_codex_review.py` → exit 0
```
=== 50 passed, 0 failed
```
(includes `PASS  trailing garbage after a valid loose-object stream is caught`,
`PASS  a change to an earlier conflict stage is reported though a later stage held`,
`PASS  a change inside a borrowed alternate store produces no warning at all`,
`PASS  the local inventory is non-empty and unchanged across a repack`.)

`python3 scripts/test_python_floor.py` → exit 0
```
=== 8 passed, 0 failed
```

`ruff check scripts/run_codex_review.py scripts/test_run_codex_review.py` → exit 0, silent.

`grep -c "its own object store" skills/codex-review/SKILL.md` → `1`, exit 0

`grep -c "keeps every object produces none" skills/codex-review/SKILL.md` → `1`, exit 0

`git diff --stat skills/codex-review/SKILL.md` → exit 0, empty output. (Working tree already
matches HEAD — the file's change is fully committed, so a plain `git diff` against the index shows
nothing at verification time. This is a property of running the command post-commit, not a defect;
the brief's own command was run exactly as written.)

### WS-2 (cwd: `/Users/g.evdokimov/.claude/skills/teamlead-snapshot-granularity`)

`python3 scripts/test_review_package.py` → exit 0
```
=== 27 passed, 0 failed
```
(includes `PASS  a backtick in a backtick fence's info string opens no fence`,
`PASS  a backtick in a tilde fence's info string still opens a fence`.)

`python3 scripts/test_python_floor.py` → exit 0 (same run as above, `=== 8 passed, 0 failed`)

`ruff check scripts/review_package.py scripts/test_review_package.py` → exit 0, silent.

Corpus A/B (cwd: `.../scripts`):
```
git show 04a626e:scripts/review_package.py > /tmp/corpus-ab-ws2-base-review_package.py
find /Users/g.evdokimov/.teamlead -name plan.md | sort | while read -r f; do h=$(shasum -a 256 "$f" | awk '{print $1}'); printf '%s  %s\n' "$h" "$f"; done > /tmp/corpus-manifest-ws2.txt
python3 corpus_ab.py --before /tmp/corpus-ab-ws2-base-review_package.py --after review_package.py --manifest /tmp/corpus-manifest-ws2.txt
```
→ exit 0:
```
corpus size: 139
newly rejected: 0
newly accepted: 0
```
Matches WS-2's own reported figures (139/0/0 — 9 more `plan.md` files exist under
`/Users/g.evdokimov/.teamlead` today than the brief's `n ≈ 130` estimate; `newly rejected`/`newly
accepted` are both 0, which is what row 3 requires).

### WS-3 (cwd: `/Users/g.evdokimov/.claude/skills/teamlead-snapshot-granularity`)

`python3 scripts/test_corpus_ab.py` → exit 0
```
=== 7 passed, 0 failed
```
(includes `PASS  an empty manifest refuses instead of reporting zero drift`,
`PASS  an unreadable manifest refuses cleanly instead of raising`,
`PASS  --allow-missing over an all-vanished manifest still refuses, distinctly from an empty manifest`.)

`python3 scripts/test_python_floor.py` → exit 0 (same run, `=== 8 passed, 0 failed`)

`ruff check scripts/corpus_ab.py scripts/test_corpus_ab.py` → exit 0, silent.

Reviewer's falsifier (cwd: `.../scripts`):
```
: > /tmp/empty-corpus-manifest.txt
python3 corpus_ab.py --before review_package.py --after review_package.py --manifest /tmp/empty-corpus-manifest.txt
```
→ exit 1, stdout empty, stderr:
```
manifest lists no entries to measure; refusing an empty corpus rather than reporting a vacuous zero-drift pass
```
Matches the brief's expectation (refusal line on stderr, no `corpus size:` line, `EXIT=1`).

## Cross-stream check

`scripts/test_python_floor.py` and `ruff check` were each run once per stream's brief but exercise
shared/overlapping surface; all three streams' full suites (50 / 27 / 7 cases) ran clean at the
final shared HEAD `4caa4ea`, with all three streams' commits present together — this is the
condition this round's report exists to confirm, and no stream's suite shows any interference from
another's edit (WS-1's `run_codex_review.py`, WS-2's `review_package.py`, WS-3's `corpus_ab.py`).

## Pre-existing analysis

No failures — nothing to analyze.

## Flaky

none
