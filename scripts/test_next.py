#!/usr/bin/env python3
"""Regression suite for next.py:  python3 scripts/test_next.py

next.py is the coordinator's router: one call per phase, which waits for what the
last call dispatched, reads the verdicts, checks the implementer's commits in git
and prints the exact next spawns. Each case here builds a real $RUN beside a real
git repository and drives the CLI, because the claim under test is the printed
instruction, not a helper's return value:

  * the commits an implementer lists are looked up in git before any verifier is
    paid for, and a missing or unrelated one halts instead;
  * a failed mutation gate leads to a rework brief, never to reviewers;
  * the RED run (`red_freeze.py --run`, which moves HEAD) is in the verifier's
    prompt only — nobody else may run it while writers share the tree;
  * the Codex gate (or its Opus fallback) loops until a gate triage at the
    current HEAD has no blocking row, and shares the one `reworkCap` count with
    ordinary rework;
  * a NEEDS_DECISION is logged and routed on, a docs-only rework goes to a
    writer, a `coordinator-fix:` commit is re-verified before the gate.

No pytest dependency, like every other suite here.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
NEXT = SCRIPTS / "next.py"
PLUGIN = SCRIPTS.parent

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, env=dict(os.environ, **GIT_ENV), check=True)
    return proc.stdout.strip()


def options_json(autopilot: bool = False, **options: str) -> str:
    """A `config.json` as run_config.py writes it, with the pre-dispatch options off."""
    opts = {"codexPlanReview": "off", "opusPlanReview": "off",
            "humanReadablePlan": "off", "securityReview": "off",
            "perfReview": "off", "codexCodeReview": "on",
            "opusCodeReview": "fallback", "adr": "off"}
    opts.update(options)
    return json.dumps({"options": opts, "sources": {k: "default" for k in opts},
                       "autopilot": autopilot, "optionsCard": "shown"})


class Result:
    def __init__(self, proc: subprocess.CompletedProcess[str]) -> None:
        self.code = proc.returncode
        self.out = proc.stdout
        self.err = proc.stderr

    def spawns(self) -> list[tuple[str, str]]:
        """(subagent type, prompt) per `spawn:` block, in printed order."""
        lines, found, i = self.out.splitlines(), [], 0
        while i < len(lines):
            if lines[i].startswith("spawn: "):
                kind = lines[i][len("spawn: "):].split()[0]
                body: list[str] = []
                j = i + 2 if lines[i + 1:i + 2] == ["<<<"] else i + 1
                while j < len(lines) and lines[j] != ">>>":
                    body.append(lines[j])
                    j += 1
                found.append((kind, "\n".join(body)))
                i = j
            i += 1
        return found

    def kinds(self) -> list[str]:
        return [k for k, _ in self.spawns()]

    def prompts(self, kind: str) -> list[str]:
        return [p for k, p in self.spawns() if k == kind]

    def commands(self) -> list[str]:
        return [ln.split(": ", 1)[1] for ln in self.out.splitlines()
                if ln.startswith(("run: ", "run-background: "))]

    def detail(self) -> str:
        return f"exit={self.code} out={self.out.strip()!r} err={self.err.strip()!r}"


class World:
    """A ready-to-dispatch run (plan validated, relay answered) beside a git repo."""

    def __init__(self, tmp: Path, streams: int = 1, deps: dict[int, int] | None = None,
                 cap: int | None = None, check_cmd: bool = False,
                 **options: str) -> None:
        self.tmp, self.streams = tmp, streams
        self.repo, self.home = tmp / "repo", tmp / "home"
        self.run = self.home / "runs" / "proj" / "2026-10-14-1000-feature"
        self.env = dict(os.environ, TEAMLEAD_HOME=str(self.home), **GIT_ENV)
        self.counter = 0
        self.repo.mkdir(parents=True)
        git(self.repo, "init", "-q")
        (self.repo / "app.py").write_text("x = 0\n")
        git(self.repo, "add", "app.py")
        git(self.repo, "commit", "-q", "-m", "base")
        self.base = git(self.repo, "rev-parse", "HEAD")
        (self.run / "briefs").mkdir(parents=True)
        if cap is not None:
            self.home.mkdir(exist_ok=True)
            (self.home / "config.json").write_text(json.dumps({"reworkCap": cap}))
        self.put("repo.txt", f"{self.repo}\n")
        self.put("task.md", "Build it.\n\nflags: none\n")
        self.put("config.json", options_json(**options))
        heads = "".join(f"## WS-{n} — stream {n}\n\n" for n in range(1, streams + 1))
        self.put("plan.md", f"# Plan\n\n{heads}")
        routes = "".join(
            f"WS-{n} | stream {n} | S | deps: "
            f"{'WS-' + str(deps[n]) if deps and n in deps else 'none'} | "
            f"input: no | hot: no | public: yes | wave {n}\n"
            for n in range(1, streams + 1))
        self.put("questions.md", "No open questions.\n\n## Routing\n"
                 f"PLAN_WRITTEN ws={streams} complex=no questions=0 decisions=0 "
                 f"adr_conflict=no\n{routes}")
        self.put("plan-validation.md",
                 "# Plan validation\n\nVerdict: PLAN_VALID\n\nSmaller: none\n")
        for n in range(1, streams + 1):
            self.put(f"briefs/impl-ws{n}-r1.md", self.brief_text(n, check_cmd))

    # --- files ---------------------------------------------------------------

    def put(self, name: str, text: str) -> Path:
        path = self.run / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def read(self, name: str) -> str:
        path = self.run / name
        return path.read_text() if path.exists() else ""

    @staticmethod
    def brief_text(ws: int, check_cmd: bool = False) -> str:
        return (f"# Implementer brief — WS-{ws} — round 1\n\n## Verification "
                "commands\n\ncwd: the repo\n- `python3 -m unittest discover`\n"
                "- `ruff check .`\n"
                + ("check: python3 -m py_compile {file}\n" if check_cmd else ""))

    def infix(self, ws: int) -> str:
        return f"ws{ws}-" if self.streams > 1 else ""

    def tag(self, ws: int, rnd: int) -> str:
        return f"{self.infix(ws)}r{rnd}"

    # --- git -----------------------------------------------------------------

    def commit(self, subject: str, name: str = "app.py") -> str:
        self.counter += 1
        with (self.repo / name).open("a") as f:
            f.write(f"x = {self.counter}\n")
        git(self.repo, "add", name)
        git(self.repo, "commit", "-q", "-m", subject)
        return git(self.repo, "rev-parse", "HEAD")

    def head(self) -> str:
        return git(self.repo, "rev-parse", "HEAD")

    def pin_base(self) -> None:
        self.put("base-sha.txt", f"{self.base}\n")

    # --- the phases a fixture run has already finished -----------------------

    def report(self, ws: int, rnd: int, commits: list[str],
               reds: list[str] | None = None, status: str = "done") -> Path:
        lines = "".join(f"{c} subject\n" for c in commits)
        red = " ".join(reds if reds is not None else commits[:1])
        return self.put(
            f"implementer-{self.tag(ws, rnd)}.md",
            f"# Implementer report — WS-{ws} — round {rnd}\n\n## Commits\n{lines}\n"
            f"## TDD\ntdd: APPLIED\nred: {red}\n\n```\nstatus: {status}\n"
            f"confidence: high — x\ncommits: {' '.join(commits)}\n```\n")

    def verifier(self, ws: int, rnd: int, outcome: str = "PASS",
                 touched: str = "") -> None:
        self.put(f"verifier-{self.tag(ws, rnd)}.md",
                 f"# Verifier — round {rnd}\n\nOUTCOME: {outcome}\n\n"
                 + (f"touched by these commits: {touched}\n" if touched else ""))

    def mutation(self, ws: int, rnd: int, ok: bool = True) -> None:
        self.put(f"mutation-{self.tag(ws, rnd)}.md",
                 "| probe | result |\n|---|---|\n"
                 + ("" if ok else "| app.py:2 | SURVIVED |\n")
                 + f"MUTATION: {'PASS' if ok else 'FAIL'} killed=3 "
                 f"survived={0 if ok else 1} invalid=0 unclassified=0 "
                 "not_run=0 not_applied=0\n")

    def reviews(self, ws: int, rnd: int, axes: tuple[str, ...] = ("code",)) -> None:
        for axis in axes:
            self.put(f"review-{self.tag(ws, rnd)}-{axis}.md",
                     "# Review\n\n| # | finding |\n\nVERDICT: APPROVED\n")

    def triage(self, ws: int, rnd: int, verdict: str, extra: str = "") -> None:
        self.put(f"triage-{self.tag(ws, rnd)}.md",
                 f"# Triage — round {rnd}\n\n{extra}\nVERDICT: {verdict}\n")

    def rework_brief(self, ws: int, rnd: int) -> None:
        self.put(f"briefs/impl-ws{ws}-r{rnd}.md", f"# rework — round {rnd}\n")

    def finished_round(self, ws: int, rnd: int, verdict: str,
                       commits: list[str] | None = None) -> list[str]:
        """Every file of a round up to its triage; a rework verdict writes the brief."""
        made = commits or [self.commit(f"round {rnd}")]
        self.report(ws, rnd, made)
        self.verifier(ws, rnd)
        self.mutation(ws, rnd)
        self.reviews(ws, rnd)
        self.triage(ws, rnd, verdict)
        if verdict == "NEEDS_REWORK":
            self.rework_brief(ws, rnd + 1)
        return made

    def gate_round(self, ws: int, rnd: int) -> list[str]:
        """A round a gate triage asked for: report, verifier and mutation only."""
        made = [self.commit(f"round {rnd}")]
        self.report(ws, rnd, made)
        self.verifier(ws, rnd)
        self.mutation(ws, rnd)
        return made

    # --- the gate ------------------------------------------------------------

    @property
    def pkg(self) -> Path:
        return self.run / "codex-gate-package"

    def attempt(self, line: str) -> None:
        self.pkg.mkdir(exist_ok=True)
        with (self.pkg / "codex-gate-attempts.log").open("a") as f:
            f.write(f"2026-10-14T10:00:00 {line}\n")

    def codex_review(self, n: int) -> None:
        self.pkg.mkdir(exist_ok=True)
        (self.pkg / f"codex-gate-r{n}.md").write_text("| # | finding |\n")
        self.attempt(f"done: {self.pkg}/codex-gate-r{n}.md")

    def gate_triage(self, k: int, verdict: str, extra: str = "") -> None:
        self.put(f"triage-gate-r{k}.md",
                 f"# Triage — gate {k}\n\n{extra}\nVERDICT: {verdict}\n")

    # --- running -------------------------------------------------------------

    def step(self, *args: str, timeout: int = 5) -> Result:
        proc = subprocess.run(
            [sys.executable, str(NEXT), str(self.run), "--poll", "0", "--timeout",
             str(timeout), *args], capture_output=True, text=True, env=self.env,
            check=False)
        return Result(proc)

    def approved(self, ws: int = 1) -> None:
        """Stream `ws` finished round 1 and was approved by its triage."""
        self.pin_base()
        self.finished_round(ws, 1, "APPROVED")


def all_approved(w: World) -> None:
    """Every stream approved at round 1: the run is at the Codex gate."""
    w.pin_base()
    for ws in range(1, w.streams + 1):
        w.finished_round(ws, 1, "APPROVED")


# ------------------------------------------------------------------------ kickoff

def case_exit_codes(tmp: Path) -> None:
    empty = tmp / "empty"
    empty.mkdir()
    proc = subprocess.run([sys.executable, str(NEXT), str(empty)],
                          capture_output=True, text=True, check=False)
    check("not a run directory → exit 2", proc.returncode == 2,
          f"exit={proc.returncode} out={proc.stdout!r}")

    w = World(tmp / "a")
    (w.run / "questions.md").unlink()
    r = w.step()
    check("a plan the planner never finished → step 4, the coordinator acts alone",
          r.code == 0 and "step: 4" in r.out, r.detail())

    w = World(tmp / "b")
    w.put("questions.md", "1. Round half-up? Recommend yes.\n\n## Routing\n"
          "PLAN_WRITTEN ws=1 complex=no questions=1 decisions=0 adr_conflict=no\n")
    r = w.step()
    check("an unanswered relay → exit 1, the user is needed",
          r.code == 1 and "step: 6" in r.out, r.detail())

    w = World(tmp / "c")
    r = w.step()
    check("a dispatchable run → exit 0", r.code == 0 and r.kinds(), r.detail())

    w = World(tmp / "d")
    w.pin_base()
    w.report(1, 1, [w.commit("work")], status="blocked")
    r = w.step()
    check("a blocked implementer → exit 1 with a halt line",
          r.code == 1 and "halt:" in r.out and not r.kinds(), r.detail())

    w = World(tmp / "e")
    r = w.step()
    r = w.step(timeout=1)
    check("a phase file that never lands → exit 3 with the RETRY line",
          r.code == 3 and "RETRY:" in r.out, r.detail())


def case_kickoff_prints_baseline_verifier(tmp: Path) -> None:
    w = World(tmp, streams=2)
    r = w.step()
    verifiers = r.prompts("teamlead:verifier")
    ok = (r.code == 0 and len(verifiers) == 2 and r.kinds() == ["teamlead:verifier"] * 2
          and all(w.base in p for p in verifiers)
          and "baseline-ws1.md" in verifiers[0] and "baseline-ws2.md" in verifiers[1])
    check("kickoff: one baseline verifier per stream, at the base SHA, in one batch",
          ok, r.detail())
    check("kickoff pins the base SHA beside the run",
          w.read("base-sha.txt").strip() == w.base, w.read("base-sha.txt"))
    check("kickoff names no implementer yet",
          "teamlead:implementer" not in r.out, r.detail())

    r = w.step(timeout=1)
    check("the baseline files are awaited, not skipped", r.code == 3, r.detail())

    r = w.step("--redo")
    check("--redo re-prints the same dispatch instead of waiting",
          r.code == 0 and r.kinds() == ["teamlead:verifier"] * 2, r.detail())

    for ws in (1, 2):
        w.put(f"baseline-ws{ws}.md", "# Verifier — baseline\n\nOUTCOME: PASS\n")
    r = w.step()
    prompts = r.prompts("teamlead:implementer")
    ok = (r.code == 0 and len(prompts) == 2
          and "briefs/impl-ws1-r1.md" in prompts[0]
          and "briefs/impl-ws2-r1.md" in prompts[1]
          and all("--run" not in p and "red_freeze" not in p for p in prompts))
    check("baselines in → both implementers in one batch, no --run in their prompts",
          ok, r.detail())

    w2 = World(tmp / "second", streams=1)
    w2.step()
    w2.put("baseline-ws1.md", "# Verifier — baseline\n\nOUTCOME: CANNOT_RUN\n")
    r = w2.step()
    check("a baseline that CANNOT_RUN is an environment problem → halt",
          r.code == 1 and "halt:" in r.out and not r.kinds(), r.detail())

    w3 = World(tmp / "third", streams=1)
    w3.step()
    w3.put("baseline-ws1.md", "# Verifier — baseline\n\nOUTCOME: FAIL\n")
    r = w3.step()
    check("a baseline that already FAILs is pre-existing, not a stop",
          r.code == 0 and r.kinds() == ["teamlead:implementer"], r.detail())


def case_dependent_stream_waits(tmp: Path) -> None:
    w = World(tmp, streams=2, deps={2: 1})
    w.pin_base()
    for ws in (1, 2):
        w.put(f"baseline-ws{ws}.md", "# b\n\nOUTCOME: PASS\n")
    r = w.step()
    ok = (r.kinds() == ["teamlead:implementer"]
          and "briefs/impl-ws1-r1.md" in r.spawns()[0][1])
    check("WS-2 depends on WS-1: only WS-1's implementer is dispatched", ok,
          r.detail())
    w.finished_round(1, 1, "APPROVED")
    r = w.step()
    ok = r.kinds() == ["teamlead:implementer"] and \
        "briefs/impl-ws2-r1.md" in r.spawns()[0][1]
    check("WS-1 approved → WS-2's implementer", ok, r.detail())


# ------------------------------------------------------------------- the commits

def case_commits_checked_before_verifier(tmp: Path) -> None:
    w = World(tmp / "missing")
    w.pin_base()
    w.report(1, 1, ["deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"])
    r = w.step()
    check("a listed SHA that git does not have halts, with no verifier",
          r.code == 1 and "halt:" in r.out and "deadbeef" in r.out
          and not r.kinds(), r.detail())

    w = World(tmp / "side")
    good = w.commit("first")
    side_base = good
    w.base = w.commit("second")  # the base the run pinned
    w.pin_base()
    git(w.repo, "checkout", "-q", "-b", "side", side_base)
    stray = w.commit("stray")
    git(w.repo, "checkout", "-q", "-")
    w.report(1, 1, [stray])
    r = w.step()
    check("a commit on a side branch is not on HEAD's history → halt",
          r.code == 1 and "halt:" in r.out and stray[:7] in r.out
          and not r.kinds(), r.detail())

    w = World(tmp / "before")
    old = w.commit("before the base")
    w.base = w.commit("the base")
    w.pin_base()
    w.report(1, 1, [old])
    r = w.step()
    check("a commit older than the base does not descend from it → halt",
          r.code == 1 and "halt:" in r.out and not r.kinds(), r.detail())

    w = World(tmp / "ok")
    w.pin_base()
    c = w.commit("good work")
    w.report(1, 1, [c])
    r = w.step()
    check("commits that exist and descend from the base → the verifier",
          r.code == 0 and r.kinds() == ["teamlead:verifier"], r.detail())

    w = World(tmp / "fallback")
    w.pin_base()
    c = w.commit("good work")
    w.put("implementer-r1.md", "# Report\n\n```\nstatus: done\nconfidence: high — x\n"
          f"commits: {c}\n```\n")
    r = w.step()
    check("a report with no ## Commits section falls back to its commits: line",
          r.code == 0 and r.kinds() == ["teamlead:verifier"]
          and c in r.spawns()[0][1], r.detail())


def case_verifier_spawn_carries_red_run(tmp: Path) -> None:
    w = World(tmp, check_cmd=True)
    w.pin_base()
    red = w.commit("tests: red")
    green = w.commit("green")
    w.report(1, 1, [red, green], reds=[red])
    r = w.step()
    prompts = r.prompts("teamlead:verifier")
    p = prompts[0] if prompts else ""
    cmd = "python3 -m unittest discover && ruff check ."
    ok = (r.code == 0 and len(prompts) == 1
          and f"Expected HEAD: {w.head()}" in p and w.base in p
          and re.search(rf"red_freeze\.py --repo {re.escape(str(w.repo))} "
                        rf"--run '?{re.escape(cmd)}'? {red}\b(?! {green})", p)
          and f"--commits {red} {green}" in p
          and "mutate.py" in p and f"--base {w.base}" in p
          and "--check-cmd 'python3 -m py_compile {file}'" in p
          and f"--out {w.run}/mutation-r1.md" in p
          and f"{w.run}/verifier-r1.md" in p)
    check("the verifier spawn names the RED run, the mutation gate and the HEAD",
          bool(ok), r.detail())
    check("the verifier waits on its own report", f"expect: {w.run}/verifier-r1.md"
          in r.out, r.detail())

    w2 = World(tmp / "plain")
    w2.pin_base()
    c = w2.commit("work")
    w2.report(1, 1, [c], reds=[])
    r = w2.step()
    p = (r.prompts("teamlead:verifier") or [""])[0]
    check("no RED commit this round → no --run, but the mutation gate stays",
          "--run" not in p and "mutate.py" in p and "--check-cmd" not in p,
          r.detail())

    w3 = World(tmp / "rework")
    w3.pin_base()
    first = w3.finished_round(1, 1, "NEEDS_REWORK")
    red2 = w3.commit("tests: round two red")
    green2 = w3.commit("round two green")
    w3.report(1, 2, [red2, green2], reds=first + [red2])
    r = w3.step()
    p = (r.prompts("teamlead:verifier") or [""])[0]
    check("a rework round runs only this round's RED, not the earlier one",
          f"{red2}" in p and first[0] not in p.split("--run", 1)[-1].split("\n")[0]
          and f"--commits {red2} {green2}" in p, r.detail())


def case_implementer_and_reviewer_prompts_have_no_run(tmp: Path) -> None:
    w = World(tmp, securityReview="on")
    w.pin_base()
    c = w.commit("work")
    w.report(1, 1, [c])
    w.verifier(1, 1)
    w.mutation(1, 1)
    r = w.step()
    briefs = sorted((w.run / "briefs").glob("review-r1-*.md"))
    texts = [p.read_text() for p in briefs]
    ok = (len(briefs) >= 2 and all("--run" not in t and "red_freeze" not in t
                                   for t in texts)
          and all("--run" not in p for _, p in r.spawns()))
    check("reviewer prompts and briefs name no `--run` (the verifier's RED run)", ok,
          r.detail())
    w2 = World(tmp / "impl")
    w2.pin_base()
    w2.finished_round(1, 1, "NEEDS_REWORK")
    r = w2.step()
    check("a rework implementer's prompt names no `--run` either",
          r.kinds() == ["teamlead:implementer"] and "--run" not in r.out,
          r.detail())


# ------------------------------------------------------------- verifier outcomes

def case_mutation_fail_routes_to_rework(tmp: Path) -> None:
    w = World(tmp / "survivor")
    w.pin_base()
    c = w.commit("work")
    w.report(1, 1, [c])
    w.verifier(1, 1, "FAIL")
    w.mutation(1, 1, ok=False)
    r = w.step()
    brief = w.read("briefs/impl-ws1-r2.md")
    ok = (r.code == 0 and r.kinds() == ["teamlead:implementer"]
          and "briefs/impl-ws1-r2.md" in r.spawns()[0][1]
          and "verifier-r1.md" in brief and "mutation-r1.md" in brief
          and "impl-ws1-r1.md" in brief and "implementer-r1.md" in brief
          and not list((w.run / "briefs").glob("review-*")))
    check("verifier FAIL with a survivor → rework brief + implementer, no reviewers",
          ok, r.detail())

    w = World(tmp / "silent")
    w.pin_base()
    c = w.commit("work")
    w.report(1, 1, [c])
    w.verifier(1, 1, "PASS")
    w.mutation(1, 1, ok=False)
    r = w.step()
    check("a verifier PASS over a MUTATION: FAIL report is still a rework",
          r.kinds() == ["teamlead:implementer"]
          and not list((w.run / "briefs").glob("review-*")), r.detail())

    w = World(tmp / "preexisting")
    w.pin_base()
    c = w.commit("work")
    w.report(1, 1, [c])
    w.verifier(1, 1, "FAIL", touched="no")
    w.mutation(1, 1)
    r = w.step()
    check("a FAIL where every failure is touched=no is pre-existing → reviewers",
          r.code == 0 and "teamlead:implementer" not in r.kinds()
          and r.prompts("code-review"), r.detail())

    w = World(tmp / "nomutation")
    w.pin_base()
    c = w.commit("work")
    w.report(1, 1, [c])
    w.verifier(1, 1, "PASS")
    r = w.step()
    check("a PASS with no mutation report is not a pass → halt",
          r.code == 1 and "halt:" in r.out and not r.kinds(), r.detail())

    w = World(tmp / "cannot")
    w.pin_base()
    w.report(1, 1, [w.commit("work")])
    w.verifier(1, 1, "CANNOT_RUN")
    r = w.step()
    check("CANNOT_RUN is an environment problem → halt, never a rework",
          r.code == 1 and "halt:" in r.out and not (w.run / "briefs" /
                                                    "impl-ws1-r2.md").exists(),
          r.detail())


def case_pass_routes_to_reviewers(tmp: Path) -> None:
    w = World(tmp, securityReview="on", perfReview="when-needed")
    w.pin_base()
    c = w.commit("work")
    w.report(1, 1, [c])
    w.verifier(1, 1)
    w.mutation(1, 1)
    r = w.step()
    spawns = r.spawns()
    code = next((p for k, p in spawns if k == "code-review"), "")
    ok = (r.code == 0 and [k for k, _ in spawns].count("code-review") == 1
          and len(spawns) == 2 and "performance-engineer" not in r.kinds()
          and f"Read and follow {w.run}/briefs/review-r1-code.md." in code
          and f"expect: {w.run}/review-r1-code.md" in r.out
          and f"expect: {w.run}/review-r1-security.md" in r.out
          and "model=opus" in r.out and "model=sonnet" in r.out)
    check("verifier + mutation PASS → the review_briefs spawns, in one batch", ok,
          r.detail())
    brief = w.read("briefs/review-r1-code.md")
    check("the reviewer brief names the commits and the mutation report",
          c in brief and "mutation-r1.md" in brief, brief)

    w.reviews(1, 1, ("code", "security"))
    r = w.step()
    triage = r.prompts("teamlead:triage")
    ok = (r.code == 0 and len(triage) == 1 and "review-r1-code.md" in triage[0]
          and "Rework count before this round: 0" in triage[0]
          and "reworkCap: 3" in triage[0] and f"{w.run}/triage-r1.md" in triage[0])
    check("all reviews in → the triage spawn with the rework count and cap", ok,
          r.detail())


def case_barrier_orders_stages(tmp: Path) -> None:
    w = World(tmp, streams=2)
    w.pin_base()
    for ws in (1, 2):
        w.put(f"baseline-ws{ws}.md", "# b\n\nOUTCOME: PASS\n")
    a = w.commit("one")
    w.report(1, 1, [a])
    r = w.step()
    check("a stream that reported waits for its sibling's implementer",
          r.kinds() == ["teamlead:implementer"]
          and "briefs/impl-ws2-r1.md" in r.spawns()[0][1], r.detail())

    b = w.commit("two")
    w.report(2, 1, [b])
    r = w.step()
    prompts = r.prompts("teamlead:verifier")
    ok = (len(prompts) == 2 and f"Expected HEAD: {w.head()}" in prompts[0]
          and f"Expected HEAD: {w.head()}" in prompts[1]
          and "verifier-ws1-r1.md" in prompts[0]
          and "verifier-ws2-r1.md" in prompts[1]
          and f"--commits {a}" in prompts[0] and f"--commits {b}" in prompts[1]
          and f"--commits {a} {b}" not in r.out)
    check("every writer done → both verifiers in one batch at one HEAD, each "
          "mutating only its own commits", ok, r.detail())

    for ws in (1, 2):
        w.verifier(ws, 1)
        w.mutation(ws, 1)
    w.verifier(2, 1, "FAIL")
    w.mutation(2, 1, ok=False)
    r = w.step()
    check("one stream's verifier FAIL → its rework spawn before anyone's reviewers",
          r.kinds() == ["teamlead:implementer"]
          and "briefs/impl-ws2-r2.md" in r.spawns()[0][1], r.detail())


# ------------------------------------------------------------------- triage

def case_halts_only_where_the_user_is_needed(tmp: Path) -> None:
    w = World(tmp / "stop")
    w.pin_base()
    w.finished_round(1, 1, "STOP")
    r = w.step()
    check("triage STOP → halt", r.code == 1 and "halt:" in r.out and not r.kinds(),
          r.detail())

    w = World(tmp / "unreadable")
    w.pin_base()
    w.finished_round(1, 1, "APPROVED")
    w.put("triage-r1.md", "# Triage\n\nthe code looks fine to me\n")
    r = w.step()
    check("a triage with no VERDICT line → halt, nothing to route on",
          r.code == 1 and "halt:" in r.out, r.detail())

    w = World(tmp / "partial")
    w.pin_base()
    w.report(1, 1, [w.commit("w")], status="partial")
    r = w.step()
    check("a partial implementer → halt", r.code == 1 and "halt:" in r.out, r.detail())

    w = World(tmp / "noroute")
    w.pin_base()
    w.put("implementer-r1.md", "# Report\n\nI did the thing.\n")
    r = w.step()
    check("a report with no routing line → halt", r.code == 1 and "halt:" in r.out,
          r.detail())


def case_needs_decision_logged(tmp: Path) -> None:
    w = World(tmp)
    w.pin_base()
    w.finished_round(1, 1, "NEEDS_DECISION")
    w.put("triage-r1.md", "# Triage — round 1\n\n| # | row |\n"
          "| 1 | rounding | recommended: keep half-up |\n"
          "recommended: log the choice in the changelog\n\n"
          "VERDICT: NEEDS_DECISION rows=2 decisions=2 docs_only=no\n")
    (w.run / "briefs" / "impl-ws1-r2.md").unlink(missing_ok=True)
    r = w.step()
    log = w.read("decisions-log.md")
    ok = (r.code == 0 and "keep half-up" in log
          and "log the choice in the changelog" in log
          and "teamlead:implementer" not in r.kinds()
          and any("review_package.py" in c for c in r.commands()))
    check("NEEDS_DECISION with no rework brief → logged, then routed as approved",
          ok, r.detail() + log)
    w.step()
    check("the decision is logged once however often next.py runs",
          w.read("decisions-log.md").count("keep half-up") == 1,
          w.read("decisions-log.md"))

    w2 = World(tmp / "rework")
    w2.pin_base()
    w2.finished_round(1, 1, "NEEDS_DECISION")
    w2.put("triage-r1.md", "# Triage\n\nrecommended: use half-even\n\n"
           "VERDICT: NEEDS_DECISION decisions=1\n")
    w2.rework_brief(1, 2)
    r = w2.step()
    check("NEEDS_DECISION beside a rework brief → routed as NEEDS_REWORK",
          r.code == 0 and r.kinds() == ["teamlead:implementer"]
          and "use half-even" in w2.read("decisions-log.md"), r.detail())


def case_docs_only_routes_to_writer(tmp: Path) -> None:
    w = World(tmp)
    w.pin_base()
    w.finished_round(1, 1, "NEEDS_REWORK")
    (w.run / "briefs" / "impl-ws1-r2.md").unlink()
    w.put("triage-r1.md", "# Triage — round 1\n\nVERDICT: NEEDS_REWORK rows=2 "
          "docs_only=yes decisions=0\n")
    w.put("briefs/docs-ws1-r1.md", "# Docs fix — fix two README rows\n")
    r = w.step()
    writers = r.prompts("teamlead:writer")
    ok = (r.code == 0 and r.kinds() == ["teamlead:writer"]
          and "briefs/docs-ws1-r1.md" in writers[0]
          and f"{w.run}/docs-fix-ws1-r1.md" in writers[0]
          and "docs-fix:" in writers[0] and "DOCS_FIXED" in writers[0]
          and not list((w.run / "briefs").glob("review-*")))
    check("docs_only=yes → one writer spawn, no implementer, no re-review", ok,
          r.detail())

    fix = w.commit("docs-fix: README rows", "README.md")
    w.put("docs-fix-ws1-r1.md", f"# Docs fix\n\nDOCS_FIXED rows=2 commit={fix}\n")
    r = w.step()
    check("the writer's commit is checked, then the next phase is the Codex gate",
          r.code == 0 and any("review_package.py" in c for c in r.commands())
          and not r.kinds(), r.detail())

    w2 = World(tmp / "bad")
    w2.pin_base()
    w2.finished_round(1, 1, "NEEDS_REWORK")
    (w2.run / "briefs" / "impl-ws1-r2.md").unlink()
    w2.put("triage-r1.md", "# Triage\n\nVERDICT: NEEDS_REWORK docs_only=yes\n")
    w2.put("briefs/docs-ws1-r1.md", "# Docs fix\n")
    wrong = w2.commit("tweak code", "app.py")
    w2.put("docs-fix-ws1-r1.md", f"DOCS_FIXED rows=1 commit={wrong}\n")
    r = w2.step()
    check("a writer commit without the docs-fix: subject is refused → halt",
          r.code == 1 and "halt:" in r.out and not r.commands(), r.detail())


# ------------------------------------------------------------------ the gate

def case_approved_routes_to_codex_gate(tmp: Path) -> None:
    w = World(tmp / "codex", streams=2)
    all_approved(w)
    r = w.step()
    cmds = r.commands()
    pkg = f"python3 {PLUGIN}/scripts/review_package.py {w.run} --out {w.pkg}"
    runner = (f"python3 {PLUGIN}/scripts/run_codex_review.py {w.pkg}/PROMPT.md "
              "--artifact-stem codex-gate")
    ok = (r.code == 0 and pkg in cmds and runner in cmds
          and cmds.index(pkg) < cmds.index(runner)
          and f"run-background: {runner}" in r.out and not r.kinds())
    check("every stream approved → the package and background runner for the "
          "whole diff", ok, r.detail())
    r = w.step(timeout=1)
    check("the Codex run is awaited, not assumed", r.code == 3 and "RETRY:" in r.out,
          r.detail())
    w.attempt("started")
    r = w.step(timeout=1)
    check("a started, unfinished run is still awaited", r.code == 3, r.detail())

    w.attempt("failed: no saved Codex login")
    r = w.step()
    p = (r.prompts("teamlead:code-reviewer") or [""])[0]
    ok = (r.code == 0 and f"PROMPT.md: {w.pkg}/PROMPT.md" in p
          and f"Repo: {w.repo}" in p
          and f"Answer: {w.pkg}/opus-review-r1.md" in p
          and "Codex could not run (no saved Codex login), so this is the only "
          "review of this change." in p)
    check("a recorded Codex failure → the teamlead:code-reviewer fallback", ok,
          r.detail())

    (w.pkg / "opus-review-r1.md").write_text("| # | finding |\n")
    r = w.step()
    gate = (r.prompts("teamlead:triage") or [""])[0]
    check("the fallback's review in → the gate triage",
          f"{w.run}/triage-gate-r1.md" in gate and "opus-review-r1.md" in gate,
          r.detail())

    w2 = World(tmp / "off", opusCodeReview="off")
    all_approved(w2)
    w2.step()
    w2.attempt("failed: no saved Codex login")
    r = w2.step()
    check("opusCodeReview=off: a Codex failure halts instead of falling back",
          r.code == 1 and "halt:" in r.out and not r.kinds(), r.detail())

    w3 = World(tmp / "skipped", codexCodeReview="off")
    all_approved(w3)
    r = w3.step()
    check("codexCodeReview=off skips the gate and closes",
          r.code == 0 and not r.commands() and "final-report.md" in r.out,
          r.detail())

    w4 = World(tmp / "done")
    all_approved(w4)
    w4.step()
    w4.codex_review(1)
    r = w4.step()
    gate = (r.prompts("teamlead:triage") or [""])[0]
    check("Codex's review in → the gate triage, which writes the rework briefs",
          f"{w4.pkg}/codex-gate-r1.md" in gate
          and f"{w4.run}/triage-gate-r1.md" in gate
          and "briefs/impl-ws1-r2.md" in gate, r.detail())


def gate_loop(tmp: Path, fallback: bool) -> None:
    label = "opus fallback" if fallback else "codex"
    w = World(tmp)
    all_approved(w)
    r = w.step()
    check(f"[{label}] gate 1 starts", any("review_package.py" in c
                                          for c in r.commands()), r.detail())

    def review(k: int) -> None:
        if fallback:
            w.attempt("failed: codex is down")
            (w.pkg / f"opus-review-r{k}.md").write_text("| # | finding |\n")
        else:
            w.codex_review(k)

    review(1)
    w.step()  # the gate triage spawn
    w.gate_triage(1, "NEEDS_REWORK")
    w.rework_brief(1, 2)
    r = w.step()
    check(f"[{label}] a blocking gate triage → the round-2 implementer",
          r.kinds() == ["teamlead:implementer"]
          and "briefs/impl-ws1-r2.md" in r.spawns()[0][1], r.detail())

    red, green = w.commit("tests: gate fix red"), w.commit("gate fix")
    w.report(1, 2, [red, green], reds=[red])
    r = w.step()
    p = (r.prompts("teamlead:verifier") or [""])[0]
    check(f"[{label}] its report → a verifier with the mutation gate",
          "mutate.py" in p and f"--commits {red} {green}" in p
          and f"{w.run}/verifier-r2.md" in p and not r.commands(), r.detail())

    w.verifier(1, 2)
    w.mutation(1, 2)
    r = w.step()
    cmds = r.commands()
    ok = (r.code == 0 and any("review_package.py" in c for c in cmds)
          and not r.kinds() and not list((w.run / "briefs").glob("review-r2*")))
    check(f"[{label}] a passing verifier → a FRESH gate at the new HEAD, with no "
          "stream reviewers or triage in between", ok, r.detail())
    check(f"[{label}] no close before a clean gate", "final-report" not in r.out,
          r.detail())

    review(2)
    w.step()
    w.gate_triage(2, "APPROVED_WITH_NOTES")
    r = w.step()
    check(f"[{label}] a clean gate triage at that HEAD closes the run",
          r.code == 0 and "final-report.md" in r.out
          and not any("review_package.py" in c for c in r.commands()),
          r.detail())


def case_gate_loops_until_clean(tmp: Path) -> None:
    gate_loop(tmp / "codex", fallback=False)
    gate_loop(tmp / "opus", fallback=True)


def case_gate_triage_is_stale_after_new_commits(tmp: Path) -> None:
    w = World(tmp)
    all_approved(w)
    w.step()
    w.codex_review(1)
    w.step()
    w.gate_triage(1, "APPROVED")
    w.commit("coordinator-fix: touch up")
    r = w.step()
    check("a gate approved at an older HEAD does not close past a new fix commit: "
          "the fix is verified first", r.kinds() == ["teamlead:verifier"]
          and "final-report" not in r.out, r.detail())


def case_gate_rework_shares_cap(tmp: Path) -> None:
    # Ordinary rework: round 3 may still ask for a round 4, round 4 may not ask
    # for a round 5.
    w = World(tmp / "ordinary", cap=3)
    w.pin_base()
    w.finished_round(1, 1, "NEEDS_REWORK")
    w.finished_round(1, 2, "NEEDS_REWORK")
    w.finished_round(1, 3, "NEEDS_REWORK")
    (w.run / "briefs" / "impl-ws1-r4.md").unlink()
    r = w.step()
    check("cap 3, NEEDS_REWORK after round 3 → triage is re-dispatched for round 4",
          r.code == 0 and r.kinds() == ["teamlead:triage"]
          and "briefs/impl-ws1-r4.md" in r.spawns()[0][1], r.detail())
    w.rework_brief(1, 4)
    w.finished_round(1, 4, "NEEDS_REWORK")
    (w.run / "briefs" / "impl-ws1-r5.md").unlink()
    r = w.step()
    check("…and a NEEDS_REWORK after round 4 halts for the user, no round 5",
          r.code == 1 and "halt:" in r.out and "cap" in r.out and not r.kinds(),
          r.detail())

    # Gate rework: same two edges.
    w = World(tmp / "gate", cap=3)
    w.pin_base()
    for rnd in (1, 2, 3):
        w.finished_round(1, rnd, "NEEDS_REWORK" if rnd < 3 else "APPROVED")
    w.step()
    w.codex_review(1)
    w.step()
    w.gate_triage(1, "NEEDS_REWORK")
    w.rework_brief(1, 4)
    r = w.step()
    check("cap 3, a gate NEEDS_REWORK after round 3 still spawns round 4",
          r.kinds() == ["teamlead:implementer"]
          and "briefs/impl-ws1-r4.md" in r.spawns()[0][1], r.detail())
    w.gate_round(1, 4)
    w.step()
    w.codex_review(2)
    w.step()
    w.gate_triage(2, "NEEDS_REWORK")
    w.rework_brief(1, 5)
    r = w.step()
    check("…and a gate NEEDS_REWORK after round 4 halts instead of spawning round 5",
          r.code == 1 and "halt:" in r.out and "cap" in r.out and not r.kinds(),
          r.detail())

    # One count: ordinary rework r1 -> r2, then gate reworks r2 -> r3 -> r4 use it up.
    w = World(tmp / "shared", cap=3)
    w.pin_base()
    w.finished_round(1, 1, "NEEDS_REWORK")
    w.finished_round(1, 2, "APPROVED")
    for k, rnd in ((1, 3), (2, 4)):
        w.step()
        w.codex_review(k)
        w.step()
        w.gate_triage(k, "NEEDS_REWORK")
        w.rework_brief(1, rnd)
        r = w.step()
        check(f"shared count: gate {k} rework to round {rnd} is still allowed",
              r.kinds() == ["teamlead:implementer"], r.detail())
        w.gate_round(1, rnd)
    w.step()
    w.codex_review(3)
    w.step()
    w.gate_triage(3, "NEEDS_REWORK")
    w.rework_brief(1, 5)
    r = w.step()
    check("shared count: ordinary + two gate reworks use the cap up → halt",
          r.code == 1 and "halt:" in r.out and not r.kinds(), r.detail())

    # A verifier FAIL is a rework too.
    w = World(tmp / "verifier", cap=3)
    w.pin_base()
    for rnd in (1, 2, 3):
        w.finished_round(1, rnd, "NEEDS_REWORK")
    w.report(1, 4, [w.commit("round 4")])
    w.verifier(1, 4, "FAIL")
    w.mutation(1, 4, ok=False)
    r = w.step()
    check("a verifier FAIL after round 4 hits the same cap → halt",
          r.code == 1 and "halt:" in r.out and not r.kinds(), r.detail())


def case_gate_triage_unreadable_or_stop_halts(tmp: Path) -> None:
    w = World(tmp / "stop")
    all_approved(w)
    w.step()
    w.codex_review(1)
    w.step()
    w.gate_triage(1, "STOP")
    r = w.step()
    check("a STOP from the gate triage → halt", r.code == 1 and "halt:" in r.out,
          r.detail())
    w = World(tmp / "nothing")
    all_approved(w)
    w.step()
    w.codex_review(1)
    w.step()
    w.gate_triage(1, "NEEDS_REWORK")
    r = w.step()
    check("a gate NEEDS_REWORK that wrote no brief → the triage is re-dispatched",
          r.kinds() == ["teamlead:triage"], r.detail())


def case_gate_docs_only_closes_after_the_writer(tmp: Path) -> None:
    w = World(tmp)
    all_approved(w)
    w.step()
    w.codex_review(1)
    w.step()
    w.gate_triage(1, "NEEDS_REWORK", "docs_only=yes")
    w.put("briefs/docs-ws1-r1.md", "# Docs fix\n")
    r = w.step()
    check("a gate NEEDS_REWORK with only a docs brief → the writer",
          r.kinds() == ["teamlead:writer"], r.detail())
    fix = w.commit("docs-fix: gate rows", "README.md")
    w.put("docs-fix-ws1-r1.md", f"DOCS_FIXED rows=1 commit={fix}\n")
    r = w.step()
    check("the docs-fix commit does not need a fresh gate → close",
          r.code == 0 and "final-report.md" in r.out
          and not any("review_package.py" in c for c in r.commands()), r.detail())


# ------------------------------------------------------- coordinator edits, close

def case_coordinator_fix_reverified(tmp: Path) -> None:
    w = World(tmp)
    all_approved(w)
    fix = w.commit("coordinator-fix: user asked for a rename")
    r = w.step()
    p = (r.prompts("teamlead:verifier") or [""])[0]
    ok = (r.code == 0 and r.kinds() == ["teamlead:verifier"] and not r.commands()
          and f"Expected HEAD: {w.head()}" in p and "mutate.py" in p
          and f"--commits {fix}" in p and f"{w.run}/verifier-fix-1.md" in p
          and f"--out {w.run}/mutation-fix-1.md" in p)
    check("a coordinator-fix commit → a verifier with the mutation gate, before "
          "the Codex gate", bool(ok), r.detail())

    w.put("verifier-fix-1.md", "# Verifier\n\nOUTCOME: PASS\n")
    w.put("mutation-fix-1.md", "MUTATION: PASS killed=1 survived=0 invalid=0 "
          "unclassified=0 not_run=0 not_applied=0\n")
    r = w.step()
    check("verified → the Codex gate sees it", r.code == 0
          and any("review_package.py" in c for c in r.commands()), r.detail())

    w2 = World(tmp / "ordinary")
    all_approved(w2)
    w2.commit("an ordinary stream commit")
    r = w2.step()
    check("a commit without the coordinator-fix: subject is not re-verified here",
          not r.kinds() and any("review_package.py" in c for c in r.commands()),
          r.detail())

    w3 = World(tmp / "fails")
    all_approved(w3)
    w3.commit("coordinator-fix: one")
    w3.step()
    w3.put("verifier-fix-1.md", "# Verifier\n\nOUTCOME: FAIL\n")
    w3.put("mutation-fix-1.md", "MUTATION: PASS killed=1 survived=0 invalid=0 "
           "unclassified=0 not_run=0 not_applied=0\n")
    r = w3.step()
    check("a failing fix verification with HEAD unchanged → halt for the "
          "coordinator", r.code == 1 and "halt:" in r.out, r.detail())
    w3.commit("coordinator-fix: two")
    r = w3.step()
    check("…and once the coordinator fixed it, the new HEAD is verified again",
          r.kinds() == ["teamlead:verifier"]
          and f"{w3.run}/verifier-fix-2.md" in r.spawns()[0][1], r.detail())


def case_close_applies_ledger(tmp: Path) -> None:
    w = World(tmp, codexCodeReview="off")
    all_approved(w)
    w.put("deferred-rows.md", "| 2026-10-14 | run | item | why | src |\n")
    r = w.step()
    ledger = (f"python3 {PLUGIN}/scripts/ledger.py apply {w.run} --ledger "
              f"{w.repo}/docs/deferred-work.md")
    check("close with deferred rows → the ledger.py apply command, then the report",
          r.code == 0 and ledger in r.commands()
          and r.out.index("ledger.py") < r.out.index("final-report.md")
          and "decisions-log.md" in r.out, r.detail())

    w2 = World(tmp / "none", codexCodeReview="off")
    all_approved(w2)
    r = w2.step()
    check("no deferred rows → no ledger command", "ledger.py" not in r.out,
          r.detail())

    w2.put("final-report.md", "# Final\n")
    r = w2.step()
    check("a written final report → the loop is complete",
          r.code == 0 and "complete" in r.out and not r.kinds(), r.detail())


def case_base_flag_and_baseline_expectation(tmp: Path) -> None:
    w = World(tmp)
    r = w.step()
    check("the baseline verifier is dispatched with a pointer to its output",
          f"expect: {w.run}/baseline-ws1.md" in r.out, r.detail())
    r = w.step("--base", w.base, "--redo")
    check("--base is accepted and the dispatch repeats", r.code == 0 and r.kinds(),
          r.detail())


CASES = [
    case_exit_codes,
    case_kickoff_prints_baseline_verifier,
    case_dependent_stream_waits,
    case_commits_checked_before_verifier,
    case_verifier_spawn_carries_red_run,
    case_implementer_and_reviewer_prompts_have_no_run,
    case_mutation_fail_routes_to_rework,
    case_pass_routes_to_reviewers,
    case_barrier_orders_stages,
    case_halts_only_where_the_user_is_needed,
    case_needs_decision_logged,
    case_docs_only_routes_to_writer,
    case_approved_routes_to_codex_gate,
    case_gate_loops_until_clean,
    case_gate_triage_is_stale_after_new_commits,
    case_gate_rework_shares_cap,
    case_gate_triage_unreadable_or_stop_halts,
    case_gate_docs_only_closes_after_the_writer,
    case_coordinator_fix_reverified,
    case_close_applies_ledger,
    case_base_flag_and_baseline_expectation,
]


def main() -> int:
    for case in CASES:
        with tempfile.TemporaryDirectory() as d:
            try:
                case(Path(d).resolve())
            except (OSError, subprocess.CalledProcessError) as exc:
                check(f"{case.__name__} ran", False, repr(exc))
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            print(f"      {detail}")
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"\n=== {len(results) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
