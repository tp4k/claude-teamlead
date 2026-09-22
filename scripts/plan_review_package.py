"""Package a teamlead plan for an independent design review, before any code exists.

`review_package.py` grades a finished diff and cannot be reused here: every part
of it resolves `base..head`, and a plan under review has no commits at all —
`resolve_base()` would raise before the prompt was built. What a plan review
needs instead is the plan, the request it came from, the decisions the user has
already taken, and the list of files the plan says it will touch.

That file list is the part worth explaining. It is the union of every round-1
brief's fenced ```scope block — the same blocks the PreToolUse hook enforces, read
with the same pattern — because an implementer physically cannot write outside
them. So the union is not an estimate of what the change will touch; it is the
boundary the change is held to, which makes it the right thing to hand a reviewer
asking "does this design fit the codebase?".
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

import paths
from review_package import (
    Fail,
    format_recent,
    referenced_inputs,
    resolve_target,
    user_answers,
)

# The hook's own pattern, deliberately identical: a fence the hook would not
# recognise is not a fence the implementer is bound by, and listing it here
# would promise the reviewer a boundary that does not exist.
FENCE_RE = re.compile(r"^```scope[ \t]*$(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)

AXIS_TEXT: dict[str, tuple[str, str]] = {
    "decomposition": (
        "Decomposition and sequencing",
        "Are the workstreams the right cut of this task — independent where the "
        "plan runs them in parallel, ordered where one genuinely needs another's "
        "output? Name any two streams that will collide on the same file, any "
        "dependency the wave order gets backwards, and any stream that is really "
        "two pieces of work or two that are really one.",
    ),
    "task-fit": (
        "Does the plan actually satisfy the task",
        "Read the task and the answers, then the plan. What has the user asked "
        "for that no workstream delivers, and what does the plan build that "
        "nobody asked for? Quote the words of the task you are measuring against "
        "— a gap you cannot quote is an opinion about scope, not a finding.",
    ),
    "acceptance": (
        "Acceptance criteria quality",
        "For each workstream: could someone who did not write the plan tell "
        "whether it is done, from the stated criteria alone? Flag criteria that "
        "restate the implementation, that no test could observe, or that would "
        "pass with the feature stubbed out.",
    ),
    "design-fit": (
        "Design fit with the codebase",
        "Read the files listed below in the real repository. Does the plan's "
        "approach match how this codebase already does this kind of thing, or "
        "does it introduce a second way of doing it? Flag a new abstraction "
        "where an existing one fits, a layering the tree does not use, and any "
        "place the plan's assumption about existing code is wrong.",
    ),
}


def scope_union(run_dir: Path | None) -> list[str]:
    """Every path any round-1 brief's ```scope fence names, de-duplicated, sorted."""
    if run_dir is None:
        return []
    found: set[str] = set()
    for brief in sorted((run_dir / "briefs").glob("impl-ws*-r1.md")):
        fence = FENCE_RE.search(brief.read_text(errors="replace"))
        if not fence:
            continue
        for line in fence.group(1).splitlines():
            entry = line.strip()
            if entry and not entry.startswith("#"):
                found.add(entry)
    return sorted(found)


def resolve_axes(repo: Path, override: str | None) -> list[str]:
    """The rubric axes to ask for, in the plugin's canonical order.

    Order is fixed rather than taken from the config so that two runs with the
    same axes produce prompts that differ only where the plan differs — a prompt
    whose sections move around is one nobody can diff between rounds.
    """
    if override is not None:
        wanted = {item.strip() for item in override.split(",") if item.strip()}
    else:
        configured = paths.setting(
            "codexPlanReviewAxes",
            repo,
            lambda value: isinstance(value, list) and all(
                isinstance(item, str) for item in value
            ),
        )
        wanted = set(configured) if isinstance(configured, list) else set(
            paths.PLAN_REVIEW_AXES
        )
    unknown = wanted - set(paths.PLAN_REVIEW_AXES)
    if unknown:
        raise Fail(
            f"unknown review axis: {', '.join(sorted(unknown))} — "
            f"pick from {', '.join(paths.PLAN_REVIEW_AXES)}"
        )
    if not wanted:
        raise Fail("no review axes left to ask about")
    return [axis for axis in paths.PLAN_REVIEW_AXES if axis in wanted]


