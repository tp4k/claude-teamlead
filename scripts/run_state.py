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
from typing import cast

import paths
import run_config
# routing_line already solves "which line of this file is the verdict", including
# the search-from-the-end rule that keeps a quoted spec excerpt from outranking the
# real one. Reimplementing it here would be the duplication this skill tells
# implementers not to write.
from wait_for import ROUTING, routing_line

AXES = ("code", "security", "perf")
SETTING_OF = {"security": "securityReview", "perf": "perfReview"}
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
    # `valid` only lets a positive int through, and the default is one too.
    return cast(int, paths.setting("reworkCap", repo, valid=paths.positive_int))


def cap_reached(rnd: int, cap: int) -> bool:
    """Whether a NEEDS_REWORK after round `rnd` is one rework too many.

    `reworkCap` counts reworks, not rounds: cap 3 allows rework rounds 2 to 4, so
    round 4 is spawned and a NEEDS_REWORK after it stops for the user. Gate-driven
    and ordinary rework add to the same count because both create the next round.
    """
    return rnd > cap


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
        allowed = tuple(a for a in AXES if a == "code" or (
            self.setting(a) != "off"
            and not (ws and self.skip_record(ws, rnd, a).exists())))
        if rnd < 2 or not ws:
            return allowed
        carried = self.carried(ws, rnd)
        return tuple(a for a in allowed if a == "code" or a not in carried)

    def carried(self, ws: int, rnd: int) -> tuple[str, ...]:
        """The axes the previous round's triage carried forward, if any.

        review_briefs.py skips exactly these, and `axes` stops expecting them, so
        both read the one function: a disagreement is a resumed run waiting for a
        report nobody was asked to write.
        """
        prev = self.phase_file("triage", ws, rnd - 1) if rnd > 1 else None
        return carried_axes(prev.read_text(errors="replace")) if prev else ()

    def setting(self, axis: str) -> str:
        """on, when-needed or off for one reviewer axis.

        The resolved option in config.json wins over the task's `--no-*` flag,
        because the options card can turn a flagged-off reviewer back on; the
        flag decides only when no option was recorded. review_briefs.py and the
        completion check must agree on this, or a resumed run waits for a
        report nobody was asked to write.
        """
        if axis == "code":
            return "on"
        option = paths.read_json(self.run / "config.json").get("options", {})
        flags = next((ln for ln in self.text("task.md").splitlines()
                      if ln.startswith("flags:")), "")
        flagged = "off" if f"--no-{axis}-review" in flags else "on"
        return str(option.get(SETTING_OF[axis], flagged))

    def skip_record(self, ws: int, rnd: int, axis: str) -> Path:
        """Where review_briefs.py records a reviewer it decided not to dispatch.

        `when-needed` + tag=no skips on the validator's tag, which lives in no
        run file; without this record a resumed run cannot tell a skipped
        reviewer from an outstanding one.
        """
        return self.run / "briefs" / f"review-{self.tag(ws, rnd)}-{axis}.skip"

    def infix(self, ws: int) -> str:
        """`ws<N>-` when several workstreams share the run, else nothing."""
        return f"ws{ws}-" if self.multi else ""

    def tag(self, ws: int, rnd: int) -> str:
        """`ws<N>-r<M>` or `r<M>`: the suffix every per-round file carries."""
        return f"{self.infix(ws)}r{rnd}"

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
    tag = r.tag(ws, rnd)
    if not r.brief(ws, rnd).exists():
        return (10, "rework brief missing", f"re-dispatch teamlead:triage (brief T, "
                f"round {rnd - 1}) to write briefs/impl-ws{ws}-r{rnd}.md, then brief I",
                False)

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
            return (9, "reviews outstanding", "run review_briefs.py, then spawn "
                    f"the reviewers in ONE turn ({', '.join(missing)}) from its "
                    f"lines (brief R, {tag})", False)
        return (10, "triage not written", "spawn teamlead:triage (brief T, "
                f"{tag}) to write triage-{tag}.md", False)
    tv = verdict(tri)
    if not tv:
        return (10, "triage verdict unreadable", f"read {tri.name} — it has no "
                "`VERDICT:` line, so nothing can route on it; decide the verdict "
                "yourself and append the line before going on", False)
    if tv == "NEEDS_REWORK":
        if cap_reached(rnd, r.cap):
            return (10, "rework cap reached", f"STOP and take it to the user: round "
                    f"{rnd} still needs rework past a cap of {r.cap}, so the plan or "
                    f"the spec is wrong, not the coder", True)
        return (10, "rework round due", f"briefs/impl-ws{ws}-r{rnd + 1}.md is "
                f"missing: re-dispatch teamlead:triage (brief T, {tag}) to write it, "
                f"then a FRESH implementer — never a SendMessage resume", False)
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


