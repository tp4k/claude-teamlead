#!/usr/bin/env python3
"""PreToolUse: refuse an implementer's Edit/Write outside its own brief's scope.

`references/roles/implementer.md` already forbids drive-by edits, and the
coordinator already turns one into a NEEDS_REWORK row at triage. Both are true
*after* the fact: the file has been rewritten, the commit exists, and the revert
costs a whole round. This hook moves the same rule to the moment of the write,
which is the only moment it is still free.

It is deliberately the narrowest possible deny, because its sibling
`allow-run-writes.py` says why: a PreToolUse hook on Edit/Write sees every write
in the session, so a wrong "no" here blocks the user's own work. Four conditions
must all hold before this file answers at all —

  1. the caller is a teamlead implementer subagent (`agent_type`),
  2. its brief is resolvable from the subagent's own transcript,
  3. that brief (or an earlier round of the same workstream) declares a machine
     readable ```scope fence,
  4. the target is inside the repo the run names.

Anything else is silence, which falls through to the normal permission flow.
That ordering matters: every failure mode of this hook — a hand-written brief, a
planner that skipped the fence, an unreadable transcript, a run directory that
moved — lands on "no decision" rather than on a block. A scope fence that fails
open is a guardrail that occasionally misses; one that fails closed is an
implementer wedged mid-round with no way to explain itself.

The deny message is not a scolding. It restates the escape hatch the role file
already gives the coder (stop, report the file in Open questions, let the
coordinator widen the brief), because an agent that is blocked and told only
"no" will try the next nearest file instead of reporting.
"""
from __future__ import annotations

import fnmatch
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import paths  # noqa: E402  -- sibling scripts/ dir, resolved above

