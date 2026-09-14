#!/usr/bin/env python3
"""Regression suite for hooks/session-title.py and scripts/session_title.py.

Run it with:  python3 scripts/test_session_title.py

The feature replaced a documented relaunch (`claude -n <slug>`) with an in-place
rename, so the cases are about the two ways that can go wrong. It must fire when
a run asks for a name — otherwise the relaunch was load-bearing after all — and
it must be *silent* everywhere else, because a plugin's hooks are installed
user-wide and this one is handed every prompt the user submits in any session.

The rule with teeth is "never overwrite a title the user chose". A rename that
takes a deliberate name away is not a smaller bug than no rename at all, so it
gets cases from both directions: the request is refused, and it is also not left
pending for some later prompt to apply.

No pytest dependency — the skill's scripts run with bare python3, and a suite
that needs an install is a suite nobody runs.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "session-title.py"
SCRIPT = Path(__file__).resolve().parent / "session_title.py"
SID = "71427d28-c493-44b5-8029-53694917dff3"
OTHER_SID = "0f6b803b-ae1a-32eb-c000-003201234567"

results: list[tuple[str, bool, str]] = []


def run_hook(event: object, home: Path) -> subprocess.CompletedProcess[str]:
    payload = event if isinstance(event, str) else json.dumps(event)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ, TEAMLEAD_HOME=str(home)),
    )


def request(
    home: Path, slug: str, session_id: str = SID
) -> subprocess.CompletedProcess[str]:
    """The writer half, invoked exactly as `new_run.py` invokes it."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), "request", slug, "--session-id", session_id],
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ, TEAMLEAD_HOME=str(home)),
    )


def prompt(
    text: str, session_id: str = SID, title: str | None = None
) -> dict[str, str]:
    event = {
        "hook_event_name": "UserPromptSubmit",
        "session_id": session_id,
        "cwd": "/repo",
        "prompt": text,
    }
    if title is not None:
        event["session_title"] = title
    return event


def title_of(r: subprocess.CompletedProcess[str]) -> str:
    """The `sessionTitle` the hook returned, or `""` for no output at all."""
    try:
        return str(json.loads(r.stdout)["hookSpecificOutput"]["sessionTitle"])
    except (ValueError, KeyError, TypeError):
        return ""


def expect_title(name: str, event: object, home: Path, want: str) -> None:
    r = run_hook(event, home)
    got = title_of(r)
    results.append(
        (
            name,
            got == want and r.returncode == 0,
            f"title={got!r} want={want!r} exit={r.returncode} stderr={r.stderr!r}",
        )
    )


def expect_silence(name: str, event: object, home: Path) -> None:
    r = run_hook(event, home)
    ok = r.stdout.strip() == "" and r.returncode == 0
    results.append(
        (name, ok, f"exit={r.returncode} stdout={r.stdout!r} stderr={r.stderr!r}")
    )


def case_a_requested_slug_is_applied_once(tmp: Path) -> None:
    home = tmp / "home"
    request(home, "980-toolgate")
    expect_title(
        "the slug new_run.py requested is applied at the next prompt",
        prompt("go"),
        home,
        "980-toolgate",
    )
    expect_silence(
        "and only at that one prompt — a request is consumed, not standing",
        prompt("now do the next round"),
        home,
    )


def case_the_request_is_per_session(tmp: Path) -> None:
    """$TEAMLEAD_HOME is shared, so two runs must not collect each other's names."""
    home = tmp / "home"
    request(home, "980-toolgate", session_id=SID)
    expect_silence(
        "another session's prompt does not collect this session's name",
        prompt("go", session_id=OTHER_SID),
        home,
    )
    expect_title(
        "...and the request is still there for the session that asked",
        prompt("go"),
        home,
        "980-toolgate",
    )


def case_a_chosen_title_is_never_overwritten(tmp: Path) -> None:
    home = tmp / "home"
    request(home, "980-toolgate")
    expect_silence(
        "a session named with claude -n or /rename keeps its name",
        prompt("go", title="my-own-name"),
        home,
    )
    expect_silence(
        "and the refused request is discarded, not left pending for a later prompt",
        prompt("go"),
        home,
    )
    expect_silence(
        "an already-titled session is not renamed by the command text either",
        prompt("/teamlead:delegate fix the flaky auth test", title="my-own-name"),
        home,
    )


def case_the_real_slug_replaces_our_own_guess(tmp: Path) -> None:
    """The sequence a real cycle runs, and the one that broke first.

    A title this hook applies is echoed back in `session_title` on every later
    prompt, so a presence check alone made turn 1's derived guess look like a
    name the user had chosen — and threw away the slug turn 2 was carrying.
    """
    home = tmp / "home"
    expect_title(
        "turn 1: the command text names the session",
        prompt("/teamlead:cycle fix the flaky auth test"),
        home,
        "fix-the-flaky-auth-test",
    )
    request(home, "980-toolgate")
    expect_title(
        "turn 2: the run's real slug replaces the guess we made ourselves",
        prompt("go", title="fix-the-flaky-auth-test"),
        home,
        "980-toolgate",
    )
    expect_silence(
        "turn 3: the name it already has is not re-applied every prompt",
        prompt("go on", title="980-toolgate"),
        home,
    )
    expect_silence(
        "and a /rename after ours is respected, not undone",
        prompt("/teamlead:delegate something else entirely", title="my-own-name"),
        home,
    )