PLAN_REVIEW_DIR = "plan-review-package"
PLAN_REVIEW_STEM = "plan-review"  # run_codex_review.py --artifact-stem
# The two options a /teamlead:cycle run appends to every task. Compared by value,
# so a user's own `--with-human-readable-plan=pause` in a cycle still counts.
CYCLE_OPTIONS = ("codexPlanReview", "humanReadablePlan")


def options(r: Run) -> dict:
    """`config.json`'s resolved options — `{}` when absent or unreadable."""
    opts = paths.read_json(r.run / "config.json").get("options")
    return opts if isinstance(opts, dict) else {}


def cycle_task_file(r: Run) -> Path | None:
    """The /teamlead:cycle task file that launched this run, if one did.

    Matched on its `worktree:` line against repo.txt rather than on the slug:
    kickoff may suffix a slug on collision, and the worktree is the very path
    the run was handed. The worktree alone is not enough, though: the cycle's
    last step hands over `/teamlead:delegate <run>/review-followup.md` in the
    same tree, so the task file's body must also be in this run's task.md —
    the cycle passes that text on verbatim. Its `flags:` line is not required
    there, since losing it is exactly what cycle_gap looks for.
    """
    repo = r.text("repo.txt").strip()
    task = r.text("task.md")
    if not repo:
        return None
    try:
        files = sorted(paths.tasks_dir().glob("*.md"))
    except OSError:
        return None
    for f in files:
        try:
            head, _, body = f.read_text(errors="replace").partition("\n# Task")
        except OSError:
            continue
        body = body.strip()
        if f"\nworktree: {repo}\n" in f"\n{head}\n" and body and body in task:
            return f
    return None


def cycle_gap(r: Run) -> tuple[int | str, str, str, bool] | None:
    """A cycle run whose own two options never reached config.json.

    The cycle appends `--codex-plan-review=always --with-human-readable-plan=
    generate` to the task it hands on, so that its plan review cannot quietly
    be off. Two places can drop them: the task file's `flags:` line, and the
    text the coordinator passes to run_config.py. Either way config.json ends up
    holding a config-file or built-in value, which reads like a deliberate
    setting and not like a lost one. An options-card answer is the user's later
    word on the same question, so it always stands.
    """
    task_file = cycle_task_file(r)
    if task_file is None:
        return None
    raw = paths.read_json(r.run / "config.json").get("sources")
    sources = raw if isinstance(raw, dict) else {}
    # Only what the card left unanswered still hangs on the flags line.
    pending = [k for k in CYCLE_OPTIONS if sources.get(k) != "options card"]
    if not pending:
        return None
    flags_line = next((ln[6:].strip() for ln in task_file.read_text(
        errors="replace").splitlines() if ln.startswith("flags:")), "")
    try:
        wanted, _ = run_config.parse_flags(flags_line)
    except run_config.Fail:
        wanted = {}
    if any(k not in wanted for k in pending):
        return ("3a", "cycle options lost", f"{task_file} has `flags: "
                f"{flags_line or 'none'}`, but a /teamlead:cycle task file always "
                "carries --codex-plan-review=always --with-human-readable-plan="
                "generate (plus any flag the user typed). Fix that line, re-run "
                "run_config.py with it and the task text, then show the options "
                "card", False)
    opts = options(r)
    off = [k for k in pending if opts.get(k) != wanted[k]]
    if off:
        got = ", ".join(f"{k}={opts.get(k)!r} from {sources.get(k, '?')}"
                        for k in off)
        return ("3a", "cycle options not in config.json", f"config.json has {got}, "
                f"but the cycle's task file asks for `{flags_line}`: re-run "
                "run_config.py with --flags carrying that line and the task text, "
                "then show the options card", False)
    return None


