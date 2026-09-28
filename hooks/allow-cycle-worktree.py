#!/usr/bin/env python3
"""PreToolUse: pre-approve `EnterWorktree` into a worktree `/teamlead:cycle` made.

Step 7 of the cycle moves the session into the fresh tree with one
`EnterWorktree({path})` call. The skill's `allowed-tools` lists the tool, yet the
switch still prompted on every cycle, and the prompt lands mid-bootstrap where it
reads as the cycle stalling. The plugin carries its own permission needs as hooks
(`allow-run-writes.py`), so this one lives here too, not in the user's settings.

The grant is narrow on purpose. The call must be exactly `{path}`, and the path
must be the `worktree:` line of a handover file in `$TEAMLEAD_HOME/tasks/` that:

- carries a full cycle header (`slug:`, `repo:`, `worktree:`, `branch:` before
  `# Task`), so an arbitrary note in that directory grants nothing;
- was written in the last `FRESH_SECONDS` — step 6 writes it one step before the
  switch, and `--resume` starts in the tree without switching, so an older file
  has no legitimate switch left to grant;
- names the branch the worktree is actually on, and the target is a linked
  worktree (its `.git` is a file pointing at a gitdir with that `HEAD`).

A primary checkout, an arbitrary directory, a stale handover, or a `{name}` call
that creates a new tree gets no decision. The tasks directory is itself
auto-writable (`allow-run-writes.py`), so a forged fresh file is the residual
risk; what it can buy is a switch into an already-registered worktree, which is
the same thing the prompt would have offered.

Like its sibling it only ever *grants*: anything it does not recognise produces no
output and falls through to the normal permission flow.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
FRESH_SECONDS = 30 * 60
HEADER_KEYS = ("slug", "repo", "worktree", "branch")


def resolved(p: str) -> Path | None:
    """An absolute path with symlinks and `..` resolved, or `None`.

    A relative path would resolve against this hook's cwd, not the session's,
    so it is never granted.
    """
    candidate = Path(p)
    if not candidate.is_absolute():
        return None
    try:
        return candidate.resolve()
    except OSError:
        return None


def branch_of(tree: Path) -> str | None:
    """The branch a linked worktree has checked out, read without running git."""
    try:
        gitdir = (tree / ".git").read_text().strip().removeprefix("gitdir:").strip()
        head = (tree / gitdir / "HEAD").read_text().strip()
    except OSError:
        return None
    return head.removeprefix("ref: refs/heads/") if head.startswith("ref: ") else None


def handed_over(tasks: Path, now: float) -> dict[Path, str]:
    """`worktree -> branch` for every fresh, complete cycle handover file."""
    found: dict[Path, str] = {}
    for f in sorted(tasks.glob("*.md")) if tasks.is_dir() else []:
        try:
            if now - f.stat().st_mtime > FRESH_SECONDS:
                continue
            head = f.read_text(errors="replace").partition("\n# Task")[0]
        except OSError:
            continue
        fields = dict(
            (k.strip(), v.strip())
            for k, sep, v in (line.partition(":") for line in head.splitlines())
            if sep
        )
        if not all(fields.get(k) for k in HEADER_KEYS):
            continue
        tree = resolved(fields["worktree"])
        if tree is not None:
            found[tree] = fields["branch"]
    return found


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(event, dict) or event.get("tool_name") != "EnterWorktree":
        return 0
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict) or set(tool_input) != {"path"}:
        return 0
    raw = tool_input["path"]
    target = resolved(raw) if isinstance(raw, str) else None
    if target is None or not (target / ".git").is_file():
        return 0
    sys.path.insert(0, str(SCRIPTS))
    import paths

    branch = handed_over(paths.tasks_dir(), time.time()).get(target)
    if branch is None or branch_of(target) != branch:
        return 0
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": "teamlead cycle worktree",
            }
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
