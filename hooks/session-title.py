#!/usr/bin/env python3
"""UserPromptSubmit: name the session after the teamlead run, in place.

The rename the skill used to demand a relaunch for. `sessionTitle` on this event
is a documented hook output ("Set the session title"), and Claude Code applies it
to the running session — no `/exit`, no `claude -n`, no second session.

Two sources, in this order:

1. A drop file from `scripts/session_title.py`, written by `new_run.py` with the
   run's real slug. This is the good name, and it is why the hook exists.
2. The prompt itself, when it *is* a teamlead command. The drop file cannot cover
   the turn the command is typed, because this hook runs before the coordinator
   and the slug does not exist yet — so a run that asks no questions and ends in
   one turn would never be renamed at all.

The rule that keeps it out of the user's way: **never overwrite a title the
session already has.** A title in the event means someone chose it — `claude -n`,
or `/rename` — and a plugin that silently renames a session out from under a
deliberate name is worse than one that leaves an ugly default alone. That also
makes the hook a no-op in every session outside a teamlead run, which matters
because a plugin's hooks are installed user-wide: this file sees every prompt the
user submits anywhere, and answers almost none of them.

Failure is silence. A `UserPromptSubmit` hook sits in front of the prompt itself;
crashing here would put an error between the user and their own message over a
cosmetic name, so every path that cannot produce a title produces no output.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType


def session_title() -> ModuleType:
    """`scripts/session_title.py`, imported from the sibling directory.

    Imported inside the function rather than at module scope so the `sys.path`
    insert it needs does not sit between the module's imports (E402). The path
    logic, the slug shape and the drop-file name live there and are not repeated
    here: the writer and the reader of that file have to agree, and two spellings
    of one path is how they stop agreeing.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import session_title as module

    return module


def title_for(event: dict[str, object], titles: ModuleType) -> str:
    """The title to apply for this prompt, or `""` to stay silent.

    "Already named" has to mean *named by someone else*. A title this hook
    applied is echoed back in `session_title` on every later prompt, so reading
    that field alone would let turn 1's coarse guess block turn 2's real slug —
    see `mark_applied`. Hence the comparison against what we applied rather than
    a bare presence check.

    The request is consumed before that check, not after: when the session does
    carry a name someone chose, the pending request is dead rather than pending.
    Left on disk it would outlive the session as a name nothing will ever apply.
    """
    session_id = event.get("session_id")
    sid = session_id if isinstance(session_id, str) else ""
    requested = titles.consume(sid) if sid else ""
    current = str(event.get("session_title") or "").strip()
    if current and current != titles.applied(sid):
        return ""
    prompt = event.get("prompt")
    derived = titles.derive_from_prompt(prompt) if isinstance(prompt, str) else ""
    title = requested or derived
    if not title or title == current:
        # Re-sending the name it already has spends a rename on nothing.
        return ""
    titles.mark_applied(sid, title)
    return title


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(event, dict):
        return 0
    try:
        title = title_for(event, session_title())
    except (ImportError, OSError):
        return 0
    if not title:
        return 0
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "sessionTitle": title,
            }
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
