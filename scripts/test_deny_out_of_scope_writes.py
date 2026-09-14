#!/usr/bin/env python3
"""Regression suite for hooks/deny-out-of-scope-writes.py.

Run it with:  python3 scripts/test_deny_out_of_scope_writes.py

This is the plugin's only hook that ever says "no", and a PreToolUse hook on
Edit/Write sees every write in the session — so the interesting half of this
suite is not the denials, it is the silences. Each of the four preconditions
(implementer caller, resolvable brief, a fence to read, a target inside the
repo) gets a case that removes exactly that one and asserts the hook goes quiet
rather than blocking, because those are the shapes a real session hits when a
brief is hand-written, a run directory moves, or the user edits a file
themselves while an implementer happens to be running.

No pytest dependency — the skill's scripts run with bare python3, and a suite
that needs an install is a suite nobody runs.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "deny-out-of-scope-writes.py"
IMPLEMENTER = "teamlead:implementer"

FENCE_R1 = """# Implementer brief — WS-1 rate limit — round 1

## Scope
Add a token bucket to the server middleware.

```scope
apps/server/src/rate-limit.ts
apps/server/test/rate-limit.test.ts
apps/server/src/middleware/
packages/shared/src/*.ts
```

## Report file
$RUN/implementer-ws1-r1.md
"""

NO_FENCE = """# Implementer brief — WS-1 rate limit — round 1

## Scope
Add a token bucket to the server middleware. Files: apps/server/src/rate-limit.ts

## Report file
$RUN/implementer-ws1-r1.md
"""

results: list[tuple[str, bool, str]] = []


class Run:
    """One run directory on disk, plus the subagent transcript that points at it.

    Building both together is the point: the hook's whole job is to join a tool
    call to the brief the calling agent was dispatched with, and every case here
    needs that join to exist before it can remove one piece of it.
    """

    def __init__(self, tmp: Path) -> None:
        self.home = tmp / "home"
        self.repo = tmp / "repo"
        self.run = self.home / "runs" / "repo" / "2026-09-11-1200-limits"
        self.briefs = self.run / "briefs"
        self.briefs.mkdir(parents=True)
        (self.repo / "apps" / "server" / "src").mkdir(parents=True)
        (self.run / "repo.txt").write_text(f"{self.repo}\n")
        self.session = tmp / "projects" / "proj" / "abc-123"
        (self.session / "subagents").mkdir(parents=True)
        self.agent_id = "a00c58cce232015ba"
        self.transcript = self.session / "subagents" / f"agent-{self.agent_id}.jsonl"

    def brief(self, round_no: int, text: str) -> Path:
        path = self.briefs / f"impl-ws1-r{round_no}.md"
        path.write_text(text)
        return path

    def dispatch(self, round_no: int = 1, rework: bool = False) -> None:
        """Write the first transcript line the coordinator's brief `I` produces."""
        line = (
            f"$RUN = {self.run}. Repo: {self.repo}. Workstream: WS-1 (rate limit). "
            f"Round: {round_no}. Your brief: "
            f"{self.briefs}/impl-ws1-r{round_no}.md — read it in full first."
        )
        if rework:
            line += (
                " This is a rework round — the brief points at "
                f"{self.briefs}/impl-ws1-r{round_no - 1}.md and "
                f"{self.run}/implementer-ws1-r{round_no - 1}.md."
            )
        self.transcript.write_text(json.dumps({"type": "user", "content": line}) + "\n")

    def event(
        self,
        target: object,
        tool: str = "Edit",
        agent_type: str | None = IMPLEMENTER,
        transcript: object = None,
        agent_id: object = None,
    ) -> dict:
        event: dict[str, object] = {
            "hook_event_name": "PreToolUse",
            "tool_name": tool,
            "tool_input": {"file_path": str(target)},
            "cwd": str(self.repo),
            "transcript_path": str(self.session) + ".jsonl"
            if transcript is None
            else transcript,
            "agent_id": self.agent_id if agent_id is None else agent_id,
        }
        if agent_type is not None:
            event["agent_type"] = agent_type
        return event


