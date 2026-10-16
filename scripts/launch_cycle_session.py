#!/usr/bin/env python3
"""Start the cycle's resume session inside its worktree, so nobody has to.

Usage:  python3 scripts/launch_cycle_session.py <abs worktree> <slug>

Cycle step 7 moves the session with EnterWorktree. That only works for a
worktree of the repository the session was launched from; a cycle started from
the plugin checkout (or any other repo) for a task in a different repository
is refused. The old fallback printed `cd <tree> && claude "..."` and stopped,
leaving the user to type it. This script types it for them: inside cmux it
opens a new workspace in the tree, inside tmux a new window, each running
`claude '/teamlead:cycle --resume <slug>'`. That session starts with its cwd in
the tree, so its workspace roots, nested CLAUDE.md files and the step 8 cwd
check are all right from the first prompt.

Output and exit codes:
  0  LAUNCHED <cmux|tmux> <worktree>  the new session is running
  1  MANUAL: cd <tree> && claude ...  no multiplexer, or it refused the launch
  2  bad arguments; nothing launched
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys

# The cycle's own slug rule (skills/cycle/SKILL.md step 1). Checking it here also
# keeps the slug inert inside the shell command the multiplexer runs.
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,29}")


def resume_command(slug: str) -> str:
    return f"claude {shlex.quote(f'/teamlead:cycle --resume {slug}')}"


def launch_argv(tree: str, slug: str) -> tuple[str, list[str]] | None:
    """The multiplexer this process runs inside and the argv that opens the
    session there, or None. cmux wins over tmux: a tmux inside a cmux pane
    still sets CMUX_*, and the cmux workspace is the one the user sees."""
    command = resume_command(slug)
    cmux = shutil.which("cmux")
    if os.environ.get("CMUX_SOCKET_PATH") and cmux:
        return "cmux", [cmux, "new-workspace", "--name", slug, "--cwd", tree,
                        "--command", command, "--focus", "true"]
    tmux = shutil.which("tmux")
    if os.environ.get("TMUX") and tmux:
        return "tmux", [tmux, "new-window", "-c", tree, "-n", slug, command]
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    tree, slug = argv
    if not SLUG.fullmatch(slug):
        print(f"refused: slug {slug!r} is not [a-z0-9-], at most 30 chars",
              file=sys.stderr)
        return 2
    if not os.path.isabs(tree) or not os.path.isdir(tree):
        print(f"refused: {tree!r} is not an absolute path to a directory",
              file=sys.stderr)
        return 2

    manual = f"MANUAL: cd {shlex.quote(tree)} && {resume_command(slug)}"
    found = launch_argv(tree, slug)
    if found is None:
        print("no cmux or tmux around this session to launch into", file=sys.stderr)
        print(manual)
        return 1
    name, cmd = found
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        print(f"{name} refused the launch (exit {proc.returncode}): "
              f"{(proc.stderr or proc.stdout).strip()}", file=sys.stderr)
        print(manual)
        return 1
    print(f"LAUNCHED {name} {tree}  {proc.stdout.strip()}".rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
