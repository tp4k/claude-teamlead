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
from collections.abc import Callable
from pathlib import Path

# The Codex plan-review rubric, in the order the prompt asks for them. It lives
# beside the other defaults because turning one axis off is a config edit, and a
# reader comparing their config against the shipped list needs both in one file.
PLAN_REVIEW_AXES: tuple[str, ...] = (
    "decomposition",
    "task-fit",
    "acceptance",
    "design-fit",
)

# Every run option defaults to "off". A run with no config and no flags is the
# plain loop this plugin started as, and a reader of config.json never has to
# know which keys are secretly on: absence means off, everywhere, for all of
# them. The two reviewers that predate this rule are restored by the config the
# first run seeds (`run_config.py`), not by a special case here — a special case
# is exactly the thing that makes the other twelve keys unreadable.
DEFAULTS: dict[str, object] = {
    "reworkCap": 3,
    "maxAgeDays": 30,
    "keepLastPerRepo": 5,
    "scopeFence": True,
    "codexPlanReview": "off",
    "opusPlanReview": "off",
    "humanReadablePlan": "off",
    "securityReview": "off",
    "perfReview": "off",
    "codexCodeReview": "off",
    "adr": "off",
    "planValidatorPasses": 1,
    "codexPlanReviewAxes": PLAN_REVIEW_AXES,
}

# What each option may say. Declaring the vocabulary here rather than in the
# script that reads it is what lets a config typo degrade the way `setting`
# promises: `"securityReview": "yes"` is skipped as invalid and the next tier
# answers, instead of reaching the coordinator as a third state nothing handles.
CHOICES: dict[str, tuple[str, ...]] = {
    "codexPlanReview": ("off", "hard", "always"),
    "opusPlanReview": ("off", "fallback", "always"),
    "humanReadablePlan": ("off", "generate", "pause"),
    "securityReview": ("off", "when-needed", "on"),
    "perfReview": ("off", "when-needed", "on"),
    "codexCodeReview": ("off", "on"),
    "adr": ("off", "on"),
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


def one_of(key: str) -> Callable[[object], bool]:
    """A validator accepting only the values `key` is allowed to take."""
    allowed = CHOICES[key]
    return lambda value: isinstance(value, str) and value in allowed


def setting(
    key: str,
    repo: Path | None = None,
    valid: Callable[[object], bool] | None = None,
) -> object:
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