def run(event: object, home: Path) -> subprocess.CompletedProcess[str]:
    payload = event if isinstance(event, str) else json.dumps(event)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ, TEAMLEAD_HOME=str(home)),
    )


def expect_deny(name: str, event: object, home: Path, mentions: str = "") -> None:
    """A structured deny: the JSON decision on stdout, and exit 0 to carry it.

    This asserted exit 2, which is the *other* refusal protocol — it blocks by
    exit code and feeds stderr back, discarding stdout. Requiring both meant the
    suite certified a combination that delivers the block without the reason, so
    every explanation these cases check was in fact thrown away at runtime.
    """
    r = run(event, home)
    try:
        out = json.loads(r.stdout)["hookSpecificOutput"]
        decision, why = (
            str(out["permissionDecision"]),
            str(out["permissionDecisionReason"]),
        )
    except (ValueError, KeyError, TypeError):
        decision, why = "", ""
    ok = decision == "deny" and r.returncode == 0 and mentions in why
    results.append(
        (name, ok, f"decision={decision!r} exit={r.returncode} reason={why!r}")
    )


def expect_silence(name: str, event: object, home: Path) -> None:
    """No output at all: the call falls through to the normal permission flow."""
    r = run(event, home)
    ok = r.stdout.strip() == "" and r.returncode == 0
    results.append(
        (name, ok, f"exit={r.returncode} stdout={r.stdout!r} stderr={r.stderr!r}")
    )


def case_the_fence_admits_its_own_files(tmp: Path) -> None:
    r = Run(tmp)
    r.brief(1, FENCE_R1)
    r.dispatch()
    expect_silence(
        "an exact file from the fence gets no decision — the fence is a deny "
        "list boundary, not a grant",
        r.event(r.repo / "apps/server/src/rate-limit.ts"),
        r.home,
    )
    expect_silence(
        "a file under a fenced directory is in scope",
        r.event(r.repo / "apps/server/src/middleware/token-bucket.ts"),
        r.home,
    )
    expect_silence(
        "a glob line matches",
        r.event(r.repo / "packages/shared/src/clock.ts"),
        r.home,
    )
    expect_silence(
        "a NEW file that does not exist yet is in scope — matching is on the "
        "path, so the red commit is not blocked",
        r.event(r.repo / "apps/server/test/rate-limit.test.ts", tool="Write"),
        r.home,
    )


def case_out_of_scope_is_denied(tmp: Path) -> None:
    r = Run(tmp)
    r.brief(1, FENCE_R1)
    r.dispatch()
    expect_deny(
        "a drive-by edit in another module is refused",
        r.event(r.repo / "apps/web/src/App.tsx"),
        r.home,
        mentions="apps/web/src/App.tsx",
    )
    expect_deny(
        "the reason names the brief, so the coder knows which fence it hit",
        r.event(r.repo / "package.json", tool="Write"),
        r.home,
        mentions="impl-ws1-r1.md",
    )
    expect_deny(
        "the reason tells the coder what to do instead of just saying no",
        r.event(r.repo / "README.md"),
        r.home,
        mentions="Open questions",
    )
    expect_deny(
        "a sibling of a fenced directory is not inside it",
        r.event(r.repo / "apps/server/src/middleware-old/x.ts"),
        r.home,
    )
    expect_deny(
        "MultiEdit is a write like any other",
        r.event(r.repo / "apps/web/src/App.tsx", tool="MultiEdit"),
        r.home,
    )


