#!/usr/bin/env python3
"""Regression suite for review_package.py's answers carve-out:
   python3 scripts/test_review_package.py

`questions.md` is excluded from the package by `SELF_REPORT_RE`, and for most of
the file that is right: the questions the run chose to ask and the option it
marked `recommended:` are its own reasoning, and handing those to an independent
reviewer pre-empts the judgement it was asked to make.

Its `## Answers` section is the opposite thing — the user amending the task after
it was written — and withholding it grades the diff against a superseded request.
One real review opened a HIGH plan defect whose two sub-claims were answers 1 and
2 verbatim, recorded eighteen minutes before the first commit.

So the cut is by SECTION, and both halves of it need a test: the answers must
arrive, and the questions must still not.

No pytest dependency — the skill's scripts run with bare python3.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

PACKAGER = Path(__file__).resolve().parent / "review_package.py"

QUESTIONS = """# Open questions

1. Should the 54 shared rows appear once or twice?
   options:
     a) once, in the branch's `Prio`-bearing bytes
     b) twice, once in each side's bytes
   recommended: a
   rests on: the task's step 3.

## Routing

```
PLAN_WRITTEN ws=2 complex=no questions=1 decisions=3 adr_conflict=no
```

## Answers

1. once, in the branch's `Prio`-bearing bytes
scope: B — fold WS-1 into WS-2

## Later section

This heading must bound the answers block.
"""

SECOND_ROUND = QUESTIONS + """
## Answers

2. defer the reparent to a follow-up run
"""

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


def scaffold(
    tmp: Path, questions: str | None, task: str = "Merge the ledger."
) -> tuple[Path, Path, str]:
    repo = tmp / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("one\n")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-qm", "base")
    base = git(repo, "rev-parse", "HEAD").strip()
    (repo / "a.txt").write_text("two\n")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-qm", "head")

    run = tmp / "run"
    run.mkdir()
    (run / "repo.txt").write_text(str(repo))
    (run / "plan.md").write_text("# Plan\n\n## Decisions taken\n\nRows appear once.\n")
    (run / "task.md").write_text(task)
    if questions is not None:
        (run / "questions.md").write_text(questions)
    return repo, run, base


def package(
    tmp: Path, run: Path, base: str
) -> tuple[Path, subprocess.CompletedProcess[str]]:
    out = tmp / "pkg"
    env = dict(os.environ, TEAMLEAD_HOME=str(tmp / "home"))
    proc = subprocess.run(
        [sys.executable, str(PACKAGER), str(run), "--out", str(out), "--base", base],
        capture_output=True,
        text=True,
        env=env,
    )
    return out, proc


def case_answers_reach_the_package(tmp: Path) -> None:
    _, run, base = scaffold(tmp, QUESTIONS)
    out, proc = package(tmp, run, base)
    answers = out / "answers.md"
    body = answers.read_text() if answers.is_file() else ""
    check(
        "the user's answers ship as answers.md, verbatim",
        "1. once, in the branch's `Prio`-bearing bytes" in body
        and "scope: B — fold WS-1 into WS-2" in body,
        f"rc={proc.returncode} body={body!r} err={proc.stderr[-300:]}",
    )


def case_answers_stop_at_the_next_heading(tmp: Path) -> None:
    _, run, base = scaffold(tmp, QUESTIONS)
    out, _ = package(tmp, run, base)
    body = (out / "answers.md").read_text()
    check(
        "the section ends at the next `## ` heading",
        "This heading must bound the answers block." not in body,
        f"body={body!r}",
    )


def case_the_questions_stay_out(tmp: Path) -> None:
    _, run, base = scaffold(tmp, QUESTIONS)
    out, _ = package(tmp, run, base)
    leaked = [
        f.name
        for f in out.iterdir()
        if "recommended:" in f.read_text(errors="replace")
        or "Should the 54 shared rows" in f.read_text(errors="replace")
    ]
    check(
        "the questions and the run's `recommended:` option are in no package file",
        leaked == [],
        f"leaked={leaked}",
    )


def case_the_prompt_says_the_task_was_amended(tmp: Path) -> None:
    _, run, base = scaffold(tmp, QUESTIONS)
    out, _ = package(tmp, run, base)
    prompt = (out / "PROMPT.md").read_text()
    check(
        "PROMPT.md names answers.md and says it binds the diff",
        "answers.md" in prompt and "amended in flight" in prompt,
        f"prompt tail={prompt[-400:]!r}",
    )


def case_unanswered_questions_add_nothing(tmp: Path) -> None:
    unanswered = QUESTIONS.split("## Answers")[0]
    _, run, base = scaffold(tmp, unanswered)
    out, _ = package(tmp, run, base)
    prompt = (out / "PROMPT.md").read_text()
    check(
        "a questions.md with no ## Answers yields no answers.md and no paragraph",
        not (out / "answers.md").exists() and "amended in flight" not in prompt,
        f"files={[f.name for f in out.iterdir()]}",
    )


def case_a_run_with_no_questions_is_unaffected(tmp: Path) -> None:
    _, run, base = scaffold(tmp, None)
    out, proc = package(tmp, run, base)
    check(
        "a run that asked nothing still packages cleanly",
        proc.returncode == 0
        and not (out / "answers.md").exists()
        and (out / "PROMPT.md").is_file(),
        f"rc={proc.returncode} err={proc.stderr[-300:]}",
    )


def case_a_task_naming_questions_md_does_not_copy_it(tmp: Path) -> None:
    _, run, base = scaffold(
        tmp, QUESTIONS, task="Fix the ledger per questions.md and plan.md."
    )
    out, _ = package(tmp, run, base)
    check(
        "naming questions.md in the task still does not copy the whole file",
        not (out / "questions.md").exists(),
        f"files={[f.name for f in out.iterdir()]}",
    )


def case_a_second_answers_round_ships_too(tmp: Path) -> None:
    _, run, base = scaffold(tmp, SECOND_ROUND)
    out, _ = package(tmp, run, base)
    body = (out / "answers.md").read_text()
    check(
        "a run that asked twice ships both ## Answers blocks, not just the first",
        "1. once, in the branch's `Prio`-bearing bytes" in body
        and "2. defer the reparent to a follow-up run" in body
        and "This heading must bound the answers block." not in body,
        f"body={body!r}",
    )


def case_the_prompt_ranks_an_answer_above_the_plan(tmp: Path) -> None:
    _, run, base = scaffold(tmp, QUESTIONS)
    out, _ = package(tmp, run, base)
    prompt = (out / "PROMPT.md").read_text()
    check(
        "PROMPT.md ranks the answer above the plan's restatement of it",
        "outranks the plan" in prompt and "## Plan defects" in prompt,
        f"prompt tail={prompt[-600:]!r}",
    )


# A real generated plan, trimmed to one workstream: it carries every section the
# structured wording announces, which is the only fixture that can honestly
# assert that wording. A headings-only skeleton passed the four-section check
# while containing none of the per-workstream material the prompt promises, so
# it certified in a test exactly the false claim the production code was making.
STRUCTURED_PLAN = """# Plan

