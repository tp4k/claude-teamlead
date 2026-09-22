#!/usr/bin/env python3
"""Regression suite for plan_review_package.py:
   python3 scripts/test_plan_review_package.py

A plan review happens before any code exists, so the reviewer has nothing to
read but the plan, the request, the user's answers, and the repository as it
stands. Two of those are easy to get wrong in ways nobody notices.

The first is the file list. It is the union of every round-1 brief's ```scope
fence — the same fences the PreToolUse hook enforces — and the whole reason to
hand it over is that it is a *boundary*, not an estimate. If the union silently
drops a brief, the reviewer is told the change cannot touch files it can, and
"the plan needs a file it is not allowed to write" stops being a finding it can
make.

The second is the prompt's repo line. `run_codex_review.py` parses the repo out
of the generated prompt with a regex, so a cosmetic edit to that one line here
breaks the runner in a different file, with no failing import to warn anyone.
That coupling gets a test of its own.

No pytest dependency — the skill's scripts run with bare python3.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGER = HERE / "plan_review_package.py"

sys.path.insert(0, str(HERE))
import run_codex_review  # noqa: E402

PLAN = """# Plan

## WS-1 — cache layer

Swap the map for an LRU.
"""

QUESTIONS = """# Open questions

1. Evict by size or by age?
   options:
     a) size
     b) age
   recommended: a

## Answers