def design_gap(r: Run) -> tuple[int | str, str, str, bool] | None:
    """Steps 4a and 5: what config.json promised before the plan is validated.

    Only *starting* the Codex review is owed. The skill is explicit that a Codex
    failure, timeout or missing login never blocks dispatch, so an answer is not
    required — what a failure does owe, when that is the setting, is the opus
    fallback. The evidence of a start is the runner's own: PROMPT.md is written
    by plan_review_package.py *before* the runner is called, so it proves only
    the first of the two commands. run_codex_review.py appends to
    `plan-review-attempts.log` before it resolves Codex at all, so even a Codex
    missing from PATH leaves the record; an events or review file counts too.
    """
    opts = options(r)
    codex, opus = opts.get("codexPlanReview"), opts.get("opusPlanReview")
    human = opts.get("humanReadablePlan")
    pkg = r.run / PLAN_REVIEW_DIR
    codex_wanted = codex == "always" or (
        codex == "hard" and "complex=yes" in r.text("questions.md"))
    run_it = (f"run_codex_review.py <abs $RUN/{PLAN_REVIEW_DIR}/PROMPT.md> "
              "--artifact-stem plan-review IN THE BACKGROUND (step 4a). If Codex "
              "fails, say so and go on")
    if codex_wanted and not (pkg / "PROMPT.md").exists():
        return (4, "Codex plan design review never started", f"codexPlanReview="
                f"{codex}: run plan_review_package.py $RUN, then {run_it}", False)
    attempted = pkg.is_dir() and (
        (pkg / f"{PLAN_REVIEW_STEM}-attempts.log").exists()
        or any(pkg.glob(f"{PLAN_REVIEW_STEM}-r*.jsonl"))
        or any(pkg.glob(f"{PLAN_REVIEW_STEM}-r*.md")))
    if codex_wanted and not attempted:
        return (4, "Codex plan review packaged but never launched",
                f"codexPlanReview={codex}: PROMPT.md is there and the runner never "
                f"ran — {run_it}", False)
    answered = sorted(pkg.glob("plan-review-r*.md")) if pkg.is_dir() else []
    opus_file = r.run / "plan-design-review.md"
    if opus == "always" and not opus_file.exists():
        return (4, "opus plan design review missing", "opusPlanReview=always: "
                "spawn teamlead:plan-reviewer (brief D) — step 4a", False)
    if opus == "fallback" and codex_wanted and not answered \
            and not opus_file.exists():
        return (5, "no plan design review answered", "wait for the Codex plan "
                "review if it is still running; if it failed, timed out or had "
                "no login, spawn teamlead:plan-reviewer (brief D, fallback line)",
                False)
    if human in ("generate", "pause") and not (r.run / "plan-human.md").exists():
        return (4, "human-readable plan missing", f"humanReadablePlan={human}: "
                "spawn teamlead:writer for $RUN/plan-human.md (brief H) — step 4a. "
                "If that writer is already running, do not spawn another: wait "
                "with wait_for.py $RUN/plan-human.md", False)
    if (answered or opus_file.exists()) and not (r.run / "plan-triage.md").exists():
        return (5, "plan triage not written", "you write $RUN/plan-triage.md: "
                "every row of every returned design review, verbatim, with its "
                "verdict and evidence (step 5)", False)
    return None


def autopilot(r: Run) -> bool:
    """`--autopilot`: skip the stops that wait on the user (SKILL.md 6, 6d).

    An explicit humanReadablePlan=pause is the one hold it keeps; nothing this
    script models is that hold, so every user stop here is skippable.
    """
    return paths.read_json(r.run / "config.json").get("autopilot") is True


def recommended_labels(q: str) -> dict[str, str]:
    """Question number → its recommended option's label, from questions.md.

    The planner writes each question as `n. …`, its options as `a) <label>`
    lines and the pick as `recommended: <letter>`; the relay shows the label on
    the card, so an answer that repeats it verbatim is the recommendation.
    """
    labels: dict[str, str] = {}
    num, options = "", {}
    for ln in q.partition("## Answers")[0].splitlines():
        if m := re.match(r"(\d+)\.\s", ln):
            num, options = m.group(1), {}
        elif m := re.match(r"\s+([a-z])\)\s+(.+)", ln):
            options[m.group(1)] = m.group(2).strip()
        elif (m := re.match(r"\s+recommended:\s*([a-z])\b", ln)) and num:
            if m.group(1) in options:
                labels[num] = options[m.group(1)]
    return labels


