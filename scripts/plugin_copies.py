"""Find other copies of this plugin that a session could load instead of this one.

    python3 plugin_copies.py        # exit 3 and say which, or print nothing

Claude Code registers every directory under `~/.claude/skills/` that carries a
`.claude-plugin/plugin.json` as a plugin. A linked worktree of this repository
put there — the natural place to put one, right beside the checkout — is a
second plugin with the same name, and which of the two a session loads is not
something this code can see or choose. Nothing announces it. One such worktree,
cut from a branch older than the options card and the plan design review, served
`delegate` and `cycle` to every session for a week; thirteen runs went by with
no `config.json` and no plan review, each one looking like a coordinator that
had skipped steps when it was faithfully following a skill that had none.

So the check is on the name, not on the version: two copies named alike are
ambiguous whichever one is newer, and the only safe answer is one copy. It runs
from `new_run.py`, because kickoff is the one call every run makes before any
agent is spawned — and it can only protect a run if the copy that loaded has it,
which is why it refuses rather than warns: a warning printed by the *right* copy
today is the one a future stale copy never prints.

`$TEAMLEAD_PLUGIN_SEARCH_DIRS` (os.pathsep-separated) replaces the default
search directory; the test suite uses it to stay off the real `~/.claude`.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import paths

DEFAULT_SEARCH = ("~/.claude/skills",)


def plugin_name(root: Path) -> str | None:
    """The `name` in `<root>/.claude-plugin/plugin.json`, or None.

    Unreadable, missing or malformed all mean None: a directory that names no
    plugin cannot shadow this one, and a guard that raises on a stranger's
    broken manifest would block every run for a problem that is not ours.
    """
    try:
        data = json.loads((root / ".claude-plugin" / "plugin.json").read_text())
    except (OSError, ValueError):
        return None
    name = data.get("name") if isinstance(data, dict) else None
    return name if isinstance(name, str) and name else None


def search_dirs() -> list[Path]:
    raw = os.environ.get("TEAMLEAD_PLUGIN_SEARCH_DIRS")
    entries = raw.split(os.pathsep) if raw else list(DEFAULT_SEARCH)
    return [Path(e).expanduser() for e in entries if e]


def other_copies(root: Path, search: list[Path]) -> list[Path]:
    """Every plugin directory in `search` named like `root`, other than `root`."""
    name = plugin_name(root)
    if name is None:
        return []
    me = root.resolve()
    found: list[Path] = []
    for d in search:
        try:
            children = sorted(d.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.is_dir():
                continue
            real = child.resolve()
            if real != me and real not in found and plugin_name(child) == name:
                found.append(real)
    return found


def refusal(root: Path, copies: list[Path]) -> str:
    listed = "\n".join(f"  {c}" for c in copies)
    return (
        f"REFUSED: another copy of this plugin is installed beside the one "
        f"running ({root}):\n{listed}\n"
        "Claude Code loads plugins from every one of those directories under the "
        "same name, so this session may be running either copy's skills — an "
        "older branch means steps (options card, plan review) that silently do "
        "not exist. Keep one copy there: move a worktree out with "
        "`git worktree move <path> <somewhere outside ~/.claude/skills>`, or "
        "remove it, and load a branch you are testing with "
        "`claude --plugin-dir <path>` instead. Then start a new session — the "
        "skills a session loaded do not change under it."
    )


def check() -> str | None:
    """The refusal text when this plugin is shadowed, else None."""
    root = paths.plugin_root()
    copies = other_copies(root, search_dirs())
    return refusal(root, copies) if copies else None


def main() -> int:
    msg = check()
    if msg:
        print(msg)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
