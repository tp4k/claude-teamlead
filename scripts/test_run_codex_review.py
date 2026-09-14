#!/usr/bin/env python3
"""Regression suite for run_codex_review.py:  python3 scripts/test_run_codex_review.py

Both behaviours here were bought with a guarantee, so the file records the
trade rather than just the code:

  * the reviewer used to run under a hard `read-only` sandbox and had no
    network, so `gh` failed with `error connecting to api.github.com` — which
    left it unable to settle its own `## Blocking` CI claim, the one part of a
    review that is a single command away from decided;
  * `workspace-write` is the only Codex mode that has network, so the runner
    gives it a disposable linked worktree populated from the recovery backup;
    the original tree's before/after comparison remains as an escape detector;
  * the first version of that comparison read `git status --porcelain` lines and
    missed the only case worth catching — a file already `` M`` before the review
    is still `` M`` after it is overwritten, so wiping a run's uncommitted
    `docs/deferred-work.md` produced no warning at all. Found by a live probe, not
    by the unit tests, because every unit test started from a clean file.
  * the digest that replaced it read the porcelain path verbatim, and a rename is
    spelled `old -> new` — a path that does not exist. The failed read digested to
    `-` on both sides, so the same blind spot came back for renamed files until
    the destination was split out.

The comparison is by DIFFERENCE, never by emptiness: a run directory's own
uncommitted deliverables (`docs/deferred-work.md`, a new ADR) are legitimately
in the porcelain output before the review starts.

No pytest dependency — the skill's scripts run with bare python3.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

# Loaded by path rather than imported: a plain `import` here has to follow a
# `sys.path` edit, which is the E402 the house linter refuses to have silenced.
_SPEC = importlib.util.spec_from_file_location(
    "run_codex_review", Path(__file__).resolve().parent / "run_codex_review.py"
)
runner = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(runner)

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


def make_repo(tmp: Path) -> Path:
    repo = tmp / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("one\n")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-qm", "one")
    return repo


def case_network_mode_pairs_workspace_write_with_the_flag(tmp: Path) -> None:
    argv = runner.codex_command("codex", Path("/repo"), Path("/out/r1.md"), True)
    paired = (
        argv[argv.index("--sandbox") + 1] == "workspace-write"
        and "sandbox_workspace_write.network_access=true" in argv
    )
    check(
        "network mode is workspace-write AND the network_access override",
        paired,
        f"argv={argv}",
    )


def case_no_network_is_the_hard_read_only_sandbox(tmp: Path) -> None:
    argv = runner.codex_command("codex", Path("/repo"), Path("/out/r1.md"), False)
    check(
        "--no-network restores read-only with no network override",
        argv[argv.index("--sandbox") + 1] == "read-only"
        and not any(a.startswith("sandbox_workspace_write") for a in argv),
        f"argv={argv}",
    )


def case_unchanged_tree_warns_about_nothing(tmp: Path) -> None:
    repo = make_repo(tmp)
    (repo / "docs").mkdir(exist_ok=True)
    (repo / "docs/deferred-work.md").write_text(
        "a deliverable the run left uncommitted\n"
    )
    before = runner.tree_state(repo)
    after = runner.tree_state(repo)
    check(
        "a dirty-but-unchanged tree is silent — the check is by difference",
        # `!= set()` used to stand here and was always true — `before[1]` is a
        # dict, so it proved nothing about the dirty file being seen. Naming the
        # path is what separates "silent because nothing changed" from "silent
        # because the snapshot was empty".
        runner.tree_warnings(before, after) == []
        and "docs/deferred-work.md" in before[1],
        f"before={before}",
    )


def case_a_file_the_review_created_is_reported(tmp: Path) -> None:
    repo = make_repo(tmp)
    before = runner.tree_state(repo)
    (repo / "codex-probe.txt").write_text("probe\n")
    warnings = runner.tree_warnings(before, runner.tree_state(repo))
    check(
        "a file created during the review produces one WARNING naming it",
        len(warnings) == 1
        and warnings[0].startswith("WARNING:")
        and "codex-probe.txt" in warnings[0],
        f"warnings={warnings}",
    )


def case_an_overwritten_dirty_file_is_reported(tmp: Path) -> None:
    """The live case: tracked, committed, modified but NOT staged.

    Both snapshots see the same `` M docs/deferred-work.md`` line, so only the
    content digest separates them. Staging the file instead would change the
    status code too and let a status-only implementation pass — this case has to
    keep the code identical on both sides to measure anything.
    """
    repo = make_repo(tmp)
    (repo / "docs").mkdir()
    ledger = repo / "docs" / "deferred-work.md"
    ledger.write_text("| 1 | committed row |\n")
    git(repo, "add", "docs/deferred-work.md")
    git(repo, "commit", "-qm", "ledger")
    ledger.write_text("| 1 | committed row |\n| 2 | the row with no other copy |\n")
    before = runner.tree_state(repo)
    ledger.write_text("WIPED\n")
    after = runner.tree_state(repo)
    warnings = runner.tree_warnings(before, after)
    same_code = [v.split()[0] for v in before[1].values()] == [
        v.split()[0] for v in after[1].values()
    ]
    check(
        "a file already dirty before the review is caught when the review rewrites it",
        same_code and len(warnings) == 1 and "docs/deferred-work.md" in warnings[0],
        f"same_code={same_code} warnings={warnings}",
    )


def case_an_untracked_file_rewritten_in_place_is_reported(tmp: Path) -> None:
    repo = make_repo(tmp)
    note = repo / "note.md"
    note.write_text("original\n")
    before = runner.tree_state(repo)
    note.write_text("replaced\n")
    warnings = runner.tree_warnings(before, runner.tree_state(repo))
    check(
        "an untracked file rewritten in place is caught, not just its creation",
        len(warnings) == 1 and "note.md" in warnings[0],
        f"warnings={warnings}",
    )


def case_a_reverted_change_is_reported_too(tmp: Path) -> None:
    repo = make_repo(tmp)
    (repo / "a.txt").write_text("edited\n")
    before = runner.tree_state(repo)
    git(repo, "checkout", "--", "a.txt")
    warnings = runner.tree_warnings(before, runner.tree_state(repo))
    check(
        "a pre-existing change the review erased is reported, not ignored",
        len(warnings) == 1 and "is gone" in warnings[0] and "a.txt" in warnings[0],
        f"warnings={warnings}",
    )


def case_a_commit_during_the_review_is_reported(tmp: Path) -> None:
    repo = make_repo(tmp)
    before = runner.tree_state(repo)
    (repo / "b.txt").write_text("two\n")
    git(repo, "add", "b.txt")
    git(repo, "commit", "-qm", "two")
    warnings = runner.tree_warnings(before, runner.tree_state(repo))
    check(
        "a commit made during the review moves HEAD and is reported",
        any("HEAD moved" in w for w in warnings),
        f"warnings={warnings}",
    )


def case_backup_captures_a_tracked_edit(tmp: Path) -> None:
    repo = make_repo(tmp)
    (repo / "a.txt").write_text("the uncommitted deliverable\n")
    dest, notes = runner.backup_worktree(repo, tmp / "pre")
    patch = (dest / "pre-review.patch").read_text() if dest else ""
    check(
        "an uncommitted tracked edit is saved as a patch before the review runs",
        "the uncommitted deliverable" in patch and notes == [],
        f"dest={dest} patch={patch[:200]!r}",
    )


def case_backup_copies_an_untracked_file(tmp: Path) -> None:
    repo = make_repo(tmp)
    (repo / "docs").mkdir()
    (repo / "docs" / "deferred-work.md").write_text(
        "| 1 | a row with no other copy |\n"
    )
    dest, _ = runner.backup_worktree(repo, tmp / "pre")
    copy = dest / "untracked" / "docs" / "deferred-work.md" if dest else Path("/nope")
    check(
        "an untracked file with no other copy is copied whole, path preserved",
        copy.is_file() and "no other copy" in copy.read_text(),
        f"dest={dest} exists={copy.exists()}",
    )


def case_a_clean_tree_needs_no_backup(tmp: Path) -> None:
    repo = make_repo(tmp)
    dest, notes = runner.backup_worktree(repo, tmp / "pre")
    check(
        "a clean tree writes no backup directory at all",
        dest is None and notes == [] and not (tmp / "pre").exists(),
        f"dest={dest} notes={notes}",
    )


def case_an_oversized_backup_says_so(tmp: Path) -> None:
    repo = make_repo(tmp)
    saved = runner.BACKUP_MAX_FILES
    runner.BACKUP_MAX_FILES = 1
    try:
        for name in ("u1.txt", "u2.txt", "u3.txt"):
            (repo / name).write_text(name)
        _, notes = runner.backup_worktree(repo, tmp / "pre")
    finally:
        runner.BACKUP_MAX_FILES = saved
    check(
        "a backup that hits its cap warns instead of silently truncating",
        len(notes) == 1 and "incomplete" in notes[0],
        f"notes={notes}",
    )


def case_prepared_tree_is_a_detached_checkout_outside_source(tmp: Path) -> None:
    repo = make_repo(tmp)
    dest = tmp / "review-tree"
    tree, notes = runner.prepare_review_tree(repo, dest)
    same_head = tree is not None and git(tree, "rev-parse", "HEAD") == git(
        repo, "rev-parse", "HEAD"
    )
    outside = tree is not None and repo.resolve() not in tree.resolve().parents
    check(
        "the prepared review tree is an equivalent checkout outside the source",
        tree == dest and dest.is_dir() and same_head and outside and notes == [],
        f"tree={tree} same_head={same_head} outside={outside} notes={notes}",
    )
    if tree is not None:
        runner.remove_review_tree(repo, tree)


def case_prepared_tree_contains_the_tracked_edit(tmp: Path) -> None:
    repo = make_repo(tmp)
    (repo / "a.txt").write_text("the uncommitted deliverable\n")
    source_status = git(repo, "status", "--porcelain", "--", "a.txt")[:2]
    tree, notes = runner.prepare_review_tree(repo, tmp / "review-tree")
    review_status = (
        git(tree, "status", "--porcelain", "--", "a.txt")[:2] if tree else ""
    )
    content = (tree / "a.txt").read_text() if tree else ""
    check(
        "the isolated checkout reproduces a tracked uncommitted edit",
        content == "the uncommitted deliverable\n"
        and source_status == review_status
        and notes == [],
        f"content={content!r} statuses={source_status!r}/{review_status!r}",
    )
    if tree is not None:
        runner.remove_review_tree(repo, tree)


def case_prepared_tree_contains_the_untracked_file(tmp: Path) -> None:
    repo = make_repo(tmp)
    note = repo / "docs" / "deferred-work.md"
    note.parent.mkdir()
    note.write_text("a row with no other copy\n")
    source_status = git(repo, "status", "--porcelain", "--", "docs")[:2]
    tree, notes = runner.prepare_review_tree(repo, tmp / "review-tree")
    review_status = (
        git(tree, "status", "--porcelain", "--", "docs")[:2] if tree else ""
    )
    copied = tree / "docs" / "deferred-work.md" if tree else Path("/nope")
    check(
        "the isolated checkout reproduces an untracked file whole",
        copied.is_file()
        and copied.read_text() == "a row with no other copy\n"
        and source_status == review_status
        and notes == [],
        f"copied={copied.exists()} statuses={source_status!r}/{review_status!r}",
    )
    if tree is not None:
        runner.remove_review_tree(repo, tree)


def case_teardown_removes_the_checkout_and_registration(tmp: Path) -> None:
    repo = make_repo(tmp)
    tree, _ = runner.prepare_review_tree(repo, tmp / "review-tree")
    notes = runner.remove_review_tree(repo, tree) if tree else ["no tree"]
    listed = git(repo, "worktree", "list", "--porcelain")
    check(
        "teardown deletes the disposable tree and leaves one worktree registered",
        tree is not None
        and not tree.exists()
        and listed.count("worktree ") == 1
        and notes == [],
        f"tree={tree} exists={tree.exists() if tree else None} list={listed!r}",
    )


def case_teardown_happens_when_review_raises(tmp: Path) -> None:
    repo = make_repo(tmp)
    run = tmp / "run"
    run.mkdir()
    prompt = run / "PROMPT.md"
    prompt.write_text(f"# Review\n\n- Repo / worktree: `{repo}`\n")
    saved_resolve = runner.resolve_codex
    saved_login = runner.require_login
    saved_review = runner.run_review
    received: list[tuple[Path, str]] = []

    def fail_review(
        codex: str,
        review_repo: Path,
        text: str,
        review: Path,
        events: Path,
        timeout: float,
        network: bool,
    ) -> int:
        received.append((review_repo, text))
        raise runner.Fail("simulated review failure")

    runner.resolve_codex = lambda: "codex"
    runner.require_login = lambda codex: None
    runner.run_review = fail_review
    raised = False
    try:
        runner.main([str(prompt)])
    except runner.Fail:
        raised = True
    finally:
        runner.resolve_codex = saved_resolve
        runner.require_login = saved_login
        runner.run_review = saved_review
    listed = git(repo, "worktree", "list", "--porcelain")
    expected_tree = (run / "review-tree").resolve()
    check(
        "a raised review still tears down its checkout and git registration",
        raised
        and not expected_tree.exists()
        and listed.count("worktree ") == 1
        and len(received) == 1
        and received[0][0] == expected_tree
        and f"- Repo / worktree: `{expected_tree}`" in received[0][1],
        f"raised={raised} received={received} list={listed!r}",
    )


def case_failed_preparation_warns_and_does_not_raise(tmp: Path) -> None:
    repo = make_repo(tmp)
    occupied = tmp / "review-tree"
    occupied.mkdir()
    (occupied / "blocker").write_text("not an empty worktree destination\n")
    tree, notes = runner.prepare_review_tree(repo, occupied)
    check(
        "failed preparation returns no tree and an actionable warning",
        tree is None
        and len(notes) == 1
        and notes[0].startswith("WARNING:")
        and str(occupied) in notes[0],
        f"tree={tree} notes={notes}",
    )


def case_failed_isolation_refuses_the_networked_review(tmp: Path) -> None:
    """The fallback this used to take was the outcome isolation exists to stop.

    A networked review runs `workspace-write` with the network on. With no
    disposable checkout to point it at, continuing aimed it at the live
    repository and said so in one lowercase `warning:` line. Refusing is the
    correct answer, and it has to happen before Codex starts, not after.
    """
    repo = make_repo(tmp)
    run = tmp / "run"
    run.mkdir()
    prompt = run / "PROMPT.md"
    prompt.write_text(f"# Review\n\n- Repo / worktree: `{repo}`\n")
    saved = (
        runner.resolve_codex,
        runner.require_login,
        runner.run_review,
        runner.prepare_review_tree,
    )
    started: list[Path] = []

    def record_review(
        codex: str,
        review_repo: Path,
        text: str,
        review: Path,
        events: Path,
        timeout: float,
        network: bool,
    ) -> int:
        started.append(review_repo)
        return 0

    runner.resolve_codex = lambda: "codex"
    runner.require_login = lambda codex: None
    runner.run_review = record_review
    runner.prepare_review_tree = lambda repo, dest: (None, ["WARNING: no tree"])
    raised = ""
    try:
        runner.main([str(prompt)])
    except runner.Fail as exc:
        raised = str(exc)
    finally:
        (
            runner.resolve_codex,
            runner.require_login,
            runner.run_review,
            runner.prepare_review_tree,
        ) = saved
    check(
        "an unisolatable networked review refuses instead of using the live tree",
        started == [] and "--no-network" in raised,
        f"started={started} raised={raised!r}",
    )


def case_a_renamed_file_is_hashed_at_its_destination(tmp: Path) -> None:
    """Porcelain spells a rename `old -> new`, and only `new` is on disk.

    Hashing the arrow string failed the read, so both snapshots digested to `-`
    and an overwrite was invisible whenever the status code also held still —
    `RM` before and after, which is exactly what an already-modified rename
    looks like.
    """
    repo = make_repo(tmp)
    git(repo, "mv", "a.txt", "b.txt")
    (repo / "b.txt").write_text("modified once\n")
    before = runner.tree_state(repo)
    (repo / "b.txt").write_text("overwritten by the review\n")
    after = runner.tree_state(repo)
    check(
        "an overwritten rename destination is caught, not hidden behind the arrow",
        "b.txt" in before[1]
        and not before[1]["b.txt"].endswith("-")
        and runner.tree_warnings(before, after) != [],
        f"before={before[1]} after={after[1]}",
    )


def case_prompt_rewrite_changes_only_the_repo_line(tmp: Path) -> None:
    old = tmp / "source"
    new = tmp / "review-tree"
    prompt = f"# Review\n\n- Repo / worktree: `{old}`\n\nKeep this exact.\n"
    rewritten = runner.prompt_for_review_tree(prompt, new)
    restored = rewritten.replace(
        f"- Repo / worktree: `{new}`", f"- Repo / worktree: `{old}`"
    )
    check(
        "prompt rewriting points at isolation and preserves every other byte",
        f"- Repo / worktree: `{new}`" in rewritten and restored == prompt,
        f"rewritten={rewritten!r}",
    )


def case_a_moved_remote_ref_has_its_own_warning(tmp: Path) -> None:
    """One `fetch` is two shared-state changes, and both are reported as such.

    Moving a remote-tracking ref also appends to that ref's reflog, so this
    produces a ref warning and a reflog warning rather than one of each kind
    being redundant: the ref line says where `origin/main` now points, the reflog
    line says the previous tip is still recoverable. Neither is an escape.
    """
    repo = make_repo(tmp)
    first = git(repo, "rev-parse", "HEAD").strip()
    (repo / "b.txt").write_text("two\n")
    git(repo, "add", "b.txt")
    git(repo, "commit", "-qm", "two")
    second = git(repo, "rev-parse", "HEAD").strip()
    git(repo, "update-ref", "refs/remotes/origin/main", first)
    before = runner.tree_state(repo)
    git(repo, "update-ref", "refs/remotes/origin/main", second)
    warnings = runner.tree_warnings(before, runner.tree_state(repo), isolated=True)
    check(
        "a shared remote-tracking ref move gets a distinct non-escape warning",
        len(warnings) == 2
        and any("worktree-shared ref moved" in warning for warning in warnings)
        and any("worktree-shared reflog changed" in warning for warning in warnings)
        and all("refs/remotes/origin/main" in warning for warning in warnings)
        and not any("isolation escaped" in warning for warning in warnings),
        f"warnings={warnings}",
    )


def case_a_quoted_path_is_still_hashed(tmp: Path) -> None:
    """Porcelain quotes any path with a space, and a quoted path is not on disk.

    This is wider than the rename it was found through: `git status --porcelain`
    wraps *any* path holding a space or a non-ASCII byte in quotes, so the digest
    read failed and both snapshots said `-`. Equal, therefore silent — the exact
    overwrite the comparison exists to catch, invisible for every file whose name
    has a space in it.
    """
    repo = make_repo(tmp)
    (repo / "my notes.txt").write_text("original\n")
    git(repo, "add", "my notes.txt")
    git(repo, "commit", "-qm", "notes")
    (repo / "my notes.txt").write_text("dirty before the review\n")
    before = runner.tree_state(repo)
    (repo / "my notes.txt").write_text("overwritten by the review\n")
    after = runner.tree_state(repo)
    entry = before[1].get("my notes.txt", "")
    check(
        "a path with a space is hashed, so overwriting it is caught",
        entry != "" and not entry.endswith("-")
        and runner.tree_warnings(before, after) != [],
        f"before={before[1]} after={after[1]}",
    )


def case_a_tag_made_inside_the_worktree_is_seen(tmp: Path) -> None:
    """All of `refs/` is shared with a linked worktree, not only `refs/remotes`.

    A probe settled this: a tag and a local branch created inside a disposable
    linked worktree both survive `git worktree remove --force`, exactly as a
    fetched remote ref does. Snapshotting `refs/remotes` alone left every other
    ref namespace unwatched, so a reviewer could move a tag or a branch in the
    real repository and the run would report a clean, isolated review.
    """
    repo = make_repo(tmp)
    first = git(repo, "rev-parse", "HEAD").strip()
    (repo / "b.txt").write_text("two\n")
    git(repo, "add", "b.txt")
    git(repo, "commit", "-qm", "two")
    second = git(repo, "rev-parse", "HEAD").strip()
    git(repo, "tag", "-f", "release", first)
    before = runner.tree_state(repo)
    git(repo, "tag", "-f", "release", second)
    warnings = runner.tree_warnings(before, runner.tree_state(repo), isolated=True)
    check(
        "a tag moved during the review is a shared-ref warning, not silence",
        len(warnings) == 1
        and "worktree-shared ref moved" in warnings[0]
        and "refs/tags/release" in warnings[0],
        f"warnings={warnings}",
    )


def case_config_written_from_a_linked_worktree_is_caught(tmp: Path) -> None:
    """Config is the shared state with no ref to move, so `refs/` never sees it.

    Run through a real linked worktree and tear it down before comparing, which
    is the sequence the runner performs: `git -C <linked> config review.escape
    survives` leaves that key set in the SOURCE repository after
    `git worktree remove --force`, and the widened ref scan reported nothing at
    all. It is also the shared state that decides what runs next — `core.hooksPath`
    and `alias.*` both live here.
    """
    repo = make_repo(tmp)
    linked = tmp / "linked"
    # Snapshot first, exactly as the runner does: it reads `tree_state` before
    # `prepare_review_tree` and again after teardown, so the disposable checkout
    # exists in neither. Snapshotting with the worktree already present would put
    # its own per-worktree HEAD reflog in `before` and nowhere else, and this case
    # would then measure that artefact instead of the config key.
    before = runner.tree_state(repo)
    git(repo, "worktree", "add", "-q", "--detach", str(linked))
    git(linked, "config", "review.escape", "survives")
    git(repo, "worktree", "remove", "--force", str(linked))
    warnings = runner.tree_warnings(before, runner.tree_state(repo), isolated=True)
    survived = git(repo, "config", "--get", "review.escape").strip()
    check(
        "a config key set from the disposable tree survives teardown and warns",
        survived == "survives"
        and len(warnings) == 1
        and "repository config changed" in warnings[0]
        and "review.escape" in warnings[0]
        and "survives" in warnings[0]
        and "isolation escaped" not in warnings[0],
        f"survived={survived!r} warnings={warnings}",
    )


def case_two_config_records_are_not_one_record_with_a_newline(tmp: Path) -> None:
    """The snapshot has to survive a value that contains its own separator.

    Repeated keys accumulate, and accumulating them into a joined string makes
    the snapshot non-injective: with a newline join, the single value
    `first\\nsecond` and the two values `first` and `second` encode identically,
    so replacing one shape with the other compared equal and warned about
    nothing. Git's own `-z` output has the same shape and solves it the same way
    — by keeping the record boundary a boundary — and a config value really can
    contain a newline, which is why no choice of separator would have done.

    `remote.origin.fetch` is the everyday version of this: a reviewer adding a
    second refspec while leaving the first in place is the change that has to
    stay visible.
    """
    repo = make_repo(tmp)
    git(repo, "config", "review.collision", "first\nsecond")
    before = runner.tree_state(repo)
    git(repo, "config", "--unset-all", "review.collision")
    git(repo, "config", "--add", "review.collision", "first")
    git(repo, "config", "--add", "review.collision", "second")
    warnings = runner.tree_warnings(before, runner.tree_state(repo), isolated=True)
    check(
        "one value holding a newline is not the same snapshot as two values",
        len(warnings) == 1
        and "repository config changed" in warnings[0]
        and "review.collision" in warnings[0]
        and "'first\\nsecond'" in warnings[0]
        and "'first', 'second'" in warnings[0],
        f"warnings={warnings}",
    )


def case_reflog_expiry_from_the_disposable_tree_is_caught(tmp: Path) -> None:
    """Ref tips say where a branch is; the reflog is the only way back.

    A linked worktree shares the reflogs too, so `git -C <linked> reflog expire
    --expire=now --all` erases the source repository's recovery history and
    leaves every ref tip exactly where it was — which meant the ref comparison,
    the config comparison and the filesystem comparison all reported nothing
    while the repository lost the record of every reset it could still be undone
    from.
    """
    repo = make_repo(tmp)
    (repo / "second.txt").write_text("second\n")
    git(repo, "add", "second.txt")
    git(repo, "commit", "-qm", "second")
    linked = tmp / "linked"
    before = runner.tree_state(repo)
    git(repo, "worktree", "add", "-q", "--detach", str(linked))
    git(linked, "reflog", "expire", "--expire=now", "--all")
    git(repo, "worktree", "remove", "--force", str(linked))
    warnings = runner.tree_warnings(before, runner.tree_state(repo), isolated=True)
    remaining = git(repo, "reflog", "show", "--all").strip()
    check(
        "erasing the shared reflogs from the disposable tree is reported",
        remaining == ""
        and warnings
        and all("reflog changed" in warning for warning in warnings)
        and any("HEAD" in warning for warning in warnings)
        and not any("isolation escaped" in warning for warning in warnings),
        f"remaining={remaining!r} warnings={warnings}",
    )


def case_a_hook_installed_through_the_linked_worktree_is_caught(tmp: Path) -> None:
    """Hooks are shared, so writing one is arbitrary code execution, later.

    An executable `.git/hooks/post-checkout` created from inside the disposable
    checkout survives `git worktree remove --force` and runs on the next checkout
    in the real repository. The snapshot that enumerated refs, config and reflogs
    reported nothing at all here, which is the strongest single argument for
    reading the directory instead of a list of remembered surfaces.
    """
    repo = make_repo(tmp)
    linked = tmp / "linked"
    before = runner.tree_state(repo)
    git(repo, "worktree", "add", "-q", "--detach", str(linked))
    hook = repo / ".git" / "hooks" / "post-checkout"
    hook.write_text("#!/bin/sh\necho owned\n")
    hook.chmod(0o755)
    git(repo, "worktree", "remove", "--force", str(linked))
    warnings = runner.tree_warnings(before, runner.tree_state(repo), isolated=True)
    check(
        "a hook written from the disposable tree outlives it, and is reported",
        hook.exists()
        and any("hook changed" in warning for warning in warnings)
        and any("post-checkout" in warning for warning in warnings)
        and not any("isolation escaped" in warning for warning in warnings),
        f"warnings={warnings}",
    )


def case_objects_pruned_from_the_disposable_tree_are_caught(tmp: Path) -> None:
    """Deleting history needs no escape, and leaves every ref where it was.

    `git prune` run inside the linked worktree destroys unreachable objects in
    the shared object database. No ref moves, no config changes, no reflog line
    is touched, and the original checkout's files are identical — so every
    comparison the old snapshot made returned equal while the repository
    permanently lost content it could still have been recovered from.
    """
    repo = make_repo(tmp)
    oid = subprocess.run(
        ["git", "-C", str(repo), "hash-object", "-w", "--stdin"],
        input=b"unreachable payload",
        capture_output=True,
    ).stdout.decode().strip()
    linked = tmp / "linked"
    before = runner.tree_state(repo)
    git(repo, "worktree", "add", "-q", "--detach", str(linked))
    git(linked, "prune", "--expire", "now")
    git(repo, "worktree", "remove", "--force", str(linked))
    warnings = runner.tree_warnings(before, runner.tree_state(repo), isolated=True)
    gone = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", oid], capture_output=True
    ).returncode != 0
    # Loose storage splits the OID after two characters, so the warning names
    # `objects/67/9681…` rather than the bare hash the caller knows it by.
    loose_path = f"objects/{oid[:2]}/{oid[2:]}"
    check(
        "an object destroyed from the disposable tree is reported as deleted",
        gone
        and any("object storage changed" in warning for warning in warnings)
        and any(loose_path in warning and "deleted" in warning for warning in warnings)
        and not any("isolation escaped" in warning for warning in warnings),
        f"gone={gone} warnings={warnings}",
    )


def case_a_config_value_utf8_cannot_represent_is_caught(tmp: Path) -> None:
    """Two values git accepts, one string Python decodes them to.

    `errors="replace"` maps every undecodable byte onto U+FFFD, so `0x80` and
    `0x81` — both legal config values — compared equal and the change was
    silent. The byte-level snapshot catches it, and because the decoded listing
    genuinely cannot name the key, the warning says that in words rather than
    reporting a change it then fails to describe.
    """
    repo = make_repo(tmp)
    config = repo / ".git" / "config"
    config.write_bytes(config.read_bytes() + b"[review]\n\tcollision = \x80\n")
    before = runner.tree_state(repo)
    config.write_bytes(config.read_bytes().replace(b"= \x80", b"= \x81"))
    after = runner.tree_state(repo)
    warnings = runner.tree_warnings(before, after, isolated=True)
    decoded_equal = before.config.get("review.collision") == after.config.get(
        "review.collision"
    )
    check(
        "a config change no decoding can show is still reported, and says why",
        decoded_equal
        and any("config changed" in warning for warning in warnings)
        and any("every decoded value is unchanged" in w for w in warnings),
        f"decoded_equal={decoded_equal} warnings={warnings}",
    )


def case_a_rewritten_reflog_message_is_caught(tmp: Path) -> None:
    """A reflog entry is more than the object it points at.

    The old snapshot projected each entry to `%gD %H`, dropping the message, both
    identities, the timestamp and the old OID. Rewriting `commit: two` to
    `commit: TWO` left the projection identical — a reflog can be edited to
    misattribute or misdate every operation in it while the digest says nothing
    moved. Reading the file keeps all of it.
    """
    repo = make_repo(tmp)
    (repo / "a.txt").write_text("two\n")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-qm", "commit: two")
    log = repo / ".git" / "logs" / "HEAD"
    tip = git(repo, "rev-parse", "HEAD").strip()
    size_before = log.stat().st_size
    before = runner.tree_state(repo)
    log.write_bytes(log.read_bytes().replace(b"commit: two", b"commit: TWO"))
    warnings = runner.tree_warnings(before, runner.tree_state(repo), isolated=True)
    # The rewrite is deliberately the same length and leaves the tip alone, so
    # neither a size comparison nor a ref comparison could have found it. Only
    # the content digest distinguishes these two files, which is the point.
    same_size = log.stat().st_size == size_before
    same_tip = git(repo, "rev-parse", "HEAD").strip() == tip
    check(
        "a reflog edited without moving any tip or changing size is reported",
        same_size
        and same_tip
        and any("reflog changed" in warning for warning in warnings)
        and any("HEAD" in warning for warning in warnings),
        f"same_size={same_size} same_tip={same_tip} warnings={warnings}",
    )


def case_an_unnamed_common_dir_file_is_still_reported(tmp: Path) -> None:
    """The property the redesign exists for: no list to be left off of.

    Four reviews each found one more shared surface the previous one had not
    listed. This asserts the thing that ends that sequence — a file nobody
    anticipated, under a name no branch of `shared_label` knows, still produces a
    warning that names it, via the catch-all rather than via being remembered.
    """
    repo = make_repo(tmp)
    before = runner.tree_state(repo)
    (repo / ".git" / "some-future-git-feature").write_text("state\n")
    warnings = runner.tree_warnings(before, runner.tree_state(repo), isolated=True)
    check(
        "an unanticipated shared file is reported by name, not silently ignored",
        any("repository state changed" in warning for warning in warnings)
        and any("some-future-git-feature" in warning for warning in warnings)
        and not any("isolation escaped" in warning for warning in warnings),
        f"warnings={warnings}",
    )


def case_a_clean_tree_clears_the_previous_backup(tmp: Path) -> None:
    """A clean tree returns no backup — so a stale one must not be left standing.

    `main()` decides whether a recovery backup exists by `is_dir()`, so a
    directory left over from an earlier run reads as this run's backup and would
    be offered to the user as recovery for work it does not contain. The early
    return skipped the cleanup that the dirty path already did.
    """
    repo = make_repo(tmp)
    dest = tmp / "pre"
    (dest / "untracked").mkdir(parents=True)
    (dest / "untracked" / "stale.txt").write_text("from a previous run\n")
    result, notes = runner.backup_worktree(repo, dest)
    check(
        "a clean tree removes the previous run's backup instead of adopting it",
        result is None and notes == [] and not dest.exists(),
        f"dest={result} notes={notes} exists={dest.exists()}",
    )


def case_an_uncopyable_untracked_file_is_named(tmp: Path) -> None:
    """The backup promises untracked work is preserved; a skip has to be audible.

    Symlinks are not followed and a socket or fifo cannot be copied, which is
    fine — silence about it is not. The user is told the tree was saved, so an
    omission nobody mentioned is the one that gets discovered after the original
    is gone.
    """
    repo = make_repo(tmp)
    (repo / "real.txt").write_text("kept\n")
    (repo / "link.txt").symlink_to(repo / "real.txt")
    dest, notes = runner.backup_worktree(repo, tmp / "pre")
    copied = dest / "untracked" / "real.txt" if dest else Path("/nope")
    skipped = [n for n in notes if "link.txt" in n]
    check(
        "an untracked symlink is named as skipped while the rest is still saved",
        len(skipped) == 1 and copied.is_file(),
        f"notes={notes} copied={copied.exists()}",
    )


CASES = [
    case_network_mode_pairs_workspace_write_with_the_flag,
    case_no_network_is_the_hard_read_only_sandbox,
    case_unchanged_tree_warns_about_nothing,
    case_a_file_the_review_created_is_reported,
    case_an_overwritten_dirty_file_is_reported,
    case_an_untracked_file_rewritten_in_place_is_reported,
    case_a_reverted_change_is_reported_too,
    case_a_commit_during_the_review_is_reported,
    case_backup_captures_a_tracked_edit,
    case_backup_copies_an_untracked_file,
    case_a_clean_tree_needs_no_backup,
    case_an_oversized_backup_says_so,
    case_prepared_tree_is_a_detached_checkout_outside_source,
    case_prepared_tree_contains_the_tracked_edit,
    case_prepared_tree_contains_the_untracked_file,
    case_teardown_removes_the_checkout_and_registration,
    case_teardown_happens_when_review_raises,
    case_failed_preparation_warns_and_does_not_raise,
    case_failed_isolation_refuses_the_networked_review,
    case_a_renamed_file_is_hashed_at_its_destination,
    case_a_quoted_path_is_still_hashed,
    case_prompt_rewrite_changes_only_the_repo_line,
    case_a_moved_remote_ref_has_its_own_warning,
    case_a_tag_made_inside_the_worktree_is_seen,
    case_config_written_from_a_linked_worktree_is_caught,
    case_two_config_records_are_not_one_record_with_a_newline,
    case_reflog_expiry_from_the_disposable_tree_is_caught,
    case_a_hook_installed_through_the_linked_worktree_is_caught,
    case_objects_pruned_from_the_disposable_tree_are_caught,
    case_a_config_value_utf8_cannot_represent_is_caught,
    case_a_rewritten_reflog_message_is_caught,
    case_an_unnamed_common_dir_file_is_still_reported,
    case_a_clean_tree_clears_the_previous_backup,
    case_an_uncopyable_untracked_file_is_named,
]


def main() -> int:
    for case in CASES:
        with tempfile.TemporaryDirectory() as d:
            case(Path(d))
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            print(f"      {detail}")
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"\n=== {len(results) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