def accepts_recommendation(answer: str, labels: dict[str, str]) -> bool:
    """Whether one `## Answers` line records the recommended option.

    6a allows `n. recommendation accepted` and `n. <chosen option, verbatim>`,
    and coordinators routinely add the option's label or a note after the
    first — `1. recommendation accepted — close the channel at once (…)`. An
    end-of-line match read that as a changed answer and blocked a real run's
    validator at 6b, so the phrase is matched at the start of the answer.
    A repeated label is compared exactly: options may differ only in case or
    punctuation (`emit OK` / `emit ok`), and folding them would let the other
    one through as the recommendation.
    """
    num, _, body = answer.partition(".")
    body = body.strip()
    if re.match(r"recommendation accepted\b", body.lower()):
        return True
    return num in labels and body == labels[num]


def fold_owed(r: Run, q: str) -> str:
    """Why step 6b's planner Fix round is owed and has not run, else "".

    Only what the skill makes certain counts, since a gate that guesses blocks
    real runs: any CONFIRMED design row is always folded, and so is an answer
    other than an accepted recommendation — the one answer that may restate the
    plan and need no round. Every Fix round appends `## Fix log`, and before the
    validator has run, none other can have.
    """
    if "## Fix log" in r.text("plan.md"):
        return ""
    counts = re.findall(r"CONFIRMED\s+(\d+)\s*·", r.text("plan-triage.md"))
    confirmed = int(counts[-1]) if counts else 0
    owed = [f"{confirmed} CONFIRMED design row(s)"] if confirmed else []
    labels = recommended_labels(q)
    answers = q.partition("## Answers")[2]
    for ln in (raw.strip() for raw in answers.splitlines()):
        if ln.startswith("design:") and not ln.lower().endswith(
                "recommendation accepted"):
            owed.append(ln)
        elif re.match(r"\d+\.\s", ln) and not accepts_recommendation(ln, labels):
            owed.append(ln)
    return "; ".join(owed)


def validator_fix_applied(r: Run) -> bool:
    """Whether plan.md carries a Fix round for the validator's findings.

    `## Fix log` alone cannot say so: the 6b design round writes one before the
    validator runs, and a 6c round appends to the same section with the same
    PLAN_FIXED line. What tells them apart is order — only a round that ran
    after plan-validation.md was written can have answered it.
    """
    plan, pv = r.run / "plan.md", r.run / "plan-validation.md"
    try:
        newer = plan.stat().st_mtime_ns > pv.stat().st_mtime_ns
    except OSError:
        return False
    return newer and "## Fix log" in r.text("plan.md")


def plan_written_gap(r: Run) -> tuple[int | str, str, str, bool] | None:
    """Steps 3 and 4: what has to exist before anything can read the plan.

    This is all the plan validator needs. It runs at step 4a, beside the design
    review and ahead of the relay, so that the scope cut it may name joins the
    single step-6 batch instead of costing a second round trip to the user.
    """
    if not (r.run / "task.md").exists():
        return (3, "kickoff incomplete", "write $RUN/task.md: the task verbatim, flags "
                "stripped, plus its `flags:` line", False)
    if not (r.run / "config.json").exists():
        return ("3a", "run options never resolved", "python3 $PLUGIN/scripts/"
                "run_config.py <repo> --flags \"<the task text, verbatim>\" --out "
                "$RUN/config.json, then the options card it asks for. Every later "
                "step reads config.json; without it no plan review is owed, so "
                "none happens", False)
    gap = cycle_gap(r)
    if gap:
        return gap
    if not (r.run / "questions.md").exists():
        return (4, "plan not on disk", "spawn the opus PLANNER (brief P) — "
                "questions.md is written last, so its absence means the plan is "
                "not finished", False)
    return None


def relay_owed(r: Run, q: str, ask_cut: bool = True) -> str:
    """What the step-6 relay still has to ask: questions and/or the scope cut.

    A relay with nothing in it to answer often leaves no `## Answers` behind: step 6
    sends the go line and continues in the same turn, so there is nothing to append.
    Three of ten recorded runs look exactly like this, and reading them as "the user
    has not replied yet" would park a resume on a decision point that never existed.
    The validator's `Smaller:` cut is now known before the relay, so it is asked in
    the same batch; a cut is a real decision, so it holds even with no questions.
    """
    owed = []
    if "## Answers" not in q and "No open questions." not in q:
        owed.append("one card per CONFIRMED design choice, then one per question "
                    "in questions.md")
    cut = scope_cut(r) if ask_cut else ""
    chosen = next((ln for ln in q.splitlines() if ln.startswith("scope:")), "")
    if cut and not chosen:
        owed.append(f"the scope selection ({cut}): one option per A)/B)/C) line, "
                    "its `scope:` line appended to questions.md's ## Answers")
    return "; and ".join(owed)