def case_the_command_names_the_session_immediately(tmp: Path) -> None:
    """The turn the command is typed has no slug yet — the prompt is the fallback."""
    home = tmp / "home"
    expect_title(
        "the command's own task text names the session on the turn it is typed",
        prompt("/teamlead:delegate fix the flaky auth test in apps/server"),
        home,
        "fix-the-flaky-auth-test-in-apps-server",
    )
    expect_silence(
        "the unnamespaced spelling is declined now the names are ordinary words",
        prompt("/teamlead cycle this: add a retry to the poller"),
        home,
    )
    expect_title(
        "codex-review's own name is consumed, not left at the head of the title",
        prompt("/teamlead:codex-review recheck the coupon rounding fix"),
        home,
        "recheck-the-coupon-rounding-fix",
    )
    expect_title(
        "the budget is spent on whole words, never a word cut in half",
        prompt(
            "/teamlead:delegate migrate the notification preferences table"
            " to the new schema"
        ),
        home,
        "migrate-the-notification-preferences",
    )
    expect_title(
        "a first word longer than the budget still yields a name",
        prompt(f"/teamlead:delegate {'z' * 60} and more"),
        home,
        "z" * 40,
    )
    expect_title(
        "flags are not words in the name",
        prompt("/teamlead:delegate --no-perf-review --adr rework the toolgate"),
        home,
        "rework-the-toolgate",
    )
    expect_title(
        "the cycle's cold-path launcher names itself — why it carries no -n",
        prompt("/teamlead:cycle --resume 980-toolgate"),
        home,
        "980-toolgate",
    )
    expect_title(
        "a file-path handoff is named by its stem, not by its directories",
        prompt("/teamlead:delegate /Users/x/.teamlead/runs/r/review-followup.md"),
        home,
        "review-followup",
    )
    request(home, "980-toolgate")
    expect_title(
        "a requested slug beats the prompt text when both are available",
        prompt("/teamlead:delegate fix the flaky auth test"),
        home,
        "980-toolgate",
    )


def case_every_other_prompt_is_silent(tmp: Path) -> None:
    home = tmp / "home"
    expect_silence(
        "an ordinary prompt in an unrelated session gets no output",
        prompt("what does this function do?"),
        home,
    )
    expect_silence(
        "another plugin's command is not ours to name",
        prompt("/weekly-review"),
        home,
    )
    expect_silence(
        "a command whose name merely starts with the same letters is not a match",
        prompt("/teamleadership please"),
        home,
    )
    expect_silence(
        "a bare command with no task text has nothing to derive a name from",
        prompt("/teamlead:delegate"),
        home,
    )
    expect_silence(
        "a command that is all flags has nothing either",
        prompt("/teamlead:delegate --adr"),
        home,
    )
    expect_silence(
        "the command must open the prompt — a mention inside a sentence does not",
        prompt("should I use /teamlead:delegate for this refactor?"),
        home,
    )


def case_unusable_input_is_silent(tmp: Path) -> None:
    home = tmp / "home"
    expect_silence(
        "malformed stdin exits 0 rather than erroring into the prompt",
        "{not json",
        home,
    )
    expect_silence("an empty event exits 0", "", home)
    expect_silence("a non-object event exits 0", "[1, 2, 3]", home)
    expect_silence(
        "a missing session_id and a non-teamlead prompt produce nothing",
        {"hook_event_name": "UserPromptSubmit", "prompt": "hello"},
        home,
    )
    expect_silence(
        "a non-string prompt is not text to derive a name from",
        {"session_id": SID, "prompt": {"nested": "object"}},
        home,
    )


def case_a_hostile_session_id_gets_no_path(tmp: Path) -> None:
    """The id is input — from an env var and from hook stdin — not a constant."""
    home = tmp / "home"
    victim = tmp / "victim.md"
    victim.write_text("keep me\n")
    r = request(home, "980-toolgate", session_id="../../victim")
    intact = victim.read_text() == "keep me\n"
    results.append(
        (
            "a traversal id is refused rather than aiming the drop file",
            r.returncode == 0 and "SESSION_TITLE=" not in r.stdout and intact,
            f"exit={r.returncode} stdout={r.stdout!r} intact={intact}",
        )
    )
    expect_silence(
        "and the hook will not read one either",
        prompt("go", session_id="../../victim"),
        home,
    )


def case_stale_requests_are_swept(tmp: Path) -> None:
    home = tmp / "home"
    request(home, "980-toolgate", session_id=OTHER_SID)
    stale = home / "session-titles" / OTHER_SID
    old = time.time() - 8 * 86400
    os.utime(stale, (old, old))
    request(home, "deferred-ledger", session_id=SID)
    results.append(
        (
            "a request from a session that never came back is swept later",
            not stale.exists() and (home / "session-titles" / SID).exists(),
            f"stale_exists={stale.exists()}",
        )
    )


def case_the_slug_shape_matches_the_run_directory(tmp: Path) -> None:
    home = tmp / "home"
    request(home, "Fix The  Flaky_Auth Test!!")
    expect_title(
        "a requested title is slugified the way new_run.py slugifies a run dir",
        prompt("go"),
        home,
        "fix-the-flaky-auth-test",
    )
    request(home, "a" * 60)
    expect_title(
        "and truncated to 40 characters, with no trailing dash",
        prompt("go"),
        home,
        "a" * 40,
    )
    r = request(home, "!!!")
    results.append(
        (
            "a title with no usable characters is refused, not written empty",
            r.returncode == 0 and "SESSION_TITLE=" not in r.stdout,
            f"exit={r.returncode} stdout={r.stdout!r}",
        )
    )


CASES = [
    case_a_requested_slug_is_applied_once,
    case_the_request_is_per_session,
    case_a_chosen_title_is_never_overwritten,
    case_the_real_slug_replaces_our_own_guess,
    case_the_command_names_the_session_immediately,
    case_every_other_prompt_is_silent,
    case_unusable_input_is_silent,
    case_a_hostile_session_id_gets_no_path,
    case_stale_requests_are_swept,
    case_the_slug_shape_matches_the_run_directory,
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
