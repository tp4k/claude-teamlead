#!/usr/bin/env python3
"""Regression suite for run_config.py:  python3 scripts/test_run_config.py

Two rules here are worth more than the code that implements them.

The first is the seed. Every run option defaults to off in `paths.DEFAULTS`, so
a machine with no config file would run with no security review and no perf
review — and the failure is invisible, because a reviewer that never ran and a
reviewer that found nothing produce the same silence in the final report. The
seed is what keeps "everything defaults to off" from meaning "the two reviewers
you already had are gone". It must therefore fire exactly once, and never touch
a config the user has since edited.

The second is the asymmetry between a bad config value and a bad flag. A config
typo is skipped so the next tier answers; a flag typo stops the run. The reason
is who is standing there: nobody is watching a config file, and someone is
always watching a flag they typed three seconds ago.

No pytest dependency — the skill's scripts run with bare python3.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "run_config.py"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def run(home: Path, repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, TEAMLEAD_HOME=str(home))
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(repo), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def value_of(output: str, key: str) -> str:
    for line in output.splitlines():
        if line.startswith(key + " "):
            return line.split()[1]
    return ""


def source_of(output: str, key: str) -> str:
    for line in output.splitlines():
        if line.startswith(key + " "):
            return " ".join(line.split()[2:])
    return ""


def fixture(tmp: Path) -> tuple[Path, Path]:
    home = tmp / "home"
    repo = tmp / "repo"
    repo.mkdir(parents=True)
    return home, repo


def case_a_missing_config_is_seeded_with_both_reviewers(tmp: Path) -> None:
    home, repo = fixture(tmp)
    out = run(home, repo).stdout
    written = json.loads((home / "config.json").read_text())
    check(
        "an absent config is seeded, reviewers on",
        written["securityReview"] == "on"
        and written["perfReview"] == "on"
        and value_of(out, "securityReview") == "on"
        and "seeded" in out,
        out,
    )


def case_an_existing_config_is_never_rewritten(tmp: Path) -> None:
    home, repo = fixture(tmp)
    home.mkdir()
    (home / "config.json").write_text(json.dumps({"securityReview": "off"}))
    out = run(home, repo).stdout
    kept = json.loads((home / "config.json").read_text())
    check(
        "a config the user edited is left alone",
        kept == {"securityReview": "off"}
        and value_of(out, "securityReview") == "off"
        and "seeded" not in out,
        out,
    )


def case_a_flag_beats_the_config(tmp: Path) -> None:
    home, repo = fixture(tmp)
    home.mkdir()
    (home / "config.json").write_text(json.dumps({"codexPlanReview": "always"}))
    out = run(home, repo, "--flags", "--codex-plan-review=hard").stdout
    check(
        "flag beats config",
        value_of(out, "codexPlanReview") == "hard"
        and source_of(out, "codexPlanReview") == "flag",
        out,
    )


def case_a_card_answer_beats_the_flag(tmp: Path) -> None:
    home, repo = fixture(tmp)
    out = run(
        home,
        repo,
        "--flags",
        "--codex-plan-review=hard",
        "--choice",
        "codexPlanReview=always",
    ).stdout
    check(
        "the card is the user's later word",
        value_of(out, "codexPlanReview") == "always"
        and source_of(out, "codexPlanReview") == "options card",
        out,
    )


def case_the_repo_config_beats_the_global_one(tmp: Path) -> None:
    home, repo = fixture(tmp)
    home.mkdir()
    (home / "config.json").write_text(json.dumps({"perfReview": "on"}))
    (repo / ".teamlead.json").write_text(json.dumps({"perfReview": "when-needed"}))
    out = run(home, repo).stdout
    check(
        "repo tier wins over global",
        value_of(out, "perfReview") == "when-needed"
        and source_of(out, "perfReview").endswith(".teamlead.json"),
        out,
    )


def case_a_config_typo_is_skipped_not_fatal(tmp: Path) -> None:
    home, repo = fixture(tmp)
    home.mkdir()
    (home / "config.json").write_text(json.dumps({"securityReview": "yes"}))
    proc = run(home, repo)
    check(
        "an invalid config value falls through to the default",
        proc.returncode == 0
        and value_of(proc.stdout, "securityReview") == "off"
        and source_of(proc.stdout, "securityReview") == "default",
        proc.stdout + proc.stderr,
    )


def case_a_flag_typo_stops_the_run(tmp: Path) -> None:
    home, repo = fixture(tmp)
    proc = run(home, repo, "--flags", "--codex-plan-review=sometimes")
    check(
        "an invalid flag value is fatal and names the options",
        proc.returncode == 1 and "off, hard, always" in proc.stderr,
        proc.stdout + proc.stderr,
    )


def case_a_value_flag_with_no_value_is_fatal(tmp: Path) -> None:
    home, repo = fixture(tmp)
    proc = run(home, repo, "--flags", "--codex-plan-review fix the login bug")
    check(
        "a bare value flag does not silently eat a word of the task",
        proc.returncode == 1 and "needs a value" in proc.stderr,
        proc.stdout + proc.stderr,
    )


def case_the_space_form_is_accepted(tmp: Path) -> None:
    home, repo = fixture(tmp)
    out = run(home, repo, "--flags", "--with-human-readable-plan pause").stdout
    check(
        "--flag value works as well as --flag=value",
        value_of(out, "humanReadablePlan") == "pause",
        out,
    )


def case_the_old_negative_flags_still_work(tmp: Path) -> None:
    home, repo = fixture(tmp)
    out = run(home, repo, "--flags", "--no-security-review --no-perf-review").stdout
    check(
        "--no-security-review and --no-perf-review still mean off",
        value_of(out, "securityReview") == "off"
        and value_of(out, "perfReview") == "off"
        and source_of(out, "securityReview") == "flag",
        out,
    )


def case_bare_adr_turns_it_on(tmp: Path) -> None:
    home, repo = fixture(tmp)
    out = run(home, repo, "--flags", "--adr make the cache pluggable").stdout
    check(
        "--adr is a bare flag meaning on",
        value_of(out, "adr") == "on",
        out,
    )


def case_task_text_is_not_mistaken_for_flags(tmp: Path) -> None:
    home, repo = fixture(tmp)
    proc = run(home, repo, "--flags", "rewrite the --perf-ish helper in utils")
    check(
        "an unrecognised token is ignored, not an error",
        proc.returncode == 0 and value_of(proc.stdout, "perfReview") == "on",
        proc.stdout + proc.stderr,
    )


def case_an_apostrophe_in_the_task_does_not_break_resolution(tmp: Path) -> None:
    home, repo = fixture(tmp)
    proc = run(home, repo, "--flags", "--adr don't drop the cache on restart")
    check(
        "an unbalanced quote in the task text is not a parse error",
        proc.returncode == 0 and value_of(proc.stdout, "adr") == "on",
        proc.stdout + proc.stderr,
    )


def case_autopilot_says_the_card_is_skipped(tmp: Path) -> None:
    home, repo = fixture(tmp)
    out = run(home, repo, "--flags", "--autopilot").stdout
    check(
        "autopilot reports the skipped card",
        "options card: skipped (--autopilot)" in out,
        out,
    )


def case_use_config_options_skips_only_the_card(tmp: Path) -> None:
    home, repo = fixture(tmp)
    out = run(home, repo, "--flags", "--use-config-options").stdout
    check(
        "--use-config-options skips the card without implying autopilot",
        "options card: skipped (--use-config-options)" in out
        and "every skippable stop" not in out,
        out,
    )


def case_the_resolved_config_is_written_for_a_later_session(tmp: Path) -> None:
    home, repo = fixture(tmp)
    target = tmp / "run" / "config.json"
    run(
        home,
        repo,
        "--flags",
        "--autopilot --codex-plan-review=always",
        "--out",
        str(target),
    )
    written = json.loads(target.read_text())
    check(
        "$RUN/config.json records the decision and where it came from",
        written["options"]["codexPlanReview"] == "always"
        and written["sources"]["codexPlanReview"] == "flag"
        and written["autopilot"] is True
        and written["optionsCard"] == "skipped"
        and written["codexPlanReviewAxes"][0] == "decomposition",
        json.dumps(written),
    )


def case_a_disabled_scope_fence_promotes_when_needed(tmp: Path) -> None:
    home, repo = fixture(tmp)
    home.mkdir()
    (home / "config.json").write_text(
        json.dumps(
            {
                "securityReview": "when-needed",
                "perfReview": "when-needed",
                "scopeFence": False,
            }
        )
    )
    out = run(home, repo).stdout
    check(
        "with no scope fence, when-needed becomes on and says so",
        value_of(out, "securityReview") == "on"
        and value_of(out, "perfReview") == "on"
        and "scopeFence off" in source_of(out, "securityReview"),
        out,
    )


def case_the_fence_leaves_when_needed_alone(tmp: Path) -> None:
    home, repo = fixture(tmp)
    home.mkdir()
    (home / "config.json").write_text(json.dumps({"securityReview": "when-needed"}))
    out = run(home, repo).stdout
    check(
        "with the fence on, when-needed survives untouched",
        value_of(out, "securityReview") == "when-needed",
        out,
    )


def case_an_unknown_choice_key_is_rejected(tmp: Path) -> None:
    home, repo = fixture(tmp)
    proc = run(home, repo, "--choice", "codeReview=off")
    check(
        "a card answer naming no real option is fatal",
        proc.returncode == 1 and "is not a run option" in proc.stderr,
        proc.stdout + proc.stderr,
    )


CASES = [
    case_a_missing_config_is_seeded_with_both_reviewers,
    case_an_existing_config_is_never_rewritten,
    case_a_flag_beats_the_config,
    case_a_card_answer_beats_the_flag,
    case_the_repo_config_beats_the_global_one,
    case_a_config_typo_is_skipped_not_fatal,
    case_a_flag_typo_stops_the_run,
    case_a_value_flag_with_no_value_is_fatal,
    case_the_space_form_is_accepted,
    case_the_old_negative_flags_still_work,
    case_bare_adr_turns_it_on,
    case_task_text_is_not_mistaken_for_flags,
    case_an_apostrophe_in_the_task_does_not_break_resolution,
    case_autopilot_says_the_card_is_skipped,
    case_use_config_options_skips_only_the_card,
    case_the_resolved_config_is_written_for_a_later_session,
    case_a_disabled_scope_fence_promotes_when_needed,
    case_the_fence_leaves_when_needed_alone,
    case_an_unknown_choice_key_is_rejected,
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