def last_fix_added_paths(r: Run) -> bool:
    """Whether the last `PLAN_FIXED` line of plan.md says `new_paths=yes`."""
    fixed = [ln for ln in r.text("plan.md").splitlines()
             if ln.strip().startswith("PLAN_FIXED")]
    return bool(fixed) and "new_paths=yes" in fixed[-1]


def pass_two_cut(r: Run) -> str:
    """The `Smaller:` cut a validator pass 2 named, else "".

    Pass 2 is the validation written after a Fix round that added paths, so it
    is newer than plan.md and plan.md's last Fix round said `new_paths=yes`.
    """
    plan, pv = r.run / "plan.md", r.run / "plan-validation.md"
    try:
        if pv.stat().st_mtime_ns <= plan.stat().st_mtime_ns:
            return ""
    except OSError:
        return ""
    return scope_cut(r) if last_fix_added_paths(r) else ""


def log_cut(r: Run, cut: str) -> None:
    """Append a pass-2 scope cut to decisions-log.md, once."""
    log = r.run / "decisions-log.md"
    row = f"- plan-validation.md (pass 2): scope cut named, not asked — {cut}"
    existing = log.read_text(errors="replace") if log.exists() else ""
    if row not in existing:
        head = existing if existing else "# Decisions log\n\n"
        log.write_text(head.rstrip("\n") + "\n" + row + "\n")


def pass_two_owed(r: Run) -> bool:
    """Whether the validator's second pass is due: the Fix round added paths.

    Pass 2 re-checks facts on the fixed plan only, and only the paths that round
    introduced are unchecked, so it is owed when plan.md is newer than the
    validation and the last `PLAN_FIXED` line says `new_paths=yes`.
    """
    plan, pv = r.run / "plan.md", r.run / "plan-validation.md"
    try:
        if plan.stat().st_mtime_ns <= pv.stat().st_mtime_ns:
            return False
    except OSError:
        return False
    return last_fix_added_paths(r)


def plan_next(r: Run) -> tuple[int | str, str, str, bool] | None:
    """The pre-dispatch half of the loop: steps 3 to 6c.

    The order is the one that lets every question reach the user in one batch.
    The validator grades the plan at 4a, beside the design review; the relay at
    step 6 then carries the answers, the design findings and the validator's
    scope cut together; one planner Fix round at 6b folds all of that and the
    validator's PLAN_NEEDS_FIX findings; and a second validator pass at 6c runs
    only when that round added paths, asks nothing, and logs any `Smaller:` cut
    it names to `$RUN/decisions-log.md`.
    """
    gap = plan_written_gap(r)
    if gap:
        return gap
    q = r.text("questions.md")
    if "adr_conflict=yes" in q and "## Answers" not in q:
        return (5, "ADR conflict", "HALT per references/adr-workflow.md: name the ADR "
                "and clause and ask the user. Do not dispatch", True)
    gap = design_gap(r)
    if gap:
        return gap
    pv_file = r.run / "plan-validation.md"
    if not pv_file.exists():
        return ("4a", "plan unvalidated", "spawn the PLAN VALIDATOR (brief V) beside "
                "the plan design review; it asks nothing, and a `Smaller:` cut it "
                "names joins the step-6 relay", False)
    chosen_cut = any(ln.startswith("scope:") for ln in q.splitlines())
    late_cut = "" if chosen_cut else pass_two_cut(r)
    if late_cut:
        log_cut(r, late_cut)
    asked = "" if autopilot(r) else relay_owed(r, q, ask_cut=not late_cut)
    if asked:
        return (6, "user relay outstanding", "send the ONE relay turn: plan summary "
                "and the plan-triage counts as text, then ONE AskUserQuestion call — "
                f"{asked}. The validator's findings ride along in the same turn; "
                "options labelled with their own words", True)
    pv = verdict(pv_file)
    chosen = next((ln for ln in q.splitlines() if ln.startswith("scope:")), "")
    # A cut the user accepted and nobody applied is the exact failure the selection
    # exists to prevent, and it is derivable: Fix mode logs `scope: chose …` into
    # plan.md, so an accepted letter with no such line means the round never ran.
    cut_owed = (chosen and not chosen[7:].lstrip().startswith("A")
                and "scope: chose" not in r.text("plan.md"))
    fold = fold_owed(r, q)
    findings = pv == "PLAN_NEEDS_FIX" and not validator_fix_applied(r)
    if fold or cut_owed or findings:
        parts = []
        if fold:
            parts.append(f"folding {fold}")
        if cut_owed:
            parts.append(f"`Scope decision: {chosen[7:].strip()}`")
        if findings:
            parts.append("the validator's findings in plan-validation.md")
        # 6b is where the answers and the cut fold; a round that is owed only for
        # the validator's findings keeps its own label.
        step = "6b" if fold or cut_owed else "6c"
        label = "plan Fix round not run" if step == "6b" else "plan needs fixing"
        return (step, label, "spawn a fresh opus planner in Fix mode (brief F) "
                f"{' and '.join(parts)}, then wait with --rewritten $RUN/plan.md "
                "--expect $RUN/plan.md PLAN_FIXED — the validator grades the plan "
                "after this round, not before it", False)
    if pass_two_owed(r):
        return ("6c", "plan changed after validation", "spawn the PLAN VALIDATOR "
                "(brief V, pass 2): the Fix round added paths, so check them. It "
                "asks nothing; a `Smaller:` cut it names is logged to "
                "$RUN/decisions-log.md", False)
    return None


