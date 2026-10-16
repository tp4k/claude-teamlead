#!/usr/bin/env python3
"""Start the cycle's resume session inside its worktree, so nobody has to.

Usage:  python3 scripts/launch_cycle_session.py <abs worktree> <slug>

Cycle step 7 moves the session with EnterWorktree. That only works for a
worktree of the repository the session was launched from; a cycle started from
the plugin checkout (or any other repo) for a task in a different repository
is refused. The old fallback printed `cd <tree> && claude "..."` and stopped,
leaving the user to type it.

This script starts that session with Claude Code's own background sessions,
`claude --bg`, run with its cwd in the tree. That needs no particular terminal
or multiplexer: the session runs under Claude Code's background service and the
user opens it from any terminal with `claude attach <id>` (or `claude agents`).
Its cwd is the tree from the first prompt, so its workspace roots, nested
CLAUDE.md files and the step 8 cwd check are all right.

The binary is CLAUDE_CODE_EXECPATH, the one running this session, because the
`claude` on PATH can be a terminal's wrapper shim; PATH is the fallback. The
caller's session identity is stripped from the environment so the new session
starts as if typed in a fresh shell.

Output and exit codes:
  0  LAUNCHED <id> <worktree>, then the attach command
  1  MANUAL: cd <tree> && claude ...  no claude binary, or it refused (for
     example an untrusted tree); Claude's own error goes to stderr
  2  bad arguments; nothing launched
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys

# The cycle's own slug rule (skills/cycle/SKILL.md step 1), leading hyphen
# included; `--name=` keeps such a slug from reading as a claude flag.
SLUG = re.compile(r"[a-z0-9-]{1,30}")
BACKGROUNDED = re.compile(r"backgrounded · (\w+)")
# Variables that describe the calling session, not the user's environment.
CALLER_IDENTITY = (
    "CLAUDECODE", "CLAUDE_PID", "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_CODE_MESSAGING_SOCKET",
    "CLAUDE_CODE_MESSAGING_TOKEN",
)


def claude_binary() -> str | None:
    running = os.environ.get("CLAUDE_CODE_EXECPATH", "")
    if running and os.access(running, os.X_OK):
        return running
    return shutil.which("claude")


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

    prompt = f"/teamlead:cycle --resume {slug}"
    manual = f"MANUAL: cd {shlex.quote(tree)} && claude {shlex.quote(prompt)}"
    claude = claude_binary()
    if claude is None:
        print("no claude binary found to start the session", file=sys.stderr)
        print(manual)
        return 1
    env = {k: v for k, v in os.environ.items() if k not in CALLER_IDENTITY}
    proc = subprocess.run([claude, "--bg", f"--name={slug}", prompt], cwd=tree, env=env,
                          capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        print(f"claude --bg refused (exit {proc.returncode}): "
              f"{(proc.stderr or proc.stdout).strip()}", file=sys.stderr)
        print(manual)
        return 1
    found = BACKGROUNDED.search(proc.stdout)
    session = found.group(1) if found else slug
    print(f"LAUNCHED {session} {tree}")
    print(f"open it from any terminal: claude attach {session}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