def case_a_missing_precondition_is_silence(tmp: Path) -> None:
    """Each of the four preconditions, removed one at a time."""
    r = Run(tmp)
    r.brief(1, FENCE_R1)
    r.dispatch()
    out = r.repo / "apps/web/src/App.tsx"
    expect_silence(
        "no agent_type: the coordinator's own edit, or the user's, is never ours "
        "to refuse",
        r.event(out, agent_type=None),
        r.home,
    )
    expect_silence(
        "a different agent type is not fenced — a reviewer or the writer agent "
        "has its own scope rules",
        r.event(out, agent_type="teamlead:writer"),
        r.home,
    )
    expect_silence(
        "an unresolvable transcript means no brief, and no brief means no " "opinion",
        r.event(out, agent_id="nonexistent"),
        r.home,
    )
    expect_silence(
        "a target outside the repo is not fenced — the run directory is where "
        "the report goes",
        r.event(r.run / "implementer-ws1-r1.md", tool="Write"),
        r.home,
    )
    expect_silence(
        "a `..` chain that leaves the repo is outside it, by resolution not by "
        "spelling",
        r.event(r.repo / ".." / "elsewhere" / "x.ts"),
        r.home,
    )
    expect_silence(
        "a non-writing tool is not our business",
        r.event(out, tool="Bash"),
        r.home,
    )


def case_a_brief_without_a_fence_blocks_nothing(tmp: Path) -> None:
    """The migration path: runs and hand-written briefs that predate the fence."""
    r = Run(tmp)
    r.brief(1, NO_FENCE)
    r.dispatch()
    expect_silence(
        "a brief with no scope fence disables the hook for that workstream",
        r.event(r.repo / "apps/web/src/App.tsx"),
        r.home,
    )
    (r.run / "repo.txt").unlink()
    r.brief(1, FENCE_R1)
    expect_silence(
        "a run with no repo.txt cannot place the target, so it decides nothing",
        r.event(r.repo / "apps/web/src/App.tsx"),
        r.home,
    )


def case_a_rework_round_inherits_the_fence(tmp: Path) -> None:
    """A rework brief is a pointer; the fence lives once, in round 1."""
    r = Run(tmp)
    r.brief(1, FENCE_R1)
    r.brief(
        2,
        "# round 2 (rework)\n\nRead first: impl-ws1-r1.md\n\n"
        "## Findings to fix\n- row 1\n",
    )
    r.dispatch(round_no=2, rework=True)
    expect_deny(
        "round 2 without a fence of its own still enforces round 1's",
        r.event(r.repo / "apps/web/src/App.tsx"),
        r.home,
        mentions="impl-ws1-r2.md",
    )
    expect_silence(
        "...and still admits round 1's files",
        r.event(r.repo / "apps/server/src/rate-limit.ts"),
        r.home,
    )


def case_a_widened_rework_fence_wins(tmp: Path) -> None:
    r = Run(tmp)
    r.brief(1, FENCE_R1)
    r.brief(
        2,
        "# round 2 (rework)\n\n## Scope\n```scope\n"
        "apps/server/src/rate-limit.ts\napps/web/src/App.tsx\n```\n",
    )
    r.dispatch(round_no=2, rework=True)
    expect_silence(
        "the coordinator widened the fence, so the file it added is now in scope",
        r.event(r.repo / "apps/web/src/App.tsx"),
        r.home,
    )
    expect_deny(
        "the nearest fence replaces the earlier one rather than merging, so a "
        "round-1 line the coordinator dropped is gone",
        r.event(r.repo / "apps/server/test/rate-limit.test.ts"),
        r.home,
    )


def case_the_subagent_transcript_is_found_either_way(tmp: Path) -> None:
    r = Run(tmp)
    r.brief(1, FENCE_R1)
    r.dispatch()
    expect_deny(
        "transcript_path pointing straight at the subagent's own file works",
        r.event(r.repo / "apps/web/src/App.tsx", transcript=str(r.transcript)),
        r.home,
    )
    expect_silence(
        "a transcript_path that is neither shape decides nothing",
        r.event(r.repo / "apps/web/src/App.tsx", transcript=12),
        r.home,
    )


def case_the_user_can_turn_it_off(tmp: Path) -> None:
    r = Run(tmp)
    r.brief(1, FENCE_R1)
    r.dispatch()
    (r.home / "config.json").write_text('{"scopeFence": false}')
    expect_silence(
        "scopeFence: false in $TEAMLEAD_HOME/config.json disables the hook",
        r.event(r.repo / "apps/web/src/App.tsx"),
        r.home,
    )
    (r.home / "config.json").write_text('{"scopeFence": true}')
    expect_deny(
        "...and true restores it, so the key is read rather than assumed",
        r.event(r.repo / "apps/web/src/App.tsx"),
        r.home,
    )


