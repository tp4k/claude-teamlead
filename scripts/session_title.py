#!/usr/bin/env python3
"""Name the *current* session after the run, without relaunching Claude Code.

Usage: python3 session_title.py request <slug> [--session-id <id>]

The run's slug names the worktree, the branch and the run directory; the session
it all happens in used to be the one thing left holding a name like `claude-repo`.
The skill's answer to that was a relaunch (`claude -n <slug>`), documented as "the
only supported way to do it". It is not: a `UserPromptSubmit` hook may return a
`sessionTitle`, and Claude Code applies it to the live session through the same
setter `/rename` uses (verified against 2.1.267 — the hook path logs `Hook
sessionTitle applied` and records the name with `nameSource:"hook"`).

The one constraint that shapes this file: `sessionTitle` rides on
`UserPromptSubmit` and `SessionStart` and nothing else, so a title can only be
applied at a *prompt boundary*. A coordinator mid-turn cannot rename anything.
Hence the handoff: whoever knows the slug drops it here, and `hooks/session-title.py`
applies it the next time the user submits anything — in a `/teamlead:delegate` run,
the answer to the step 6 questions, a minute or two in.

Keyed by session id, because `$TEAMLEAD_HOME` is shared: two sessions running two
runs must not collect each other's names. The id is in the coordinator's Bash
environment as `$CLAUDE_CODE_SESSION_ID` and in the hook's stdin as `session_id`,
which is what makes the two halves meet without a registry.
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

import paths

MAX_LEN = 40
SAFE_ID = re.compile(r"\A[0-9a-fA-F][0-9a-fA-F-]{7,63}\Z")
# The `teamlead:` prefix is required, unlike the bare `/teamlead` this once
# accepted. That form was safe only because it repeated the plugin's own name;
# `delegate`, `cycle` and `codex-review` are ordinary words another plugin may
# own, and the two mistakes are not equally cheap. A title we decline to derive
# is replaced by the run's real slug at the next prompt anyway, while a title we
# derive from someone else's command renames a session that is not ours.
COMMAND = re.compile(r"\A/teamlead:(?:delegate|cycle|codex-review)\b")


def slugify(text: str) -> str:
    """The same shape `new_run.py` gives a run directory: lower-case `[a-z0-9-]`.

    A session name is read at a glance in `/resume` and in `ListAgents`, so it is
    worth nothing if it is a sentence. Truncation is by character rather than by
    word on purpose: a name cut mid-word still sorts and greps next to the run
    directory it was cut from, which a re-worded one does not.
    """
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:MAX_LEN].rstrip("-")


def pending_path(session_id: str) -> Path | None:
    """The drop file for `session_id`, or `None` when the id is not usable as one.

    The id reaches us from an environment variable and from hook stdin, so it is
    input, not a constant: anything that is not the uuid shape Claude Code uses
    gets no path at all. A `..` or a `/` here would aim a write, and later a
    delete, at a file of the caller's choosing.
    """
    if not SAFE_ID.match(session_id):
        return None
    return paths.session_titles_dir() / session_id


def applied_path(session_id: str) -> Path | None:
    """Where we record the last title *we* applied, next to the request."""
    path = pending_path(session_id)
    return None if path is None else path.with_name(path.name + ".applied")


def mark_applied(session_id: str, title: str) -> None:
    """Remember that this title is ours, so a later prompt may replace it.

    Without this the feature defeats itself. A title the hook applies comes back
    on the next prompt in the event's `session_title`, identical in every way to
    one the user typed — verified against 2.1.267. So the coarse name derived
    from the command text would make the session "already named" by the time the
    run's real slug arrives, and the good name would be dropped as an overwrite
    of a deliberate one. This file is the only thing that tells the two apart.
    """
    path = applied_path(session_id)
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{title}\n")
    except OSError:
        pass


def applied(session_id: str) -> str:
    """The last title we applied to this session, or `""` if we applied none."""
    path = applied_path(session_id)
    if path is None:
        return ""
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def request(session_id: str, title: str) -> Path | None:
    """Ask for `title` to be applied at the next prompt. Returns the drop file.

    Overwrites an existing request rather than appending to it: only the newest
    matters, and a stale name from a run that never finished should not be what
    the next prompt applies.
    """
    path = pending_path(session_id)
    slug = slugify(title)
    if path is None or not slug:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{slug}\n")
    sweep(path)
    return path


def sweep(keep: Path, max_age_days: int = 7) -> None:
    """Drop requests old enough that no live session is going to collect them.

    A request is consumed by the session's next prompt, so one still here a week
    later belongs to a session that ended before submitting another — a quit
    right after kickoff, a crash. Nothing reads it and nothing deletes it, so
    without this the directory only grows. Cheap enough to do on every request,
    and doing it here means the pruning happens in the process that has a reason
    to touch the directory at all.
    """
    cutoff = max_age_days * 86400
    try:
        entries = list(keep.parent.iterdir())
    except OSError:
        return
    for entry in entries:
        try:
            if entry != keep and time.time() - entry.stat().st_mtime > cutoff:
                entry.unlink()
        except OSError:
            continue


def consume(session_id: str) -> str:
    """The requested title, removing the request — it applies once, or never.

    Deleting before returning is deliberate. If the rename itself fails (a name
    another live session holds, a title the harness declines), retrying it at
    every prompt for the rest of the session would spend a hook run per prompt on
    a rename that has already been decided against.
    """
    path = pending_path(session_id)
    if path is None:
        return ""
    try:
        title = path.read_text().strip()
    except OSError:
        return ""
    try:
        path.unlink()
    except OSError:
        pass
    return slugify(title)


def derive_from_prompt(prompt: str) -> str:
    """A title for a `/teamlead:delegate …` prompt, before any slug exists yet.

    The drop file cannot help the turn the command is typed — the hook runs
    *before* the coordinator does, so the run's own slug does not exist yet. This
    is the coarse stand-in: the task's first few words, replaced by the real slug
    at the next prompt. It matters for the short runs that ask nothing and end
    without a second user turn, which the drop file alone would never reach.

    A file-path argument (`/teamlead:delegate <run>/review-followup.md`, the
    handoff `codex-review` prints) is named by its stem, since `-users-g-…` is
    a worse name than none.
    """
    if not COMMAND.match(prompt.strip()):
        return ""
    rest = COMMAND.sub("", prompt.strip(), count=1).strip()
    words = [w for w in rest.split() if not w.startswith("-")]
    if not words:
        return ""
    if "/" in words[0]:
        return slugify(Path(words[0]).stem)
    return fill(words)


def fill(words: list[str]) -> str:
    """As many whole words as `MAX_LEN` holds — never a word cut in half.

    A word count would be the obvious cap and is the wrong one: four words of a
    task like "fix the flaky auth test" spends 18 of the 40 characters and drops
    the noun that identifies it. Filling the budget instead means one limit
    rather than two, and it agrees with a word cap exactly where the budget is
    what actually binds.

    The first word goes in unconditionally, so a single word longer than the
    budget still yields a name (`slugify` truncates that one) rather than "".
    """
    slug = slugify(words[0])
    for word in words[1:]:
        candidate = f"{slug}-{slugify(word)}".strip("-")
        if len(candidate) > MAX_LEN:
            break
        slug = candidate
    return slug


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] != "request":
        print(__doc__)
        return 2
    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if "--session-id" in argv:
        session_id = argv[argv.index("--session-id") + 1]
    path = request(session_id, argv[1])
    if path is None:
        # Not an error: a script run outside a session has no session to rename.
        return 0
    print(f"SESSION_TITLE={path.read_text().strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