1. size — the age variant needs a clock we do not have
"""

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


def scaffold(
    tmp: Path, *, plan: str | None = PLAN, questions: str | None = None
) -> tuple[Path, Path]:
    """A git repo plus a run directory pointing at it. No commits are needed.

    That is the point of this packager existing at all: `review_package.py`
    resolves `base..head` before it does anything else, and a plan under review
    has no commits to resolve.
    """
    repo = tmp / "repo"
    repo.mkdir()
    git(repo, "init", "-q")

    run = tmp / "run"
    run.mkdir()
    (run / "repo.txt").write_text(str(repo))
    (run / "task.md").write_text("Make the cache evict.\n")
    if plan is not None:
        (run / "plan.md").write_text(plan)
    if questions is not None:
        (run / "questions.md").write_text(questions)
    return repo, run


def brief(run: Path, number: int, body: str) -> None:
    briefs = run / "briefs"
    briefs.mkdir(exist_ok=True)
    (briefs / f"impl-ws{number}-r1.md").write_text(body)


def fenced(*paths: str) -> str:
    listed = "\n".join(paths)
    return f"# Brief\n\n```scope\n{listed}\n```\n\nBuild it.\n"


def package(
    tmp: Path, target: Path, *args: str
) -> tuple[Path, subprocess.CompletedProcess[str]]:
    out = tmp / "pkg"
    env = dict(os.environ, TEAMLEAD_HOME=str(tmp / "home"))
    proc = subprocess.run(
        [sys.executable, str(PACKAGER), str(target), "--out", str(out), *args],
        capture_output=True,
        text=True,
        env=env,
    )
    return out, proc


def prompt_of(out: Path) -> str:
    target = out / "PROMPT.md"
    return target.read_text() if target.is_file() else ""


def case_the_scope_union_spans_every_brief(tmp: Path) -> None:
    _, run = scaffold(tmp)
    brief(run, 1, fenced("src/cache.ts", "src/index.ts"))
    brief(run, 2, fenced("src/index.ts", "src/evict.ts"))
    out, proc = package(tmp, run)
    body = prompt_of(out)
    listed = [line for line in body.splitlines() if line.startswith("- `src/")]
    check(
        "every brief's fence contributes, deduplicated and sorted",
        listed == ["- `src/cache.ts`", "- `src/evict.ts`", "- `src/index.ts`"],
        f"rc={proc.returncode} listed={listed} err={proc.stderr[-300:]}",
    )


def case_a_brief_with_no_fence_does_not_silence_the_others(tmp: Path) -> None:
    _, run = scaffold(tmp)
    brief(run, 1, fenced("src/cache.ts"))
    brief(run, 2, "# Brief\n\nNo fence here at all.\n")
    out, _ = package(tmp, run)
    body = prompt_of(out)
    check(
        "an unfenced brief is skipped, not fatal to the union",
        "- `src/cache.ts`" in body
        and "No workstream declared a file scope" not in body,
        body[:400],
    )


def case_comments_inside_a_fence_are_not_paths(tmp: Path) -> None:
    _, run = scaffold(tmp)
    brief(run, 1, "# Brief\n\n```scope\n# the cache only\nsrc/cache.ts\n\n```\n")
    out, _ = package(tmp, run)
    body = prompt_of(out)
    check(
        "a `#` comment and a blank line are not scope entries",
        "- `src/cache.ts`" in body and "the cache only" not in body,
        body[:600],
    )


def case_no_fence_anywhere_warns_and_still_packages(tmp: Path) -> None:
    _, run = scaffold(tmp)
    out, proc = package(tmp, run)
    check(
        "a fenceless run warns that nothing enforces the file list",
        proc.returncode == 0
        and "WARNING: no brief declared a ```scope fence" in proc.stdout
        and "_No workstream declared a file scope._" in prompt_of(out),
        proc.stdout + proc.stderr,
    )


def case_the_runner_can_parse_the_repo_back_out(tmp: Path) -> None:
    repo, run = scaffold(tmp)
    out, _ = package(tmp, run)
    parsed = run_codex_review.repo_from_prompt(prompt_of(out))
    check(
        "run_codex_review.repo_from_prompt reads this prompt's repo line",
        Path(parsed).resolve() == repo.resolve(),
        f"parsed={parsed!r} expected={repo}",
    )


def case_the_answers_ship_and_are_announced(tmp: Path) -> None:
    _, run = scaffold(tmp, questions=QUESTIONS)
    out, _ = package(tmp, run)
    shipped = (out / "answers.md").read_text()
    check(
        "answers.md ships and the prompt calls it binding",
        "size — the age variant needs a clock we do not have" in shipped
        and "binding amendments to the task" in prompt_of(out),
        shipped[:200],
    )


def case_no_questions_means_no_answers_file(tmp: Path) -> None:
    _, run = scaffold(tmp)
    out, _ = package(tmp, run)
    check(
        "a run that asked nothing ships no empty answers.md",
        not (out / "answers.md").exists() and "answers.md" not in prompt_of(out),
        str(sorted(p.name for p in out.iterdir())),
    )


def case_an_axis_subset_is_honoured(tmp: Path) -> None:
    _, run = scaffold(tmp)
    out, proc = package(tmp, run, "--axes", "design-fit,acceptance")
    body = prompt_of(out)
    check(
        "--axes narrows the rubric but keeps the canonical order",
        "axes    : acceptance, design-fit" in proc.stdout
        and "1. **Acceptance criteria quality.**" in body
        and "2. **Design fit with the codebase.**" in body
        and "Decomposition" not in body,
        proc.stdout,
    )


def case_an_unknown_axis_is_fatal(tmp: Path) -> None:
    _, run = scaffold(tmp)
    _, proc = package(tmp, run, "--axes", "decomposition,security")
    check(
        "an axis with no rubric text stops the run instead of shipping a gap",
        proc.returncode == 1 and "unknown review axis: security" in proc.stderr,
        proc.stdout + proc.stderr,
    )


def case_a_run_with_no_plan_is_fatal(tmp: Path) -> None:
    repo, _ = scaffold(tmp, plan=None)
    out = tmp / "pkg"
    env = dict(os.environ, TEAMLEAD_HOME=str(tmp / "home"))
    proc = subprocess.run(
        [sys.executable, str(PACKAGER), str(repo), "--out", str(out)],
        capture_output=True,
        text=True,
        env=env,
    )
    check(
        "no plan means no review, and the error says how to supply one",
        proc.returncode == 1 and "--plan <file>" in proc.stderr,
        proc.stdout + proc.stderr,
    )


def case_an_external_plan_can_be_reviewed(tmp: Path) -> None:
    repo, _ = scaffold(tmp, plan=None)
    loose = tmp / "pr-body.md"
    loose.write_text("# Plan\n\nRewrite the evictor.\n")
    out, proc = package(tmp, repo, "--plan", str(loose))
    check(
        "--plan reviews a plan that never came from a run",
        proc.returncode == 0
        and "Rewrite the evictor." in (out / "plan.md").read_text(),
        proc.stdout + proc.stderr,
    )


def case_the_task_is_quoted_verbatim(tmp: Path) -> None:
    _, run = scaffold(tmp)
    out, _ = package(tmp, run)
    check(
        "the request reaches the reviewer as written",
        "Make the cache evict." in prompt_of(out),
        prompt_of(out)[:400],
    )


CASES = [
    case_the_scope_union_spans_every_brief,
    case_a_brief_with_no_fence_does_not_silence_the_others,
    case_comments_inside_a_fence_are_not_paths,
    case_no_fence_anywhere_warns_and_still_packages,
    case_the_runner_can_parse_the_repo_back_out,
    case_the_answers_ship_and_are_announced,
    case_no_questions_means_no_answers_file,
    case_an_axis_subset_is_honoured,
    case_an_unknown_axis_is_fatal,
    case_a_run_with_no_plan_is_fatal,
    case_an_external_plan_can_be_reviewed,
    case_the_task_is_quoted_verbatim,
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