WRITERS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
IMPLEMENTER = "implementer"
BRIEF_RE = re.compile(r"[^\s`'\"]*briefs/impl-ws(\d+)-r(\d+)\.md")
FENCE_RE = re.compile(r"^```scope[ \t]*$(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)


def is_implementer(event: dict) -> bool:
    """Does this call come from a teamlead implementer subagent?

    Matched on the suffix, not on the full `teamlead:implementer`: the
    prefix is the plugin's installed name, which the user chooses, and a hook
    that stops firing because someone renamed the plugin directory fails
    silently in the direction of doing nothing at all.
    """
    agent_type = event.get("agent_type")
    return isinstance(agent_type, str) and agent_type.endswith(IMPLEMENTER)


def agent_transcript(event: dict) -> Path | None:
    """The subagent's own transcript file, from whichever shape we are handed.

    Inside a subagent `transcript_path` may already be that file
    (`.../<session>/subagents/agent-<id>.jsonl`); when it is the parent
    session's transcript instead, the subagent's sits beside it under a
    directory named for the session. Supporting both costs three lines and
    removes a guess about a harness detail we do not control.
    """
    raw = event.get("transcript_path")
    if not isinstance(raw, str) or not raw:
        return None
    transcript = Path(raw)
    if transcript.name.startswith("agent-") and transcript.suffix == ".jsonl":
        return transcript
    agent_id = event.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id:
        return None
    return transcript.with_suffix("") / "subagents" / f"agent-{agent_id}.jsonl"


def brief_from_prompt(transcript: Path) -> Path | None:
    """The brief path named in the first line of the subagent's transcript.

    That line is the dispatch prompt (brief `I` in the coordinator's SKILL.md),
    and it is written when the agent starts — long before its first Edit — so it
    is on disk by the time this runs. A rework prompt names more than one brief,
    because the current round points back at the previous one; the highest round
    number is the one the coder is working from.
    """
    try:
        with transcript.open() as handle:
            first = handle.readline()
    except OSError:
        return None
    best: tuple[int, str] | None = None
    for match in BRIEF_RE.finditer(first):
        candidate = (int(match.group(2)), match.group(0))
        if best is None or candidate[0] > best[0]:
            best = candidate
    if best is None:
        return None
    found = Path(best[1])
    return found if found.is_absolute() else None


def scope_patterns(brief: Path) -> list[str]:
    """The brief's ```scope fence, falling back down the rounds to round 1.

    A workstream's file scope is set once, by the planner, and a rework round
    inherits it — so a coordinator-written brief that omits the fence should
    resolve to the same answer rather than to no answer. Walking down is also
    what keeps the fence a *planner* obligation: one author, one place to get it
    right.
    """
    match = re.fullmatch(r"impl-ws(\d+)-r(\d+)\.md", brief.name)
    if match is None:
        return []
    ws, round_no = match.group(1), int(match.group(2))
    for earlier in range(round_no, 0, -1):
        path = brief.with_name(f"impl-ws{ws}-r{earlier}.md")
        try:
            text = path.read_text()
        except OSError:
            continue
        fence = FENCE_RE.search(text)
        if fence is None:
            continue
        lines = [line.strip() for line in fence.group(1).splitlines()]
        patterns = [line for line in lines if line and not line.startswith("#")]
        if patterns:
            return patterns
    return []


def repo_of_run(brief: Path) -> Path | None:
    """The repo path the run names, from `$RUN/repo.txt`.

    Read from the run rather than from the hook's `cwd`: the coordinator's cwd
    is the session's, and `cycle` moves that into a worktree partway
    through, so cwd is not reliably the tree the implementer is editing.
    """
    try:
        line = (brief.parent.parent / "repo.txt").read_text().strip()
    except OSError:
        return None
    repo = Path(line)
    return repo if line and repo.is_absolute() else None


def in_scope(rel: str, patterns: list[str]) -> bool:
    """Is the repo-relative path `rel` covered by any scope line?

    Three spellings are accepted, in the order a planner is likely to write
    them: the exact file, a directory (everything under it), and a glob. The
    glob uses `fnmatch`, whose `*` crosses `/` — so `src/*.ts` also matches
    `src/a/b.ts`. That is looser than a shell glob, and loose is the right
    direction for a rule whose mistakes block a coder.
    """
    for pattern in patterns:
        if rel == pattern:
            return True
        prefix = pattern.rstrip("/")
        if prefix and rel.startswith(prefix + "/"):
            return True
        if fnmatch.fnmatch(rel, pattern):
            return True
    return False


def relative_to_repo(target: str, repo: Path) -> str | None:
    candidate = Path(target)
    if not candidate.is_absolute():
        return None
    try:
        return candidate.resolve().relative_to(repo.resolve()).as_posix()
    except (OSError, ValueError):
        return None


def target_path(tool_input: object) -> str | None:
    """The path a writing tool is aimed at, whichever key that tool spells it with.

    `NotebookEdit` names its target `notebook_path`; every other writer uses
    `file_path`. Reading only `file_path` meant the hook was registered for
    `NotebookEdit` and then failed open on it — indistinguishable, from the
    outside, from a write the fence had allowed.
    """
    if not isinstance(tool_input, dict):
        return None
    for key in ("file_path", "notebook_path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def deny(reason: str) -> int:
    """Refuse the write and tell the implementer why, in one protocol.

    Structured JSON on stdout and exit 2 are two different mechanisms, not one:
    exit 2 blocks and feeds *stderr* back, ignoring stdout, while the JSON below
    is read only from a hook that exits 0. Emitting both meant the write was
    blocked with the explanation dropped on the floor — the implementer saw a
    bare refusal and no way to learn it should record an Open question instead.
    The JSON carries the reason, so 0 is the exit code that belongs with it.
    """
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


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(event, dict) or event.get("tool_name") not in WRITERS:
        return 0
    if not is_implementer(event):
        return 0
    tool_input = event.get("tool_input")
    target = target_path(tool_input)
    if not isinstance(target, str) or not target:
        return 0
    transcript = agent_transcript(event)
    brief = brief_from_prompt(transcript) if transcript is not None else None
    if brief is None:
        return 0
    patterns = scope_patterns(brief)
    repo = repo_of_run(brief)
    if not patterns or repo is None:
        return 0
    # The fence check waits for `repo`, which is only known here. Asking earlier
    # meant asking without it, and `paths.setting` skips the `<repo>/.teamlead.json`
    # tier entirely when it has no repo — so the documented per-repository
    # override silently did nothing and only the global config was ever read.
    if paths.setting("scopeFence", repo) is False:
        return 0
    rel = relative_to_repo(target, repo)
    if rel is None or in_scope(rel, patterns):
        return 0
    return deny(
        f"Out of brief scope: {rel} is not in the ## Scope fence of "
        f"{brief.name}, which covers {', '.join(patterns)}. Do not edit it and "
        "do not work around it. If this workstream genuinely needs the file, "
        "stop and record it under Open questions in your report — the "
        "coordinator widens the brief. If it is a refactor, file a Refactor "
        "request instead."
    )


if __name__ == "__main__":
    sys.exit(main())
