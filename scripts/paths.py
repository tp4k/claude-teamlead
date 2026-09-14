"""Where teamlead keeps state, and how one setting resolves across config tiers.

State lives outside the plugin, under `$TEAMLEAD_HOME` (default `~/.teamlead`),
for two reasons the plugin conversion introduced. `claude plugin update` replaces
the plugin directory, so anything kept under it is state a version bump can
delete; and a plugin is meant to be installable by someone other than its author,
which a 17 MB `runs/` tree of one machine's briefs and repo paths is not.

The env override is also what makes the config tiers testable. Before this the
global tier was the plugin's own `config.json` with no way to point it elsewhere,
so a machine that happened to have one silently changed what the tests asserted.

One file holds every setting: the cleanup policy used to be a second file, which
meant two formats and two lookup rules for one question ("what did the user
configure?"). Defaults live here in code rather than in a shipped JSON file, so
no config at all is a supported state instead of a missing-file error.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULTS: dict[str, object] = {
    "reworkCap": 3,
    "maxAgeDays": 30,
    "keepLastPerRepo": 5,
    "scopeFence": True,
}


def home() -> Path:
    return Path(os.environ.get("TEAMLEAD_HOME") or "~/.teamlead").expanduser()


def plugin_root() -> Path:
    """The installed plugin directory — where `references/` and `agents/` live.

    Derived from this file's own location rather than from `$CLAUDE_PLUGIN_ROOT`,
    which is set for hook and MCP commands but not for a script the coordinator
    runs itself. Two levels up from `scripts/paths.py` is the root either way, and
    a wrong answer here is a role file a reviewer cannot read.
    """
    return Path(__file__).resolve().parent.parent


def runs_dir() -> Path:
    return home() / "runs"


def tasks_dir() -> Path:
    return home() / "tasks"


def session_titles_dir() -> Path:
    return home() / "session-titles"


def config_path() -> Path:
    return home() / "config.json"


def read_json(path: Path) -> dict:
    """The JSON object at `path`, or `{}` for anything that is not one.

    Every caller is resolving a default, so an absent, unreadable or hand-broken
    config has to degrade to "not configured". A stopping rule that raises is
    worse than one that is merely not the number you set.
    """
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def positive_int(value: object) -> bool:
    # bool is an int in Python, and `"reworkCap": true` is a config typo, not a cap.
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def nonneg_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def setting(key: str, repo: Path | None = None, valid=None) -> object:
    """`key` from the repo's `.teamlead.json`, else the global config, else the default.

    A value that fails `valid` does not stop the search, it is skipped — a typo in
    one tier must not shadow a good value in the next, and the last resort is
    always `DEFAULTS`. This is the precedence `references/adr-workflow.md` states
    for `adrPath`; every setting uses it so there is one rule to remember.
    """
    sources = ([repo / ".teamlead.json"] if repo is not None else []) + [config_path()]
    for src in sources:
        data = read_json(src)
        if key in data and (valid is None or valid(data[key])):
            return data[key]
    return DEFAULTS.get(key)