def build_prompt(
    repo: Path,
    task: str,
    axes: list[str],
    scope: list[str],
    inputs: list[str],
    has_answers: bool,
    out: Path,
) -> str:
    lines: list[str] = []
    add = lines.append

    add("# Review this plan before it is built")
    add("")
    add(
        "You are reviewing a plan, not a diff. No code has been written yet, so "
        "nothing here can be checked by reading a change — everything you say "
        "has to come from the plan, the request, and the repository as it stands "
        "today. That is the point: a defect caught here costs a paragraph, and "
        "the same defect caught after implementation costs the round that built it."
    )
    add("")
    add("## Where things are")
    add("")
    add(f"- Repo / worktree: `{repo}`")
    add(f"- This package: `{out}`")
    add("- `plan.md` — the plan under review, copied whole")
    if has_answers:
        add(
            "- `answers.md` — decisions the user has already taken on this run's "
            "open questions. These are binding amendments to the task; a finding "
            "that re-opens one of them is wrong before it is written."
        )
    for name in inputs:
        add(
            f"- `{name}` — an input the task names by a `$RUN/…` path you cannot "
            "expand; where it states acceptance criteria it *is* the specification"
        )
    add("")
    add(
        "Read the repository directly — you are running inside it. Nothing about "
        "the plan is authoritative about the code; where the two disagree, the "
        "code is what exists."
    )
    add("")
    add("## The request, verbatim")
    add("")
    add(task.strip() if task.strip() else "_No task text was recorded for this run._")
    add("")

    if scope:
        add("## Files this plan is allowed to change")
        add("")
        add(
            "The union of every workstream's declared file scope. A hook refuses "
            "any write outside this list, so it is a hard boundary and not an "
            "estimate — if the plan's approach needs a file that is not here, "
            "that is itself a finding."
        )
        add("")
        for entry in scope:
            add(f"- `{entry}`")
        add("")
    else:
        add("## Files this plan is allowed to change")
        add("")
        add(
            "_No workstream declared a file scope._ Read the plan's own file "
            "lists instead, and say so in `## Verified for this review` — an "
            "unfenced plan is a weaker thing to review and the reader should know."
        )
        add("")

    add("## What to grade")
    add("")
    for index, axis in enumerate(axes, start=1):
        title, body = AXIS_TEXT[axis]
        add(f"{index}. **{title}.** {body}")
    add("")
    add(
        "Grade only these. Code style, test frameworks and anything that will be "
        "decided while writing the code are out of bounds — there is no code yet, "
        "and a finding about it cannot be acted on at this stage."
    )
    add("")
    add("## Answer in exactly this shape")
    add("")
    add("```")
    add(
        "| # | Severity | Finding | Plan section "
        "| Why it is wrong | How to falsify it |"
    )
    add("|---|---|---|---|---|---|")
    add("")
    add("## Per axis")
    add("<one line per axis above: the axis, then OK or the row numbers against it>")
    add("")
    add("## Verified for this review")
    add("<what you actually read or ran — files, greps, commands. Be specific.>")
    add("```")
    add("")
    add(
        "Severity is **BLOCKER** (an implementer would build the wrong thing), "
        "**MAJOR** (fixable mid-stream but expensive to find later) or **MINOR**. "
        "Use the same words the plan validator uses, so both reviews triage "
        "against one vocabulary."
    )
    add("")
    add(
        "**Every row carries a falsification step.** The plan's author gets to "
        "reject a finding, and can only do that against something checkable — a "
        "row that says \"this seems risky\" with no way to settle it will be "
        "dropped, which wastes the row and the trip. Cite `file:line` wherever "
        "you are making a claim about the existing code."
    )
    add("")
    add(
        "Say nothing about what the plan gets right. The reader of this review is "
        "deciding what to change, and a list of passes is a list they have to "
        "read past to find the three lines that matter."
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("target", nargs="?", default=None, help="run dir, repo, or cwd")
    ap.add_argument(
        "--out", help="package directory (default: <run>/plan-review-package)"
    )
    ap.add_argument("--axes", help="comma-separated subset, overriding the config")
    ap.add_argument("--plan", help="plan file, when the run has none")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--list", action="store_true", help="list recent runs and exit")
    args = ap.parse_args(argv)

    if args.list:
        print(format_recent(20))
        return 0

    run_dir, repo = resolve_target(args.target)

    plan_src = Path(args.plan).expanduser().resolve() if args.plan else None
    if plan_src is None and run_dir is not None:
        plan_src = run_dir / "plan.md"
    if plan_src is None or not plan_src.is_file():
        raise Fail(
            "no plan to review — this run has no plan.md; pass --plan <file>"
        )

    task = ""
    if run_dir is not None and (run_dir / "task.md").is_file():
        task = (run_dir / "task.md").read_text(errors="replace")

    out = Path(args.out).expanduser() if args.out else None
    if out is None:
        if run_dir is None:
            raise Fail("no run directory found; pass --out DIR")
        out = run_dir / "plan-review-package"
    out.mkdir(parents=True, exist_ok=True)
    out = out.resolve()

    shutil.copyfile(plan_src, out / "plan.md")

    answers = user_answers(run_dir)
    if answers:
        (out / "answers.md").write_text(answers, encoding="utf-8")

    inputs: list[str] = []
    for src in referenced_inputs(run_dir, task):
        shutil.copyfile(src, out / src.name)
        inputs.append(src.name)

    axes = resolve_axes(repo, args.axes)
    scope = scope_union(run_dir)
    prompt_path = (out / "PROMPT.md").resolve()
    prompt_path.write_text(
        build_prompt(repo, task, axes, scope, inputs, bool(answers), out),
        encoding="utf-8",
    )

    if args.quiet:
        print(out)
        return 0

    print(f"run dir : {run_dir or '(none)'}")
    print(f"repo    : {repo}")
    print(f"plan    : {plan_src}")
    print(f"axes    : {', '.join(axes)}")
    print(f"scope   : {len(scope)} file(s) across the round-1 briefs")
    if not scope:
        print("WARNING: no brief declared a ```scope fence — the reviewer gets the")
        print("         plan's own file lists instead, which nothing enforces.")
    if inputs:
        print(f"inputs  : {', '.join(inputs)}")
    print()
    print(f"package : {out}")
    for name in sorted(p.name for p in out.iterdir()):
        print(f"          {name}  ({(out / name).stat().st_size} bytes)")
    print()
    print(f"Follow instructions to review the plan @{prompt_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Fail as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