## Goal

Merge the ledger.

## WS-1 — ledger merge

### Spec excerpt

> Rows shared by both sides appear once, in the branch's bytes.

### Observable acceptance

`test_merge_ledger::shared_rows_appear_once` fails before, passes after.

### Test plan

existing: none relevant
new: `test_merge_ledger.py::shared_rows_appear_once` — the union is byte-exact

### Reuse and scope

reuse: `scripts/ledger.py::parse_rows`
do not reuse: the date-ordered comparator, which #1066 replaced
keep because: `parse_rows` already tolerates the `Prio` block header

## Decisions taken

Rows appear once — the task's step 3.

## Project forbiddens

No `# noqa`, verbatim from CLAUDE.md.

## Anti-scope

The reparent.
"""
# The opening words of the structured claim. Kept here rather than spelled out
# three times, because a test that looks for wording the prompt no longer uses
# passes for the wrong reason — it would read a renamed claim as an absent one.
ANNOUNCEMENT = "It carries, in every `## WS-` block"
# Two excerpts of the fixture above, quoted exactly so the edits that follow are
# real: every case using them asserts that the replacement changed the text, or a
# typo here would silently turn the case into a second copy of the positive one.
TEST_PLAN_BODY = (
    "existing: none relevant\n"
    "new: `test_merge_ledger.py::shared_rows_appear_once` — the union is byte-exact\n"
)
DO_NOT_REUSE_LINE = "do not reuse: the date-ordered comparator, which #1066 replaced\n"


def case_a_partial_plan_is_not_structured(tmp: Path) -> None:
    """The check and the claim have to name the same sections.

    This was one alternation, so any single heading made a plan "structured";
    tightening it to four headings fixed the cheap half and left the expensive
    one, because the same paragraph also promises per-workstream acceptance
    criteria, test plans and `reuse:` lines that four global headings are no
    evidence of. A skeleton of bare headings still cleared the bar.
    """
    _, run, base = scaffold(tmp, None)
    (run / "plan.md").write_text(
        "# Plan\n\n### Spec excerpt\n\n> x\n\n## Decisions taken\n\nd\n\n"
        "## Project forbiddens\n\nf\n\n## Anti-scope\n\na\n"
    )
    out, _ = package(tmp, run, base)
    prompt = (out / "PROMPT.md").read_text()
    check(
        "a headings-only skeleton is not announced as carrying the material",
        ANNOUNCEMENT not in prompt and "### Observable acceptance" in prompt,
        f"structured_at={prompt.find(ANNOUNCEMENT)}",
    )


def case_the_absent_sections_are_named_not_assumed(tmp: Path) -> None:
    """A partial plan must not be told it lacks a section it actually has.

    The negative branch enumerated a fixed list, so a plan carrying
    `## Anti-scope` and nothing else was described as having no `## Anti-scope`
    — and a reviewer that trusts the package then either hunts for sections that
    are not there or discounts the package's claims about itself. Absence is
    reported from the document, not from a constant.
    """
    _, run, base = scaffold(tmp, None)
    (run / "plan.md").write_text("# Plan\n\n## Anti-scope\n\nThe reparent.\n")
    out, _ = package(tmp, run, base)
    prompt = (out / "PROMPT.md").read_text()
    absent = prompt.split("These sections are absent", 1)[-1].split("\n", 1)[0]
    check(
        "the one section the plan does have is not listed as absent",
        "`## Anti-scope`" not in absent and "`### Spec excerpt`" in absent,
        f"absent_line={absent!r}",
    )


def case_a_full_plan_is_announced(tmp: Path) -> None:
    """...and a plan that really carries the material is still recognised."""
    _, run, base = scaffold(tmp, None)
    (run / "plan.md").write_text(STRUCTURED_PLAN)
    out, _ = package(tmp, run, base)
    prompt = (out / "PROMPT.md").read_text()
    check(
        "a plan carrying every advertised section is announced as carrying them",
        ANNOUNCEMENT in prompt and "Spec / plan conformance" in prompt,
        f"head={prompt.find(ANNOUNCEMENT)}",
    )


def announced_for(tmp: Path, plan: str) -> bool:
    """Does the package announce the structured material for this plan text?"""
    _, run, base = scaffold(tmp, None)
    (run / "plan.md").write_text(plan)
    out, _ = package(tmp, run, base)
    return ANNOUNCEMENT in (out / "PROMPT.md").read_text()


def case_an_emptied_section_is_not_material(tmp: Path) -> None:
    """A heading with nothing under it is not the thing the prompt promises.

    The positive fixture used to certify the production mistake rather than
    measure it: none of its section bodies affected the assertion, so deleting
    every one of them left the suite green while the prompt went on announcing a
    verbatim spec excerpt, acceptance criteria and a test plan. Emptying one
    section is the smallest edit that has to flip the answer — otherwise the
    fixture is only checking that headings can be spelled.
    """
    emptied = STRUCTURED_PLAN.replace(TEST_PLAN_BODY, "")
    check(
        "a section emptied of its body is no longer announced as present",
        emptied != STRUCTURED_PLAN and not announced_for(tmp, emptied),
        f"edited={emptied != STRUCTURED_PLAN}",
    )


def case_every_workstream_has_to_carry_it(tmp: Path) -> None:
    """"Per workstream" is a claim about all of them, not about finding one.

    The search ran once over the whole document, so a plan whose second
    workstream was a bare heading answered exactly as a complete one did — and
    the reviewer sent to WS-2 finds nothing where the package said to look. WS-1
    being complete is no comfort there.
    """
    truncated = STRUCTURED_PLAN + "\n## WS-2 — the reparent\n"
    check(
        "a workstream carrying none of the material is not announced away",
        not announced_for(tmp, truncated),
        "appended an empty WS-2 to the complete fixture",
    )


def case_the_optional_reuse_line_stays_optional(tmp: Path) -> None:
    """`do not reuse:` exists "where it applies", so requiring it would misreport.

    The planner's template makes `reuse:` and `keep because:` unconditional and
    the negative line conditional, which is why the prompt now names it
    separately. A check that demanded all three would call a correct plan
    incomplete — the same class of error as announcing what is not there, just
    pointing the other way.
    """
    without = STRUCTURED_PLAN.replace(DO_NOT_REUSE_LINE, "")
    check(
        "a workstream that drew no negative reuse call is still complete",
        without != STRUCTURED_PLAN and announced_for(tmp, without),
        f"edited={without != STRUCTURED_PLAN}",
    )


def case_a_heading_that_merely_starts_the_same_is_not_the_section(tmp: Path) -> None:
    """`### Spec excerpt appendix` is a different section with a similar name.

    The match was an unanchored prefix, so a plan could satisfy all seven
    requirements without carrying one of them, and the prompt then told the
    reviewer to read sections the document does not have. Announcing what is not
    there is the fault this whole check exists to prevent.
    """
    renamed = STRUCTURED_PLAN.replace("### Spec excerpt", "### Spec excerpt appendix")
    check(
        "a section whose name only starts the same way is not announced as present",
        renamed != STRUCTURED_PLAN and not announced_for(tmp, renamed),
        f"edited={renamed != STRUCTURED_PLAN}",
    )


def case_a_parenthesised_heading_is_still_the_section(tmp: Path) -> None:
    """The calibration guard: tightening the tail must not reject real plans.

    Real plans annotate a heading — `### Spec excerpt (verbatim from task.md)`,
    `### Test plan (WS-3)`. Across 174 plans the tail is empty 1510 times and
    parenthesised 5, and nothing else occurs, so the narrowest rule that accepts
    every real heading is "empty, or one parenthesis group". Without this case a
    later tightening to `$` alone would look correct and silently call a third of
    the corpus incomplete.
    """
    annotated = STRUCTURED_PLAN.replace(
        "### Spec excerpt", "### Spec excerpt (verbatim from task.md)"
    )
    check(
        "a heading annotated in parentheses is still recognised as the section",
        annotated != STRUCTURED_PLAN and announced_for(tmp, annotated),
        f"edited={annotated != STRUCTURED_PLAN}",
    )


def case_a_template_shown_in_a_labelled_fence_does_not_count(tmp: Path) -> None:
    """Quoting the template is showing the shape, not carrying the content.

    A plan that pastes the planner's own ```markdown skeleton satisfied every
    heading requirement while its real workstreams were empty — the headings were
    found inside the example. This is the emptied-section fault arriving by a
    different route, so it is refused the same way.
    """
    shown = """# Plan

