#!/usr/bin/env python3
"""PreToolUse: pre-approve `EnterWorktree` into a worktree `/teamlead:cycle` made.

Step 7 of the cycle moves the session into the fresh tree with one
`EnterWorktree({path})` call. The skill's `allowed-tools` lists the tool, yet the
switch still prompted on every cycle, and the prompt lands mid-bootstrap where it
reads as the cycle stalling. The plugin carries its own permission needs as hooks
(`allow-run-writes.py`), so this one lives here too, not in the user's settings.

The grant is narrow on purpose. The call must be exactly `{path}`, and the path
must be the `worktree:` line of a handover file in `$TEAMLEAD_HOME/tasks/` that:

- carries a full cycle header (`slug:`, `repo:`, `worktree:`, `branch:`,
  `session:` before `# Task`), so an arbitrary note in that directory grants
  nothing;
- names the session asking. `$TEAMLEAD_HOME` is shared by every session on the
  machine, so without this a handover would pre-approve the same switch for all of
  them; step 6 writes `$CLAUDE_CODE_SESSION_ID`, which is the hook's `session_id`
  (the pairing `scripts/session_title.py` already relies on);
- was written in the last `FRESH_SECONDS` — step 6 writes it one step before the
  switch, and `--resume` starts in the tree without switching, so an older file
  has no legitimate switch left to grant;
- names the branch the worktree is actually on, and the target is a linked
  worktree (its `.git` is a file pointing at a gitdir with that `HEAD`);
- targets a worktree git created within `FRESH_SECONDS`, and was itself written
  after that creation — the cycle makes the tree in step 3 and hands it over in
  step 6, so an older tree was not made by this cycle.

A primary checkout, an arbitrary directory, an older worktree, a stale handover,
or a `{name}` call that creates a new tree gets no decision.

What no hook can close: the tasks directory is auto-writable
(`allow-run-writes.py`), and a file the cycle writes and one the same model
forges are the same Write from the same session. The last check bounds what a
forgery buys to a switch into a worktree created in the last half hour, rather
than any registered tree; closing it fully needs a human click somewhere, which
is the prompt this hook exists to remove.

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
HEADER_KEYS = ("slug", "repo", "worktree", "branch", "session")


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


def linked_tree(tree: Path) -> tuple[str, float] | None:
    """`(branch, created)` for a linked worktree, read without running git.

    `created` is the mtime of the admin dir's `commondir`: `git worktree add`
    writes it once and nothing afterwards touches it, where `HEAD` and `index`
    move with every checkout.
    """
    try:
        pointer = (tree / ".git").read_text().strip().removeprefix("gitdir:")
        gitdir = tree / pointer.strip()
        head = (gitdir / "HEAD").read_text().strip()
        created = (gitdir / "commondir").stat().st_mtime
    except OSError:
        return None
    if not head.startswith("ref: refs/heads/"):
        return None
    return head.removeprefix("ref: refs/heads/"), created


def handed_over(tasks: Path, now: float,
                since: float) -> set[tuple[Path, str, str]]:
    """`(worktree, branch, session)` for every fresh, complete cycle handover file.

    Fresh means written within `FRESH_SECONDS` of `now` and not before `since`,
    the target tree's creation: step 6 follows the tree step 3 made, so a file
    that predates the tree was not written for it.

    A set, not a map keyed by worktree: two files naming one tree must not
    shadow each other, or which session gets the grant would depend on sort order.
    """
    found: set[tuple[Path, str, str]] = set()
    for f in sorted(tasks.glob("*.md")) if tasks.is_dir() else []:
        try:
            written = f.stat().st_mtime
            if now - written > FRESH_SECONDS or written < since:
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
            found.add((tree, fields["branch"], fields["session"]))
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
    session = event.get("session_id")
    raw = tool_input["path"]
    target = resolved(raw) if isinstance(raw, str) else None
    if not isinstance(session, str) or not session or target is None:
        return 0
    linked = linked_tree(target) if (target / ".git").is_file() else None
    now = time.time()
    if linked is None or now - linked[1] > FRESH_SECONDS:
        return 0
    branch, created = linked
    sys.path.insert(0, str(SCRIPTS))
    import paths

    grants = handed_over(paths.tasks_dir(), now, since=created)
    if (target, branch, session) not in grants:
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
