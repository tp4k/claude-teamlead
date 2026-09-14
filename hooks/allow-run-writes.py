#!/usr/bin/env python3
"""PreToolUse: pre-approve Edit/Write inside teamlead's own state, and nothing else.

Every teamlead agent writes its report to `$RUN` — that is the whole design
(`references/run-directory.md`): a brief is a pointer, so the report has to be a
file. Before the plugin conversion that cost the user a line in their personal
`~/.claude/settings.json` naming the skill's own `runs/` path, which is the wrong
place for it twice over: a plugin that ships its own permission need should not
require hand-editing a user file to work, and the path in that line stopped being
correct the moment state moved to `$TEAMLEAD_HOME`.

Two trees are granted, not one. `runs/` holds the reports; `tasks/` holds the
worktree handover file `cycle` writes in phase 1 and reads back in phase
2 of a different session. Both left the plugin in the same move and both are this
plugin's own state, so granting only the first left the cycle prompting for the
one write it makes outside a run.

The one rule this file must not break: it only ever *grants*. A hook that returns
`deny` here would reach every Edit and Write in the session, including the
implementers' actual work in the repo — so a target that is not under the runs
tree produces no decision at all and falls through to the normal permission flow.
Silence is the safe answer; "no" is not ours to give.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import paths  # noqa: E402  -- sibling scripts/ dir, resolved above

WRITERS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}


def under(target: str, root: Path) -> bool:
    """Is `target` a path inside `root`, after symlinks and `..` are resolved?

    `resolve()` runs on both sides so that two spellings of one real directory
    agree: a run tree reached through a symlink, or a `..` that walks out of the
    grant and back into it. Comparing the strings instead would answer on how a
    path was written rather than on where it lands.

    A relative path is not resolved and not granted — it would resolve against
    this hook's cwd, which is not the agent's, so a guess here could approve a
    write somewhere else entirely.
    """
    candidate = Path(target)
    if not candidate.is_absolute():
        return False
    try:
        return root.resolve() in candidate.resolve().parents
    except OSError:
        return False


def granted_root(target: str) -> Path | None:
    """The `$TEAMLEAD_HOME` subtree `target` sits in, or `None` for anywhere else.

    Both roots come from `paths`, never from a literal here: `$TEAMLEAD_HOME` moves
    them together, and a second spelling of either path is a grant that keeps
    pointing at a tree the scripts have stopped using.
    """
    for root in (paths.runs_dir(), paths.tasks_dir()):
        if under(target, root):
            return root
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(event, dict) or event.get("tool_name") not in WRITERS:
        return 0
    tool_input = event.get("tool_input")
    target = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    root = granted_root(target) if isinstance(target, str) else None
    if root is None:
        return 0
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": f"teamlead {root.name} directory",
            }
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
