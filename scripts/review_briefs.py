#!/usr/bin/env python3
"""Write one round's reviewer briefs (brief R) and print how to dispatch each.

    python3 $PLUGIN/scripts/review_briefs.py $RUN --ws 1 --round 1 \
        --tags input=no,hot=no,public=yes --commits "abc123 def456"

Brief R is a template plus four facts: the axis, the round, the tag and the
commits. The coordinator used to type it once per reviewer, restating duties
that `roles/reviewer.md` already carries and copying the settled decisions into
each copy; in measured runs the review-dispatch turn was the largest single
output turn of the run. The settled decisions are now written once, to the file
named by `--settled`, and copied verbatim into every brief here.

The axis set and the setting/tag table are step 9's: code always runs in full;
a specialist runs in full on tag=yes, as a sonnet sanity pass on tag=no with
setting `on`, and not at all on `off` or `when-needed` + no. The setting is
the resolved option in config.json, not the task's `--no-*` flag: the options
card can turn a flagged-off reviewer back on. A rework round also drops the
specialists the previous triage carried. Every skip leaves a `.skip` record
beside the briefs so run_state's completion check stops expecting that report.

Prints one line per axis:
  <axis> full|sanity type=<subagent type> model=<opus|sonnet> brief=<abs path>
  <axis> skip reason=<why>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import paths
from run_state import AXES, SETTING_OF, Run, carried_axes

TAG_OF = {"code": "public", "security": "input", "perf": "hot"}
TYPE_OF = {
    "code": "code-review",
    "security": "security-review (general-purpose if unregistered)",
    "perf": "performance-engineer",
}
TOOLS = (
    "Tools: Read, Grep, Glob, Bash, Write. Write only the report. Bash permits "
    "code-probe clone creation, temporary edits, and restoration under $RUN. "
    "Follow the role's isolation procedure. Never edit the shared repo. "
    "No commits, Skill tool, or agents."
)


def parse_tags(raw: str) -> dict[str, str]:
    tags = dict(part.split("=", 1) for part in raw.split(",") if "=" in part)
    for axis, tag in TAG_OF.items():
        if tags.get(tag) not in ("yes", "no"):
            raise ValueError(f"--tags needs {tag}=yes|no for the {axis} axis")
    return tags


def mode(axis: str, setting: str, tag: str) -> str:
    """full, sanity or skip — the step 9 table."""
    if axis == "code":
        return "full"
    if setting == "off":
        return "skip"
    if tag == "yes":
        return "full"
    return "sanity" if setting == "on" else "skip"


def ws_name(run: Run, ws: int) -> str:
    heading = re.compile(rf"^##\s+WS-{ws}\b\s*[—:-]*\s*(.*)$", re.M)
    m = heading.search(run.text("plan.md"))
    return m.group(1).strip() if m and m.group(1).strip() else f"WS-{ws}"


def brief(run: Run, ws: int, rnd: int, axis: str, how: str, tag: str,
          commits: str, settled: str) -> str:
    root = paths.plugin_root()
    infix = f"ws{ws}-" if run.multi else ""
    infix_line = (
        "Several workstreams share this run: use the ws<N>- infix." if run.multi
        else "One workstream in this run: no ws<N>- infix."
    )
    lines = [
        f"Role: read and follow {root}/references/roles/reviewer.md. "
        f"$RUN = {run.run}. Repo: {run.text('repo.txt').strip()}.",
        f"Axis: {axis}. Workstream: WS-{ws} ({ws_name(run, ws)}). Round: {rnd}. "
        f"{infix_line}",
        f"Inputs: $RUN/plan.md ## WS-{ws}, $RUN/briefs/impl-ws{ws}-r{rnd}.md, "
        f"$RUN/implementer-ws{ws}-r{rnd}.md, $RUN/verifier-{infix}r{rnd}.md, "
        "$RUN/task.md, CLAUDE.md.",
        f"Review standard: {root}/references/review-standard.md. "
        f"Commits: {commits}.",
        f"Tag: {TAG_OF[axis]}={tag}. Use the validator's final tag and the "
        "plan's reason.",
    ]
    if how == "sanity":
        lines.append("This is a specialist sanity pass: use the review standard's "
                     "sanity-pass shape.")
    lines.append("Settled decisions (verbatim; check factual justifications "
                 "against code):")
    lines.append(settled.strip() or "none")
    if rnd > 1:
        lines.append(
            f"Rework: previous rows are in $RUN/triage-{infix}r{rnd - 1}.md. "
            f"Rework commits: {commits}. Check only those rows and changed lines. "
            "Test-only rework replaces probes with assertion-removal review."
        )
    lines.append(f"Output: $RUN/review-{infix}r{rnd}-{axis}.md following the "
                 "review standard. Return VERDICT and file line.")
    lines.append(TOOLS)
    return "\n".join(lines) + "\n"


def write_briefs(run_dir: Path, ws: int, rnd: int, tags: dict[str, str],
                 commits: str, settled: str) -> list[str]:
    run = Run(run_dir.resolve())
    if not (run.run / "repo.txt").is_file():
        raise ValueError(f"{run_dir} has no repo.txt, so it is not a run directory")
    prev = run.phase_file("triage", ws, rnd - 1) if rnd > 1 else None
    carried = carried_axes(prev.read_text(errors="replace")) if prev else ()
    infix = f"ws{ws}-" if run.multi else ""
    out: list[str] = []
    for axis in AXES:
        tag = tags[TAG_OF[axis]]
        skip = run.skip_record(ws, rnd, axis)
        setting = run.setting(axis)
        how = mode(axis, setting, tag)
        reason = ""
        if axis != "code" and axis in carried:
            reason = f"carried by triage round {rnd - 1}"
        elif how == "skip":
            reason = f"{SETTING_OF[axis]}={setting}, {TAG_OF[axis]}={tag}"
        if reason:
            skip.parent.mkdir(exist_ok=True)
            skip.write_text(reason + "\n")
            out.append(f"{axis} skip reason={reason}")
            continue
        skip.unlink(missing_ok=True)
        path = run.run / "briefs" / f"review-{infix}r{rnd}-{axis}.md"
        path.parent.mkdir(exist_ok=True)
        path.write_text(brief(run, ws, rnd, axis, how, tag, commits, settled))
        model = "opus" if how == "full" else "sonnet"
        out.append(f"{axis} {how} type={TYPE_OF[axis]} model={model} brief={path}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run", type=Path)
    parser.add_argument("--ws", type=int, required=True)
    parser.add_argument("--round", type=int, required=True, dest="rnd")
    parser.add_argument("--tags", required=True,
                        help="input=yes|no,hot=yes|no,public=yes|no")
    parser.add_argument("--commits", required=True,
                        help="space-separated hashes for this round")
    parser.add_argument("--settled", type=Path,
                        help="file holding the settled decisions, verbatim")
    args = parser.parse_args()
    try:
        settled = args.settled.read_text() if args.settled else ""
        lines = write_briefs(args.run, args.ws, args.rnd, parse_tags(args.tags),
                             args.commits, settled)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, f"Cannot write reviewer briefs: {exc}\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
