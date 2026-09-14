#!/usr/bin/env python3
"""Print where a $RUN sits in the coordination loop, and the one next action.

    python3 $SKILL/scripts/run_state.py $RUN

Every phase leaves a file behind, so the file set *is* the state. A coordinator
that lost its context — new session, or a compaction mid-run — does not have to
reconstruct the run from a transcript it no longer has; it reads the directory.
Runs have stalled mid-loop with every artifact on disk and nothing driving the
next spawn, and that is the failure this exists to make impossible.

One thing files cannot tell you: whether an agent is still running. On resume it
never is — a subagent dies with the session that spawned it — so an expected file
that is absent means "spawn it again", not "keep waiting". The `next:` line is
written that way deliberately. Within a live session, prefer `wait_for.py`.

Exit codes, so a resume is one command and a branch:
  0  the coordinator can take the next action alone
  1  the next action needs the user: an unanswered relay, a blocked or partial
     implementer, a CANNOT_RUN verifier, the rework cap, or an ADR conflict
  2  $RUN is not a usable run directory
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import paths
# routing_line already solves "which line of this file is the verdict", including
# the search-from-the-end rule that keeps a quoted spec excerpt from outranking the
# real one. Reimplementing it here would be the duplication this skill tells
# implementers not to write.
from wait_for import ROUTING, routing_line

AXES = ("code", "security", "perf")
WS_HEADING = re.compile(r"^##\s+WS-(\d+)\b", re.M)


def rework_cap(run: Path) -> int:
    """How many rework rounds a workstream gets before triage must STOP.

    Configurable because the right number is empirical, not a principle. Too low
    and a coder one row from done is escalated to the user; too high and an
    ambiguous spec buys another full round of reviewers to say the same thing.
    `paths.setting` owns the tiers and the fallbacks: the repo's own
    `.teamlead.json`, then the global config, then the default.

    Every failure returns the default — no repo.txt, a repo that has since moved,
    unreadable JSON, a value that is not a positive int. A cap is a stopping rule,
    and a stopping rule that raises is worse than one that is merely not the
    number you configured.
    """
    try:
        repo = Path((run / "repo.txt").read_text().strip())
    except OSError:
        repo = None
    return paths.setting("reworkCap", repo, valid=paths.positive_int)


def verdict(path: Path) -> str:
    """The routing token of a phase file — PASS, PLAN_VALID, DONE, APPROVED — or "".

    `routing_line` falls back to the file's first non-heading line when it finds no
    routing keyword, which is the right answer for a human reading output but the
    wrong one to route on: real runs *do* ship reports with the fenced block
    missing, and the fallback then hands back a sentence of prose whose first word
    reads exactly like a verdict. So re-check the match and return "" instead. An
    unreadable verdict has to stay distinguishable from a good one.
    """
    line = routing_line(path)
    if not line or not ROUTING.match(line):
        return ""
    _, sep, rest = line.partition(":")
    tail = (rest if sep else line).strip().strip("*`").strip()
    return tail.split()[0].upper() if tail else ""


RE_REVIEW = re.compile(r"^##\s+Re-review set\s*$(.*?)(?=^##\s|\Z)",
                       re.M | re.S)
AXIS_CARRIED = re.compile(r"^(code|security|perf)\s*:\s*carried\b", re.M)


def carried_axes(triage: str) -> tuple[str, ...]:
    """The axes a triage file records as carried forward instead of re-run.

    Detecting `carried` rather than `re-run` is deliberate, and it is the same
    asymmetry `roles/triage.md` states for triage itself: unsure means re-run,
    because a wrong "carried" costs a missed defect while a wrong "re-run" costs
    a few minutes. So only an explicit `carried` narrows the expected set, and
    everything else — a missing section, a malformed line, prose the template did
    not anticipate — leaves the axis expected. Real runs need that: one recorded
    basis line reads `perf: sanity pass again for WS-2 — …`, which means re-run
    and matches neither keyword; keying on `re-run` would have dropped it.
    """
    section = RE_REVIEW.search(triage)
    return tuple(AXIS_CARRIED.findall(section.group(1))) if section else ()


def first(*paths: Path) -> Path | None:
    """The first of several spellings that exists.

    Verifier, review and triage files carry a `ws<N>-` segment only when the run
    has more than one workstream, and a resumed coordinator does not always know
    which case it is in before it has read the plan.
    """
    return next((p for p in paths if p.exists()), None)


class Run:
    def __init__(self, run: Path) -> None:
        self.run = run
        self.roster = self._roster()
        self.multi = len(self.roster) > 1
        self.cap = rework_cap(run)

    def text(self, name: str) -> str:
        p = self.run / name
        return p.read_text(errors="replace") if p.exists() else ""

    def _roster(self) -> list[int]:
        found = {int(n) for n in WS_HEADING.findall(self.text("plan.md"))}
        if not found:
            found = {int(m.group(1)) for f in (self.run / "briefs").glob("impl-ws*.md")
                     if (m := re.match(r"impl-ws(\d+)-r\d+\.md$", f.name))}
        return sorted(found) or [1]

    def axes(self, ws: int = 0, rnd: int = 1) -> tuple[str, ...]:
        """Which reviewers this round is meant to produce.

        Round 1 is the run-wide set: code always, the specialists unless a flag
        turned them off. A REWORK round is deliberately narrower — code plus only
        the specialists the previous triage put in its re-review set — so scoring
        it against the run-wide set demands agents the coordinator was right not
        to spawn, which is how a finished stream ends up looking unfinished.

        The set is read from the previous triage file's `## Re-review set` section
        (`roles/triage.md:70`), not from the `rereview=` field. That field belongs
        to triage's *return* line, which is spoken to the coordinator and never
        written to disk — so a resumed session has lost it, which is the one thing
        this script may not depend on. Across the 23 recorded triage files the
        section is present every time and the field not once.

        Only an explicit `carried` narrows the set; see `carried_axes` for why
        that direction and not the other. Code is never subtracted — it is the
        one axis `triage.md` says always re-runs.
        """
        flags = next((ln for ln in self.text("task.md").splitlines()
                      if ln.startswith("flags:")), "")
        allowed = tuple(a for a in AXES
                        if a == "code" or f"--no-{a}-review" not in flags)
        if rnd < 2 or not ws:
            return allowed
        prev = self.phase_file("triage", ws, rnd - 1)
        carried = carried_axes(prev.read_text(errors="replace")) if prev else ()
        return tuple(a for a in allowed if a == "code" or a not in carried)

    def brief(self, ws: int, rnd: int) -> Path:
        return self.run / "briefs" / f"impl-ws{ws}-r{rnd}.md"

    def report(self, ws: int, rnd: int) -> Path | None:
        return first(self.run / f"implementer-ws{ws}-r{rnd}.md",
                     self.run / f"implementer-r{rnd}.md")

    def phase_file(self, kind: str, ws: int, rnd: int, tail: str = "") -> Path | None:
        return first(self.run / f"{kind}-ws{ws}-r{rnd}{tail}.md",
                     self.run / f"{kind}-r{rnd}{tail}.md")

    def round_of(self, ws: int) -> int:
        """The highest round with a brief — the round actually in play."""
        rounds = [r for r in range(1, 12) if self.brief(ws, r).exists()]
        return rounds[-1] if rounds else 1


def stream_line(r: Run, ws: int) -> str:
    """One human-readable line per workstream: how far this round got."""
    rnd = r.round_of(ws)
    parts: list[str] = []
    if not r.brief(ws, rnd).exists():
        parts.append("no brief")
    def cell(label: str, path: Path | None) -> str:
        if path is None:
            return f"{label} —"
        # "(no routing line)" is not a cosmetic detail: it is the difference
        # between a phase that reported and one whose report cannot be routed.
        return f"{label} {verdict(path) or '(no routing line)'}"

    parts.append(cell("impl", r.report(ws, rnd)))
    parts.append(cell("verify", r.phase_file("verifier", ws, rnd)))
    done = [a for a in r.axes(ws, rnd) if r.phase_file("review", ws, rnd, f"-{a}")]
    parts.append("review " + ("+".join(done) if done else "—"))
    parts.append(cell("triage", r.phase_file("triage", ws, rnd)))
    return f"WS-{ws} r{rnd}: " + " · ".join(parts)


def stream_next(r: Run, ws: int) -> tuple[int, str, str, bool] | None:
    """(step, label, action, needs_user) for this stream, or None once approved."""
    rnd = r.round_of(ws)
    tag = f"ws{ws}-r{rnd}" if r.multi else f"r{rnd}"
    if not r.brief(ws, rnd).exists():
        return (10, "rework brief missing", f"write briefs/impl-ws{ws}-r{rnd}.md "
                "(rows merged, per references/roles/triage.md), then brief I", False)

    rep = r.report(ws, rnd)
    if rep is None:
        return (7, "implementer not reported", "spawn a FRESH sonnet implementer "
                f"(brief I, WS-{ws} round {rnd}); its brief is already written",
                False)
    st = verdict(rep)
    if st in ("BLOCKED", "PARTIAL"):
        return (8, f"implementer {st.lower()}", f"read {rep.name} — its one "
                "question is yours to resolve, with the user if the spec is what "
                "is unclear", True)

    ver = r.phase_file("verifier", ws, rnd)
    if ver is None:
        return (8, "verifier not run",
                f"spawn the sonnet VERIFIER (brief G, {tag})", False)
    # Everything between "the verifier ran" and "triage is written" only matters
    # while triage is absent. A triage file is downstream evidence that the whole
    # middle of the round closed — the coordinator wrote it after reading the
    # verifier and the reviews — so it settles those phases whatever their files
    # look like. Both halves of that are load-bearing on real runs: one recorded
    # run carries `OUTCOME: FAIL` with `touched: no`, was correctly reviewed
    # anyway and triaged APPROVED_WITH_NOTES, and re-asking about the FAIL sends
    # a resumed coordinator to re-adjudicate a decision already made; and asking
    # about missing reviews first re-spawns reviewers whose findings triage has
    # already consolidated.
    tri = r.phase_file("triage", ws, rnd)
    if tri is None:
        out = verdict(ver)
        if out == "CANNOT_RUN":
            return (8, "verifier CANNOT_RUN", "environment problem, not a code "
                    f"failure: fix the command in the brief or ask the user — see "
                    f"{ver.name}", True)
        if out == "FAIL":
            # touched=yes/no lives in the verifier's body; deciding it is judgement.
            return (8, "verifier FAIL", f"read {ver.name}: every failure touched=no "
                    f"is pre-existing → report and review anyway; otherwise write "
                    f"briefs/impl-ws{ws}-r{rnd + 1}.md and rerun the round", False)
        missing = [a for a in r.axes(ws, rnd)
                   if not r.phase_file("review", ws, rnd, f"-{a}")]
        if missing:
            return (9, "reviews outstanding", "spawn the reviewers in ONE turn "
                    f"({', '.join(missing)}) with this stream's axis tags "
                    f"(brief R, {tag})", False)
        return (10, "triage not written", f"you write {r.run.name}/triage-{tag}.md "
                f"following references/roles/triage.md", False)
    tv = verdict(tri)
    if not tv:
        return (10, "triage verdict unreadable", f"read {tri.name} — it has no "
                "`VERDICT:` line, so nothing can route on it; decide the verdict "
                "yourself and append the line before going on", False)
    if tv == "NEEDS_REWORK":
        if rnd > r.cap:
            return (10, "rework cap reached", f"STOP and take it to the user: round "
                    f"{rnd} still needs rework past a cap of {r.cap}, so the plan or "
                    f"the spec is wrong, not the coder", True)
        return (10, "rework round due", f"write briefs/impl-ws{ws}-r{rnd + 1}.md "
                f"(spec-growth rows demoted to Notes), then a FRESH implementer — "
                f"never a SendMessage resume", False)
    if tv == "STOP":
        return (10, "triage says STOP",
                f"read {tri.name} and take it to the user", True)
    return None


def scope_cut(r: Run) -> str:
    """The validator's `Smaller:` line when it names a cut, else "".

    `none — already minimal …` is the common answer and is not a decision, so it
    must not turn the relay into a choice the user has to make.
    """
    line = next((ln for ln in r.text("plan-validation.md").splitlines()
                 if ln.startswith("Smaller:")), "")
    body = line[8:].strip()
    return "" if body.lower().startswith("none") else body


def plan_next(r: Run) -> tuple[int, str, str, bool] | None:
    """The pre-dispatch half of the loop: steps 3 to 6a."""
    if not (r.run / "task.md").exists():
        return (3, "kickoff incomplete", "write $RUN/task.md: the task verbatim, flags "
                "stripped, plus its `flags:` line", False)
    if not (r.run / "questions.md").exists():
        return (4, "plan not on disk", "spawn the opus PLANNER (brief P) — "
                "questions.md is written last, so its absence means the plan is "
                "not finished", False)
    q = r.text("questions.md")
    if "adr_conflict=yes" in q and "## Answers" not in q:
        return (5, "ADR conflict", "HALT per references/adr-workflow.md: name the ADR "
                "and clause and ask the user. Do not dispatch", True)
    if not (r.run / "plan-validation.md").exists():
        return (4, "plan unvalidated", "spawn the opus PLAN VALIDATOR (brief V)", False)
    pv = verdict(r.run / "plan-validation.md")
    if pv == "PLAN_NEEDS_FIX" and "## Fix log" not in r.text("plan.md"):
        return (5, "plan needs fixing", "spawn a fresh opus planner in Fix mode "
                "(brief F), then wait with --rewritten $RUN/plan.md "
                "--expect $RUN/plan.md PLAN_FIXED", False)
    cut = scope_cut(r)
    # A relay with nothing in it to answer often leaves no `## Answers` behind: step 6
    # sends the go line and continues in the same turn, so there is nothing to append.
    # Three of ten recorded runs look exactly like this, and reading them as "the user
    # has not replied yet" would park a resume on a decision point that never existed.
    # A scope cut is a real decision, so it still holds even with no questions.
    nothing_asked = "No open questions." in q and not cut
    if "## Answers" not in q and not nothing_asked:
        scope = f"the scope selection ({cut}) FIRST, " if cut else ""
        return (6, "user relay outstanding", "send the ONE relay turn: plan summary "
                "and validator verdict as text, then ONE AskUserQuestion call — "
                f"{scope}then one card per question in questions.md, options "
                "labelled with their own words", True)
    # A cut the user accepted and nobody applied is the exact failure the selection
    # exists to prevent, and it is derivable: Fix mode logs `scope: chose …` into
    # plan.md, so an accepted letter with no such line means the round never ran.
    chosen = next((ln for ln in q.splitlines() if ln.startswith("scope:")), "")
    if chosen and not chosen[7:].lstrip().startswith("A") \
            and "scope: chose" not in r.text("plan.md"):
        return (6, "accepted scope cut not applied", "spawn a fresh opus planner in "
                f"Fix mode (brief F) with `Scope decision: {chosen[7:].strip()}`, "
                "then wait with --rewritten $RUN/plan.md "
                "--expect $RUN/plan.md PLAN_FIXED", False)
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    run = Path(argv[1]).expanduser()
    if not (run / "repo.txt").exists():
        print(f"{run} is not a run directory (no repo.txt)")
        return 2

    r = Run(run)
    print(f"RUN={run}")
    print(f"repo={(run / 'repo.txt').read_text().strip()}")

    if (run / "final-report.md").exists():
        print("step: 11 — final report written; the loop is complete")
        print("next: send $RUN/final-report.md to the user if you have not already")
        return 0

    state = plan_next(r)
    if state is None:
        for ws in r.roster:
            print(stream_line(r, ws))
        # Wave order matters, but a stream's own gap is what a resume acts on, so
        # take the lowest-numbered stream that is not finished and act there.
        pending = [s for ws in r.roster if (s := stream_next(r, ws))]
        if not pending:
            print("step: 11 — every workstream approved")
            print("next: spawn the sonnet LEDGER WRITER (brief L) if any row was "
                  "demoted or deferred, then write $RUN/final-report.md")
            return 0
        state = pending[0]

    step, label, action, needs_user = state
    print(f"step: {step} — {label}")
    print(f"next: {action}")
    return 1 if needs_user else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
