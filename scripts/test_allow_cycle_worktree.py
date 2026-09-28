#!/usr/bin/env python3
"""Regression suite for hooks/allow-cycle-worktree.py.

Run it with:  python3 scripts/test_allow_cycle_worktree.py

The hook grants one `EnterWorktree` — into the tree a cycle handover file names —
and must stay silent for every other switch. Each case builds a real git repo
with a linked worktree, because "is a linked worktree" is half of the grant.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "allow-cycle-worktree.py"

results: list[tuple[str, bool, str]] = []


def run(event: object, home: Path) -> subprocess.CompletedProcess[str]:
    payload = event if isinstance(event, str) else json.dumps(event)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ, TEAMLEAD_HOME=str(home)),
    )


def check(name: str, event: object, home: Path, allow: bool) -> None:
    r = run(event, home)
    if allow:
        try:
            out = json.loads(r.stdout)["hookSpecificOutput"]
            ok = out["permissionDecision"] == "allow" and r.returncode == 0
        except (ValueError, KeyError, TypeError):
            ok = False
    else:
        ok = r.stdout.strip() == "" and r.returncode == 0
    results.append(
        (name, ok, f"exit={r.returncode} stdout={r.stdout!r} stderr={r.stderr!r}")
    )


SESSION = "sess-a"


def enter(path: object, session: object = SESSION) -> dict:
    return {"tool_name": "EnterWorktree", "session_id": session,
            "tool_input": {"path": path}}


def git(*args: str) -> None:
    subprocess.run(["git", *args], check=True, capture_output=True)


def cycle_fixture(tmp: Path) -> tuple[Path, Path, Path]:
    """A repo, its linked worktree, and a home whose task file names the tree."""
    repo, tree, home = tmp / "repo", tmp / "repo-slug", tmp / "home"
    repo.mkdir()
    git("-C", str(repo), "init", "-q", "-b", "main")
    git("-C", str(repo), "-c", "user.email=e@x", "-c", "user.name=e",
        "commit", "-q", "--allow-empty", "-m", "base")
    git("-C", str(repo), "worktree", "add", "-q", "-b", "feat/slug", str(tree))
    (home / "tasks").mkdir(parents=True)
    (home / "tasks" / "slug.md").write_text(
        f"slug: slug\nrepo: {repo}\nworktree: {tree}\nbranch: feat/slug\n"
        f"session: {SESSION}\n\n"
        "# Task\nworktree: /somewhere/else\n"
    )
    return repo, tree, home


def case_the_handed_over_tree_is_allowed(tmp: Path) -> None:
    _, tree, home = cycle_fixture(tmp)
    check("the worktree a cycle task file names is allowed", enter(str(tree)),
          home, allow=True)
    check("a spelling with `..` that lands on it is allowed too",
          enter(str(tree / "sub" / "..")), home, allow=True)


def case_everything_else_gets_no_decision(tmp: Path) -> None:
    repo, tree, home = cycle_fixture(tmp)
    other = tmp / "repo-other"
    git("-C", str(repo), "worktree", "add", "-q", "-b", "feat/other", str(other))
    check("a linked worktree no task file names is not granted",
          enter(str(other)), home, allow=False)
    check("the primary checkout is not granted", enter(str(repo)), home,
          allow=False)
    check("a `worktree:` line in the task *body* grants nothing",
          enter("/somewhere/else"), home, allow=False)
    check("a relative path is not granted", enter("repo-slug"), home,
          allow=False)
    check("a `name` call (create a new tree) is not granted",
          {"tool_name": "EnterWorktree", "tool_input": {"name": "x"}}, home,
          allow=False)
    check("another tool is not our business",
          {"tool_name": "Bash", "tool_input": {"path": str(tree)}}, home,
          allow=False)
    check("with $TEAMLEAD_HOME elsewhere the grant is gone", enter(str(tree)),
          tmp / "elsewhere", allow=False)
    check("malformed stdin exits 0 silently", "{not json", home, allow=False)


def case_a_removed_tree_loses_the_grant(tmp: Path) -> None:
    repo, tree, home = cycle_fixture(tmp)
    git("-C", str(repo), "worktree", "remove", str(tree))
    tree.mkdir()
    check("a plain directory at the handed-over path is not granted",
          enter(str(tree)), home, allow=False)


def case_the_handover_must_be_fresh_complete_and_match(tmp: Path) -> None:
    """The Codex review's HIGH: any old or partial `worktree:` line used to grant."""
    repo, tree, home = cycle_fixture(tmp)
    task = home / "tasks" / "slug.md"
    hour_ago = time.time() - 3600
    os.utime(task, (hour_ago, hour_ago))
    check("a handover older than the freshness window grants nothing",
          enter(str(tree)), home, allow=False)
    task.write_text(f"worktree: {tree}\n\n# Task\nx\n")
    check("a bare `worktree:` note without the cycle header grants nothing",
          enter(str(tree)), home, allow=False)
    task.write_text(f"slug: slug\nrepo: {repo}\nworktree: {tree}\n"
                    f"branch: feat/other\nsession: {SESSION}\n\n# Task\nx\n")
    check("a handover naming a branch the tree is not on grants nothing",
          enter(str(tree)), home, allow=False)


