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
alone, `corpus_ab.py:158` still sits above the `try:`, and a
…[truncated]

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