def case_the_repo_can_turn_it_off_against_the_global(tmp: Path) -> None:
    """`<repo>/.teamlead.json` is the documented first tier, so it has to win.

    The two files disagree on purpose. A global `true` with a repo-local `false`
    is the only shape that can tell "the repo tier was read" apart from "some
    tier said false" — and the hook used to ask `paths.setting` before it had
    worked out the repo, which makes that call skip the repo tier entirely and
    answer from the global file. Both orders pass a test where only one file
    exists; only this one fails.
    """
    r = Run(tmp)
    r.brief(1, FENCE_R1)
    r.dispatch()
    (r.home / "config.json").write_text('{"scopeFence": true}')
    (r.repo / ".teamlead.json").write_text('{"scopeFence": false}')
    expect_silence(
        "a repo-local .teamlead.json overrides an enabling global config",
        r.event(r.repo / "apps/web/src/App.tsx"),
        r.home,
    )
    (r.repo / ".teamlead.json").write_text('{"scopeFence": true}')
    expect_deny(
        "...and the same tier can enable it, so the file is read either way",
        r.event(r.repo / "apps/web/src/App.tsx"),
        r.home,
    )


def case_a_notebook_write_is_fenced_too(tmp: Path) -> None:
    """`NotebookEdit` spells its target `notebook_path`, and the hook is on it.

    Reading only `file_path` made the hook return silently for every notebook
    write — which from outside is indistinguishable from a write the fence
    allowed. Registering a tool and then failing open on it is worse than not
    registering it: the scope boundary reads as enforced and is not.
    """
    r = Run(tmp)
    r.brief(1, FENCE_R1)
    r.dispatch()
    event = r.event(r.repo / "apps/web/notebooks/explore.ipynb", tool="NotebookEdit")
    event["tool_input"] = {
        "notebook_path": str(r.repo / "apps/web/notebooks/explore.ipynb"),
        "new_source": "print('hello')",
    }
    expect_deny(
        "an out-of-scope NotebookEdit is denied under its own path key",
        event,
        r.home,
        mentions="explore.ipynb",
    )
    fenced = r.repo / "apps/server/src/middleware/notes.ipynb"
    inside = r.event(fenced, tool="NotebookEdit")
    inside["tool_input"] = {
        "notebook_path": str(fenced),
        "new_source": "print('hello')",
    }
    expect_silence(
        "a NotebookEdit inside the fence is not blocked by the new key",
        inside,
        r.home,
    )


def case_unusable_input_is_silent(tmp: Path) -> None:
    r = Run(tmp)
    r.brief(1, FENCE_R1)
    r.dispatch()
    expect_silence(
        "malformed stdin exits 0 rather than erroring into the session",
        "{not json",
        r.home,
    )
    expect_silence("an empty event exits 0", "", r.home)
    expect_silence(
        "a missing file_path is not a path",
        {"tool_name": "Edit", "tool_input": {}, "agent_type": IMPLEMENTER},
        r.home,
    )
    expect_silence(
        "a relative file_path is not resolvable against the agent's cwd from here",
        r.event("src/rate-limit.ts"),
        r.home,
    )


CASES = [
    case_the_fence_admits_its_own_files,
    case_out_of_scope_is_denied,
    case_a_missing_precondition_is_silence,
    case_a_brief_without_a_fence_blocks_nothing,
    case_a_rework_round_inherits_the_fence,
    case_a_widened_rework_fence_wins,
    case_the_subagent_transcript_is_found_either_way,
    case_the_user_can_turn_it_off,
    case_the_repo_can_turn_it_off_against_the_global,
    case_a_notebook_write_is_fenced_too,
    case_unusable_input_is_silent,
]


def main() -> int:
    for case in CASES:
        with tempfile.TemporaryDirectory() as d:
            case(Path(d))
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            print(f"      {detail}")
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"\n=== {len(results) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