def case_extra_inputs_get_no_decision(tmp: Path) -> None:
    """The Codex review's MEDIUM: `path` plus `name` is not the one-path switch."""
    _, tree, home = cycle_fixture(tmp)
    check("a call carrying both `path` and `name` is not granted",
          {"tool_name": "EnterWorktree", "session_id": SESSION,
           "tool_input": {"path": str(tree), "name": "x"}}, home, allow=False)


def case_the_grant_belongs_to_the_session_that_wrote_it(tmp: Path) -> None:
    """The PR #5 review: `$TEAMLEAD_HOME` is shared, so the handover must name
    the one session it pre-approves, not every session on the machine."""
    repo, tree, home = cycle_fixture(tmp)
    check("another session switching into the handed-over tree is not granted",
          enter(str(tree), session="sess-b"), home, allow=False)
    check("an event with no session id is not granted",
          enter(str(tree), session=None), home, allow=False)
    check("an empty session id is not granted", enter(str(tree), session=""),
          home, allow=False)
    (home / "tasks" / "slug.md").write_text(
        f"slug: slug\nrepo: {repo}\nworktree: {tree}\nbranch: feat/slug\n\n"
        "# Task\nx\n"
    )
    check("a handover with no `session:` line grants nothing", enter(str(tree)),
          home, allow=False)


def case_two_handovers_for_one_tree_do_not_shadow(tmp: Path) -> None:
    repo, tree, home = cycle_fixture(tmp)
    (home / "tasks" / "zz-later.md").write_text(
        f"slug: slug\nrepo: {repo}\nworktree: {tree}\nbranch: feat/slug\n"
        "session: sess-b\n\n# Task\nx\n"
    )
    check("the first file's session keeps its grant beside a second file",
          enter(str(tree)), home, allow=True)
    check("the second file's session gets its own grant",
          enter(str(tree), session="sess-b"), home, allow=True)


def case_only_a_newly_created_tree_is_granted(tmp: Path) -> None:
    """A forged fresh handover must not reach an old, long-registered worktree."""
    _, tree, home = cycle_fixture(tmp)
    commondir = tmp / "repo" / ".git" / "worktrees" / tree.name / "commondir"
    task = home / "tasks" / "slug.md"
    now = time.time()
    os.utime(commondir, (now - 3600, now - 3600))
    check("a worktree created before the freshness window is not granted",
          enter(str(tree)), home, allow=False)
    os.utime(commondir, (now - 60, now - 60))
    os.utime(task, (now - 120, now - 120))
    check("a handover written before its tree existed is not granted",
          enter(str(tree)), home, allow=False)
    os.utime(task, (now - 30, now - 30))
    check("a handover written after a fresh tree is granted", enter(str(tree)),
          home, allow=True)


CASES = [
    case_the_handed_over_tree_is_allowed,
    case_everything_else_gets_no_decision,
    case_a_removed_tree_loses_the_grant,
    case_the_handover_must_be_fresh_complete_and_match,
    case_extra_inputs_get_no_decision,
    case_the_grant_belongs_to_the_session_that_wrote_it,
    case_two_handovers_for_one_tree_do_not_shadow,
    case_only_a_newly_created_tree_is_granted,
]


def main() -> int:
    for case in CASES:
        with tempfile.TemporaryDirectory() as d:
            case(Path(d).resolve())
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            print(f"      {detail}")
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"\n=== {len(results) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