# The roles whose spawn marks a step boundary, and so can be checked against
# the run directory before they start. Reviewers, verifiers and writers are
# spawned at many points and prove nothing about what came before them.
GATED_ROLES = ("planner", "plan-validator", "implementer")


def spawn_gap(r: Run, role: str) -> tuple[int | str, str, str, bool] | None:
    """What the run still owes before `role` may be spawned, or None.

    The same reading of the run directory as plan_next, cut at the point each
    role belongs to: a planner needs the options resolved, a plan validator
    everything up to its own step 6c — the design reviews config.json promised
    the relay and the design Fix round — and an implementer the whole
    pre-dispatch half. A Fix-mode planner passes too, since it comes after
    everything a planner needs. Autopilot is applied inside plan_next, so a
    resume and this gate skip the same stops.
    """
    if role not in GATED_ROLES:
        return None
    if not (r.run / "config.json").exists():
        return plan_next(r)  # step 3 or 3a, whichever is missing
    gap = cycle_gap(r)
    if gap or role == "planner":
        return gap
    return plan_written_gap(r) if role == "plan-validator" else plan_next(r)


FOLLOWUP_OF = re.compile(r"^followup-of:\s*(\S.*)$", re.M)
FOLLOWUP_REVIEWER = re.compile(r"^followup-reviewer:\s*(\S.*?)\s*$", re.M)


def followup_rereview_owed(r: Run) -> str | None:
    """The step-11 re-review a review-followup run still owes, or None.

    A run whose `task.md` carries `followup-of:` closes a /teamlead:codex-review,
    and its step 11 reruns that review after the final report is sent — so the
    report alone does not finish it. Step 11 names this run as the review
    target, so `$RUN/review-package/` is where the evidence lands, and only
    evidence newer than the report is that rerun's. As with the plan review,
    only *starting* it is owed: the runner's attempts log is written before
    Codex is resolved, so a Codex that is missing or failed still leaves the
    record, and an Opus fallback answer counts too.
    """
    task = r.text("task.md")
    if not FOLLOWUP_OF.search(task):
        return None
    pkg = r.run / "review-package"
    report = (r.run / "final-report.md").stat().st_mtime
    evidence = ([pkg / "codex-review-attempts.log"]
                + sorted(pkg.glob("codex-review-r*.md"))
                + sorted(pkg.glob("opus-review-r*.md"))) if pkg.is_dir() else []
    # Only a start *after* the report is the step-11 rerun; a review of the same
    # run that ran mid-loop wrote the same files earlier and settles nothing.
    if any(f.exists() and f.stat().st_mtime >= report for f in evidence):
        return None
    reviewer = FOLLOWUP_REVIEWER.search(task)
    flag = (" --opus-code-review=fallback"
            if reviewer and reviewer.group(1) == "Opus fallback" else "")
    return (f"task.md has followup-of: — invoke /teamlead:codex-review "
            f"{r.run}{flag} (Skill tool), as step 11 says")


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
        owed = followup_rereview_owed(r)
        if owed:
            print("step: 11 — final report written; the re-review is still owed")
            print(f"next: {owed}")
            return 0
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
