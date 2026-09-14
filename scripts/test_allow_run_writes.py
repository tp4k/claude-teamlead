#!/usr/bin/env python3
"""Regression suite for hooks/allow-run-writes.py.

Run it with:  python3 scripts/test_allow_run_writes.py

The hook exists so the plugin carries its own permission need, and the whole risk
of that is scope: it sees every Edit and Write in the session, including the
implementers' work in the repo. So the cases below are mostly about what it must
*not* answer. A hook that grants too widely is a permission prompt the user
stopped seeing; one that ever says `deny` would block real work.

`under()` is where that scope lives, so each case names a path shape that has to
land on one side of it and asserts the decision, not the shape.

No pytest dependency — the skill's scripts run with bare python3, and a suite
that needs an install is a suite nobody runs.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "allow-run-writes.py"

results: list[tuple[str, bool, str]] = []


def run(
    event: object, home: Path, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    payload = event if isinstance(event, str) else json.dumps(event)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd) if cwd is not None else None,
        env=dict(os.environ, TEAMLEAD_HOME=str(home)),
    )


def decision_of(r: subprocess.CompletedProcess[str]) -> tuple[str, str]:
    """The hook's `(permissionDecision, permissionDecisionReason)`, or `("", "")`.

    Silence is a valid answer everywhere in this suite, so an unparseable stdout
    is not an error here — it is the "no decision" outcome, and the caller is the
    one that knows whether that was what the case expected.
    """
    try:
        out = json.loads(r.stdout)["hookSpecificOutput"]
        return str(out["permissionDecision"]), str(out["permissionDecisionReason"])
    except (ValueError, KeyError, TypeError):
        return "", ""


def expect_allow(
    name: str, event: object, home: Path, reason: str | None = None
) -> None:
    r = run(event, home)
    decision, why = decision_of(r)
    if not decision:
        results.append(
            (name, False, f"no decision in stdout={r.stdout!r} stderr={r.stderr!r}")
        )
        return
    ok = decision == "allow" and r.returncode == 0 and (reason is None or why == reason)
    results.append(
        (name, ok, f"decision={decision!r} reason={why!r} exit={r.returncode}")
    )


def expect_silence(
    name: str, event: object, home: Path, cwd: Path | None = None
) -> None:
    """No output at all: the tool call falls through to the normal permission flow."""
    r = run(event, home, cwd)
    ok = r.stdout.strip() == "" and r.returncode == 0
    results.append(
        (name, ok, f"exit={r.returncode} stdout={r.stdout!r} stderr={r.stderr!r}")
    )


def edit(path: object, tool: str = "Edit") -> dict:
    target = str(path) if isinstance(path, Path) else path
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": {"file_path": target},
    }


def home_with_run(tmp: Path) -> tuple[Path, Path]:
    home = tmp / "home"
    run_dir = home / "runs" / "myrepo" / "2026-09-10-1200-slug"
    run_dir.mkdir(parents=True)
    return home, run_dir


def case_a_report_write_is_allowed(tmp: Path) -> None:
    home, run_dir = home_with_run(tmp)
    report = run_dir / "implementer-ws1-r1.md"
    expect_allow(
        "an Edit of an existing report in $RUN is allowed", edit(report), home
    )
    expect_allow(
        "a Write of a report that does not exist yet is allowed — the agent is "
        "creating it",
        edit(run_dir / "verifier-r1.md", tool="Write"),
        home,
    )
    (run_dir / "briefs").mkdir()
    expect_allow(
        "a brief nested under $RUN is allowed",
        edit(run_dir / "briefs" / "impl-ws1-r2.md"),
        home,
    )


def case_repo_writes_get_no_decision(tmp: Path) -> None:
    home, _ = home_with_run(tmp)
    repo = tmp / "repo" / "src" / "server.ts"
    repo.parent.mkdir(parents=True)
    repo.write_text("export const x = 1\n")
    expect_silence(
        "an implementer's edit in the repo is neither granted nor denied — the "
        "hook only grants",
        edit(repo),
        home,
    )
    expect_silence(
        "a write to the user's settings is not granted",
        edit(Path.home() / ".claude" / "settings.json", tool="Write"),
        home,
    )
    expect_silence(
        "a sibling of the runs tree is not granted — the boundary is the "
        "directory, not a prefix",
        edit(home / "runs-elsewhere" / "x.md"),
        home,
    )
    expect_silence(
        "the runs directory itself is not a write target", edit(home / "runs"), home
    )


def case_the_cycle_handover_file_is_allowed(tmp: Path) -> None:
    """`tasks/` is the second granted tree, and it needs its own cases.

    `cycle` writes `$TEAMLEAD_HOME/tasks/<slug>.md` in phase 1 and reads
    it back in phase 2 from a different session — the one write the plugin makes
    outside a run directory. While the grant covered `runs/` alone this prompted,
    and the prompt is easy to miss because it arrives in the middle of a worktree
    bootstrap. The sibling case is what keeps the fix from being a prefix match.
    """
    home, _ = home_with_run(tmp)
    (home / "tasks").mkdir()
    expect_allow(
        "the cycle's handover file under $TEAMLEAD_HOME/tasks is allowed",
        edit(home / "tasks" / "980-toolgate.md", tool="Write"),
        home,
        reason="teamlead tasks directory",
    )
    expect_allow(
        "a run report still reports the runs tree, so the reason names which "
        "grant fired",
        edit(home / "runs" / "myrepo" / "2026-09-10-1200-slug" / "plan.md"),
        home,
        reason="teamlead runs directory",
    )
    expect_silence(
        "a sibling of the tasks tree is not granted either",
        edit(home / "tasks-old" / "980-toolgate.md"),
        home,
    )
    expect_silence(
        "$TEAMLEAD_HOME itself is not granted — only the two named subtrees are",
        edit(home / "config.json"),
        home,
    )


def case_the_transitional_symlink_resolves(tmp: Path) -> None:
    """A session that started before the state move still holds the old path."""
    home, run_dir = home_with_run(tmp)
    old = tmp / "plugin" / "runs"
    old.parent.mkdir(parents=True)
    old.symlink_to(home / "runs")
    expect_allow(
        "the pre-move plugin path is allowed, because both spellings resolve to "
        "one directory",
        edit(old / run_dir.parent.name / run_dir.name / "review-r1-code.md"),
        home,
    )


def case_traversal_out_is_not_granted(tmp: Path) -> None:
    home, run_dir = home_with_run(tmp)
    expect_silence(
        "a `..` chain that leaves the runs tree is not granted",
        edit(run_dir / ".." / ".." / ".." / ".." / "repo" / "src" / "server.ts"),
        home,
    )
    expect_allow(
        "a `..` chain that stays inside it still is — resolution decides, not "
        "the spelling",
        edit(run_dir / "briefs" / ".." / "plan.md"),
        home,
    )


def case_unusable_input_is_silent(tmp: Path) -> None:
    home, run_dir = home_with_run(tmp)
    expect_silence(
        "a relative path is not granted — it would resolve against the hook's "
        "cwd, not the agent's",
        edit("implementer-ws1-r1.md"),
        home,
        cwd=run_dir,
    )
    expect_silence(
        "a non-writing tool is not our business",
        edit(run_dir / "x.md", tool="Bash"),
        home,
    )
    expect_silence(
        "a Bash `tee` into $RUN is not granted either — only the file tools are "
        "matched",
        {"tool_name": "Bash", "tool_input": {"command": f"tee {run_dir}/x.md"}},
        home,
    )
    expect_silence(
        "a missing file_path is not a path",
        {"tool_name": "Edit", "tool_input": {}},
        home,
    )
    expect_silence(
        "a non-string file_path is not a path", edit({"nested": "object"}), home
    )
    expect_silence(
        "malformed stdin exits 0 rather than erroring into the session",
        "{not json",
        home,
    )
    expect_silence("an empty event exits 0", "", home)


def case_teamlead_home_moves_the_boundary(tmp: Path) -> None:
    """The grant follows $TEAMLEAD_HOME, so it cannot be aimed at a stale tree."""
    _, run_dir = home_with_run(tmp)
    elsewhere = tmp / "elsewhere"
    (elsewhere / "runs").mkdir(parents=True)
    (elsewhere / "tasks").mkdir()
    expect_silence(
        "with $TEAMLEAD_HOME pointed elsewhere, the old runs tree loses its grant",
        edit(run_dir / "plan.md"),
        elsewhere,
    )
    expect_allow(
        "...and the new one has it",
        edit(elsewhere / "runs" / "r" / "d" / "plan.md"),
        elsewhere,
    )
    expect_allow(
        "the tasks grant follows $TEAMLEAD_HOME too — neither root is a literal",
        edit(elsewhere / "tasks" / "slug.md", tool="Write"),
        elsewhere,
    )


CASES = [
    case_a_report_write_is_allowed,
    case_repo_writes_get_no_decision,
    case_the_cycle_handover_file_is_allowed,
    case_the_transitional_symlink_resolves,
    case_traversal_out_is_not_granted,
    case_unusable_input_is_silent,
    case_teamlead_home_moves_the_boundary,
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