## Goal

Merge the ledger.

Here is the shape each workstream should take:

```markdown
## WS-1 — example

### Spec excerpt
...

### Observable acceptance
...

### Test plan
...

### Reuse and scope
reuse: x
keep because: y
```

## Decisions taken

none

## Project forbiddens

none

## Anti-scope

none
"""
    check(
        "headings that exist only inside a labelled example are not announced",
        not announced_for(tmp, shown),
        "plan carries the template in a ```markdown fence and nothing else",
    )


def case_a_spec_quote_containing_code_keeps_its_headings(tmp: Path) -> None:
    """The mirror of the case above, and the one that is easy to get wrong.

    Markdown cannot nest same-length fences: any bare run of three backticks
    closes the block, so a plan quoting a spec that itself contains a ```python
    example inverts the parity of every fence after it. Pairing bare fences
    therefore swallowed the rest of the document — three real plans in the corpus
    lost their genuine `### Observable acceptance` onwards and were called
    incomplete. Only a fence with an info string opens a block now, which fails
    toward stripping too little; too little is the old permissiveness, while too
    much invents a false rejection of a real plan.
    """
    quoted = STRUCTURED_PLAN.replace(
        "> Rows shared by both sides appear once, in the branch's bytes.",
        "```\nRows appear once. Use:\n\n```python\ndef parse_rows(): ...\n```\n```",
    )
    check(
        "a spec quote containing its own code fence does not hide the sections",
        quoted != STRUCTURED_PLAN and announced_for(tmp, quoted),
        f"edited={quoted != STRUCTURED_PLAN}",
    )


CASES = [
    case_answers_reach_the_package,
    case_answers_stop_at_the_next_heading,
    case_the_questions_stay_out,
    case_the_prompt_says_the_task_was_amended,
    case_unanswered_questions_add_nothing,
    case_a_run_with_no_questions_is_unaffected,
    case_a_task_naming_questions_md_does_not_copy_it,
    case_a_second_answers_round_ships_too,
    case_the_prompt_ranks_an_answer_above_the_plan,
    case_a_partial_plan_is_not_structured,
    case_the_absent_sections_are_named_not_assumed,
    case_a_full_plan_is_announced,
    case_an_emptied_section_is_not_material,
    case_every_workstream_has_to_carry_it,
    case_the_optional_reuse_line_stays_optional,
    case_a_heading_that_merely_starts_the_same_is_not_the_section,
    case_a_parenthesised_heading_is_still_the_section,
    case_a_template_shown_in_a_labelled_fence_does_not_count,
    case_a_spec_quote_containing_code_keeps_its_headings,
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
