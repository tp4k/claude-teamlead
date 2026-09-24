#!/usr/bin/env python3
"""PreToolUse: refuse a teamlead spawn that skips a step the run still owes.

`run_state.py` already knows, from the run directory alone, which step a run is
at and what it owes next. That knowledge used to be advisory: the coordinator
asks for it on a resume, and nothing asks for it on the way forward. Thirteen
runs in a row went from kickoff to planner to implementers with no config.json,
no options card and no plan design review, and nothing on disk objected —
every missing step reads, afterwards, like a decision.

So the same reading is applied at the three spawns that mark a step boundary:

  planner         needs config.json (step 3a), and a cycle's own options in it
  plan-validator  also needs the design reviews config.json promised (4a, 5)
  implementer     needs everything before dispatch: validation, the relay
                  turn (unless autopilot), an accepted scope cut applied

A Codex review that failed never blocks anything — only *starting* it is owed,
exactly as the skill says; see run_state.design_gap.

Like its sibling `deny-out-of-scope-writes.py`, it answers only when it is sure:
a `teamlead:`-namespaced subagent type whose role is gated, a prompt that opens
with `$RUN = <absolute path>` as every coordinator brief does, and a run
directory with a repo.txt. Anything else — a hand-written spawn, an unknown
layout, an exception — is silence, and silence falls through to the normal flow.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import run_state  # noqa: E402  -- sibling scripts/ dir, resolved above

SPAWNERS = {"Agent", "Task"}
RUN_RE = re.compile(r"\$RUN\s*=\s*(\S+)")


def role_of(tool_input: dict) -> str | None:
    """The gated role a spawn names, or None.

    Only a namespaced type counts: plugin agents register as `<plugin>:<role>`,
    and a bare `planner` is somebody else's agent. The prefix is whatever the
    plugin is installed as, so only the part after the colon is compared.
    """
    kind = tool_input.get("subagent_type")
    if not isinstance(kind, str) or ":" not in kind:
        return None
    role = kind.rsplit(":", 1)[1]
    return role if role in run_state.GATED_ROLES else None


def run_dir(prompt: object) -> Path | None:
    if not isinstance(prompt, str):
        return None
    match = RUN_RE.search(prompt)
    if match is None:
        return None
    raw = match.group(1).rstrip(".,;`'\"")
    run = Path(raw).expanduser()
    return run if run.is_absolute() and (run / "repo.txt").is_file() else None


def deny(reason: str) -> int:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    return 0


def decide(event: object) -> str | None:
    """The deny reason for this event, or None to stay silent."""
    if not isinstance(event, dict) or event.get("tool_name") not in SPAWNERS:
        return None
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    role = role_of(tool_input)
    run = run_dir(tool_input.get("prompt")) if role else None
    if run is None:
        return None
    gap = run_state.spawn_gap(run_state.Run(run), role)
    if gap is None:
        return None
    step, label, action, _ = gap
    where = f"python3 {SCRIPTS / 'run_state.py'} {run}"
    return (
        f"Not yet: this run is at step {step} — {label}, and spawning the {role} "
        f"now would skip it. Do that first: {action}. `{where}` shows where "
        "the run stands. If the user explicitly waived this step, record that "
        "in the run directory (config.json or the file the step writes) "
        "rather than skipping it silently."
    )


def main() -> int:
    # A gate that crashes must not block: every failure is silence.
    try:
        reason = decide(json.load(sys.stdin))
    except Exception:
        return 0
    return deny(reason) if reason else 0


if __name__ == "__main__":
    sys.exit(main())
