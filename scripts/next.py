#!/usr/bin/env python3
"""Route a $RUN one phase at a time: wait, read the verdicts, print what to spawn.

    python3 $SKILL/scripts/next.py $RUN [--poll S] [--timeout S] [--redo]
                                        [--base SHA]

One call per phase. The call first waits for what the previous call dispatched
(its `expect:` files, or the Codex gate's attempts log), then reads the run
directory and the git history, and prints the next dispatch: the exact prompts
of the agents to spawn, in one batch, and the commands to run. The coordinator
copies them out; it does not compose a prompt, count a round, judge a cap or
look a commit up. Those are the places a run used to go wrong by hand.

What it decides, from files and git alone (the file set is the state, as in
run_state.py; `next-state.json` only remembers which dispatch it last printed
and the head each Codex gate saw):

  * Before dispatch it prints run_state.plan_next's step. It never invents one.
  * A baseline verifier per workstream at the base SHA, then the implementers.
    A baseline that fails is the pre-existing state; one that CANNOT_RUN halts,
    unless each CANNOT_RUN row is `absent at base: <path>` and git confirms it.
    The base SHA is pinned to `base-sha.txt` on the first call (or `--base`).
  * Stages are a barrier: baseline, implementer, verifier, reviewers, triage,
    writer. The lowest stage any workstream is at is dispatched as one batch,
    so no verifier runs beside a writer. Verifiers are the exception: they move
    HEAD (the RED run) and patch files (the mutation gate) in the one shared
    repo, so they are serialised, lowest workstream first, one per call.
  * The commits a report lists are looked up before a verifier is paid for:
    they must exist, descend from the base and be on HEAD's history.
  * The verifier's prompt carries the RED run (`red_freeze.py --run`, this
    round's RED only) and the mutation gate (`mutate.py`). A PASS whose `head:`
    another stream's rework has since moved past is archived and verified
    again before any reviewer reads it. A verifier FAIL or a
    `MUTATION: FAIL` writes the rework brief and spawns an implementer, never
    reviewers. The RED run appears nowhere else.
  * Reviewer spawns come from review_briefs.py. Triage verdicts route:
    the `recommended:` rows of NEEDS_DECISION and NEEDS_REWORK are logged to
    decisions-log.md, NEEDS_DECISION goes on, a docs brief goes to a writer (its
    commit must say `docs-fix:`) and then to a fresh Codex gate, STOP and an
    unreadable verdict halt.
  * A `cwd:` line in a brief's `## Verification commands` is carried into the
    RED and mutation commands as `(cd <dir> && <cmd>)`; a bad one halts.
  * `reworkCap` counts reworks, ordinary and gate-driven alike (see
    run_state.cap_reached); a rework past it halts.
  * `coordinator-fix:` commits are verified (verifier-fix-<k>.md) before the
    gate. The gate (codexCodeReview) packages the whole diff, waits for
    run_codex_review.py, falls back to the Opus reviewer when Codex failed
    (opusCodeReview), has it triaged, and loops through rework rounds until a
    gate triage at the current HEAD has no blocking row. Then the ledger
    (`ledger.py apply`, when deferred-rows.md exists) and the final report.

Output, one item per line after `RUN=` and `repo=`:
  step: <what this dispatch is>
  spawn: <subagent type> [model=<m>]      then `<<<`, the prompt, `>>>`
  expect: <file the spawn will write>
  run: <command to run now>               run-background: <command, background>
  next: <instruction for the coordinator>
  halt: <why the loop stops>

Exit codes:
  0  dispatch printed (or the loop is complete): carry it out, call again
  1  halt, or the plan needs the user: read the `halt:` / `next:` line
  2  $RUN is not a run directory
  3  the wait timed out; a `RETRY:` line holds the command to call again

`--redo` skips the wait and prints the current dispatch again (the coordinator
died before spawning it). `--poll` and `--timeout` are seconds, as in
wait_for.py. `--base` pins the base SHA.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import current_brief
import run_metrics
import workflow_profile
import archive_reports
import paths
import review_briefs
import run_state
import wait_for
from run_state import Run, cap_reached, verdict

APPROVED_LIKE = ("APPROVED", "APPROVED_WITH_NOTES")
LOGGED = ("NEEDS_DECISION", "NEEDS_REWORK")
STAGES = {"baseline": 0, "implement": 1, "verify": 2, "review": 3,
          "triage": 4, "triage-redo": 4, "writer": 5, "wait": 99}
STAGE_LABEL = {"baseline": "baseline verification", "implement": "implementer",
               "verify": "verifier gate", "review": "reviewers",
               "triage": "triage", "triage-redo": "triage (rework brief missing)",
               "writer": "docs-fix writer"}

SECTION = re.compile(r"^##\s+Verification commands\s*$(.*?)(?=^##\s|\Z)",
                     re.M | re.S)
BULLET = re.compile(r"^\s*[-*]\s+`([^`]+)`\s*$", re.M)
CHECK = re.compile(r"^\s*check:\s*(\S.*?)\s*$", re.M)
BACKTICKED = re.compile(r"`([^`]+)`")
CWD = re.compile(r"^[ \t]*cwd:[ \t]*(\S.*?)[ \t]*$")
COMMITS = re.compile(r"^##\s+Commits\s*$(.*?)(?=^##\s|^```|\Z)", re.M | re.S)
HEX = re.compile(r"\b[0-9a-f]{7,40}\b")
TOUCHED = re.compile(r"touched by these commits:\s*[*`]*\s*(yes|no|unclear)", re.I)
MUTATION = re.compile(r"^MUTATION:\s*(PASS|FAIL)\b", re.M)
DOCS_FIXED = re.compile(r"DOCS_FIXED\s+rows=\d+\s+commit=([0-9a-fA-F]{7,40})")
TERMINAL = re.compile(r"^\S+\s+(done|failed):\s*(.*?)\s*$")
RECOMMENDED = re.compile(r"recommended:\s*(.+)")
SNAPSHOT_HEAD = re.compile(r"^head:\s*`?([0-9a-f]{7,40})\b", re.M)
CANNOT_ROW = re.compile(r"→\s*CANNOT_RUN\(([^)\n]*)\)")
ABSENT = re.compile(r"^absent at base:\s*`?([^`]+?)`?\s*$")
BASELINE_ROW = re.compile(r"^(.*?)\s*→\s*(?:exit\s+(\d+)|TIMEOUT)\b")


class Halt(Exception):
    """The loop stops here: somebody has to act before another call helps."""


@dataclass
class Spawn:
    kind: str
    prompt: str
    expect: Path
    model: str = ""


@dataclass
class BriefCmd:
    """One verification bullet: its text, the `cwd:` in force and where it sits."""
    text: str
    cwd: str
    cwd_line: int
    brief: Path


@dataclass
class Need:
    kind: str
    ws: int
    rnd: int

    @property
    def rank(self) -> int:
        return STAGES[self.kind]


@dataclass
class Plan:
    step: str = ""
    spawns: list[Spawn] = field(default_factory=list)
    cmds: list[tuple[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    halt: str = ""
    code: int = 0
    expects: list[Path] = field(default_factory=list)
    rewritten: dict[str, int] = field(default_factory=dict)
    gate_log: str = ""
    gate_seen: int = 0
    state: dict[str, object] = field(default_factory=dict)


def as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def as_int(value: object) -> int:
    return value if isinstance(value, int) else 0


def terminals(log: Path) -> list[tuple[str, str]]:
    """The `done:` / `failed:` lines of a run_codex_review.py attempts log."""
    try:
        lines = log.read_text(errors="replace").splitlines()
    except OSError:
        return []
    return [(m.group(1), m.group(2)) for ln in lines if (m := TERMINAL.match(ln))]


def q(path: Path) -> str:
    """A path as one shell word."""
    return shlex.quote(str(path))


def clean(row: str) -> str:
    return re.sub(r"[\s|]+$", "", row).strip()


class Router:
    def __init__(self, run: Path, args: argparse.Namespace) -> None:
        self.run = run
        self.args = args
        self.r = Run(run)
        self.repo = Path(self.r.text("repo.txt").strip())
        self.plugin = paths.plugin_root()
        self.state_path = run / "next-state.json"
        self.state = self.load_state()

    # --- state ---------------------------------------------------------------

    def load_state(self) -> dict[str, object]:
        try:
            return as_dict(json.loads(self.state_path.read_text()))
        except (OSError, ValueError):
            return {}

    def save_state(self) -> None:
        self.state_path.write_text(json.dumps(self.state, indent=2) + "\n")

    # --- git -----------------------------------------------------------------

    def git(self, *args: str) -> tuple[int, str]:
        proc = subprocess.run(["git", "-C", str(self.repo), *args],
                              capture_output=True, text=True, check=False)
        return proc.returncode, proc.stdout.strip()

    def head(self) -> str:
        return self.git("rev-parse", "HEAD")[1]

    def resolve(self, ref: str) -> str:
        code, out = self.git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
        return out if code == 0 else ""

    def is_ancestor(self, older: str, newer: str) -> bool:
        return self.git("merge-base", "--is-ancestor", older, newer)[0] == 0

    def subject(self, sha: str) -> str:
        return self.git("log", "-1", "--format=%s", sha)[1]

    def between(self, older: str, newer: str) -> list[tuple[str, str]]:
        """(sha, subject) for older..newer, oldest first."""
        code, out = self.git("log", "--reverse", "--format=%H%x09%s",
                             f"{older}..{newer}")
        if code != 0:
            return []
        rows = [ln.split("\t", 1) for ln in out.splitlines() if ln]
        return [(row[0], row[1] if len(row) > 1 else "") for row in rows]

    def base(self) -> str:
        """The SHA every commit of this run descends from, pinned on first use."""
        pin = self.run / "base-sha.txt"
        given = self.args.base
        if given:
            sha = self.resolve(given)
            if not sha:
                raise Halt(f"--base {given} is not a commit of {self.repo}")
            pin.write_text(sha + "\n")
            return sha
        words = pin.read_text().split() if pin.exists() else []
        if words:
            sha = self.resolve(words[0])
            if not sha:
                raise Halt(f"{pin} names {words[0]}, which git does not have")
            return sha
        if any(self.r.report(ws, 1) for ws in self.r.roster):
            raise Halt(f"{pin.name} is missing but implementers have already "
                       "reported: pass --base <sha of the commit before the "
                       "first implementer commit>")
        sha = self.head()
        if not sha:
            raise Halt(f"{self.repo} has no HEAD to pin as the base")
        pin.write_text(sha + "\n")
        return sha

    # --- reading the run -----------------------------------------------------

    def routing(self, ws: int) -> str:
        m = re.search(rf"^WS-{ws}\s*\|.*$", self.r.text("questions.md"), re.M)
        return m.group(0) if m else ""

    def deps(self, ws: int) -> list[int]:
        m = re.search(r"deps:\s*([^|]*)", self.routing(ws))
        return [int(n) for n in re.findall(r"WS-(\d+)", m.group(1))] if m else []

    def tags(self, ws: int) -> dict[str, str]:
        """input/hot/public for one stream; unknown means yes (more review)."""
        line = self.routing(ws)
        validation = (self.r.text("plan-validation.md") + "\n"
                      + self.r.text(run_state.TAG_UPGRADES))
        out = {}
        for tag in ("input", "hot", "public"):
            m = re.search(rf"\b{tag}:\s*(yes|no)\b", line)
            val = m.group(1) if m else "yes"
            # The validator may upgrade a tag, never downgrade one.
            if val == "no" and re.search(
                    rf"WS-{ws}\b[^\n]*\b{tag}:\s*no\b[^\n]*requires\s+{tag}:\s*yes",
                    validation):
                val = "yes"
            out[tag] = val
        return out

    def settled(self, ws: int, rnd: int) -> str:
        """Settled decisions for the reviewer briefs: the coordinator's file,
        else the user's binding answers, else none."""
        own = self.run / f"settled-{self.r.tag(ws, rnd)}.md"
        if own.exists():
            return (own.read_text(errors="replace") + "\n"
                    + current_brief.decision_text(self.run))
        m = re.search(r"^##\s+Answers\s*$(.*?)(?=^##\s|\Z)",
                      self.r.text("questions.md"), re.M | re.S)
        answers = m.group(1).strip() if m else ""
        return answers + "\n" + current_brief.decision_text(self.run)

    @staticmethod
    def section_commands(brief: Path, text: str, sec: re.Match[str]) -> list[BriefCmd]:
        """The bullets of a section, each with the `cwd:` line above it."""
        first = text.count("\n", 0, sec.start(1)) + 1
        found: list[BriefCmd] = []
        cwd, cwd_line = "", 0
        for i, ln in enumerate(sec.group(1).split("\n")):
            if m := CWD.match(ln):
                value = m.group(1)
                span = BACKTICKED.match(value)
                cwd = span.group(1).strip() if span else value.strip("`").strip()
                cwd_line = first + i
            elif m := BULLET.match(ln):
                found.append(BriefCmd(m.group(1), cwd, cwd_line, brief))
        return found

    def brief_commands(self, ws: int, rnd: int) -> tuple[list[BriefCmd], str, str]:
        """(commands, check command, the whole section) of one impl brief.

        A rework brief may omit the section: the nearest earlier one has it."""
        for k in range(rnd, 0, -1):
            brief = self.r.brief(ws, k)
            try:
                text = brief.read_text(errors="replace")
            except OSError:
                continue
            sec = SECTION.search(text)
            cmds = self.section_commands(brief, text, sec) if sec else []
            if sec and cmds:
                chk = CHECK.search(sec.group(1))
                return cmds, chk.group(1) if chk else "", sec.group(0).strip()
        raise Halt(f"impl-ws{ws}-r{rnd}.md and the rounds before it have no "
                   "`## Verification commands` bullets (- `<command>`): the "
                   "verifier would have nothing to run")

    def absent_at_base(self, baseline: Path) -> bool:
        """Whether every CANNOT_RUN row of a clean baseline is a path git
        confirms is missing at the base: a directory or file the run creates."""
        text = baseline.read_text(errors="replace")
        reasons = CANNOT_ROW.findall(text)
        if not reasons or not re.search(r"^tree:\s*CLEAN\b", text, re.M):
            return False
        repo, base = self.repo.resolve(), self.base()
        for reason in reasons:
            m = ABSENT.match(reason.strip())
            if not m:
                return False
            path = (repo / m.group(1).strip()).resolve()
            if path != repo and repo not in path.parents:
                return False
            rel = path.relative_to(repo).as_posix()
            if rel == "." or self.git("cat-file", "-e", f"{base}:{rel}")[0] == 0:
                return False
        return True

    def cwd_dir(self, cmd: BriefCmd) -> Path:
        """The directory a bullet runs in, symlinks resolved; the repo for none."""
        repo = self.repo.resolve()
        return (repo / cmd.cwd).resolve() if cmd.cwd else repo

    def effective(self, cmd: BriefCmd, strict: bool) -> str:
        """The command as it runs: raw at the repo root, `(cd <dir> && <cmd>)`
        elsewhere. `strict` halts on a directory that is not inside the repo."""
        repo, where = self.repo.resolve(), self.cwd_dir(cmd)
        if strict and (not where.is_dir() or (where != repo
                                              and repo not in where.parents)):
            raise Halt(
                f"{cmd.brief.name} line {cmd.cwd_line}: `cwd: {cmd.cwd}` is not an "
                f"existing directory inside {self.repo}. Dispatch a planner Fix for "
                f"line {cmd.cwd_line} of {cmd.brief} (point it at a directory that "
                "exists, or that the brief's scope creates) and call next.py "
                "again; no user question is needed")
        return cmd.text if where == repo else \
            f"(cd {shlex.quote(str(where))} && {cmd.text})"

    def effective_commands(self, ws: int, rnd: int, strict: bool
                           ) -> tuple[list[str], str, list[str]]:
        """(effective commands, check command, row labels) of one impl brief.

        The labels are the effective commands, and only when one has a cwd."""
        cmds, check, _ = self.brief_commands(ws, rnd)
        effs = [self.effective(c, strict) for c in cmds]
        cwd = any(c.text != e for c, e in zip(cmds, effs))
        return effs, check, effs if cwd else []

    def mutation(self, ws: int, rnd: int) -> str:
        return self.mutation_file(self.run / f"mutation-{self.r.tag(ws, rnd)}.md")

    @staticmethod
    def mutation_file(path: Path) -> str:
        try:
            found = MUTATION.findall(path.read_text(errors="replace"))
        except OSError:
            return ""
        return found[-1] if found else ""

    @staticmethod
    def pre_existing(ver: Path) -> bool:
        touched = TOUCHED.findall(ver.read_text(errors="replace"))
        return bool(touched) and all(t.lower() == "no" for t in touched)

    def gate_commands(self, ws: int, cmds: list[str]) -> list[str]:
        """The brief commands that do not already fail in baseline-ws<N>.md.

        A command that fails at the base fails every mutant's run, so keeping it
        in mutate.py's --cmd would report every mutant killed over nothing."""
        rows = self.r.text(f"baseline-ws{ws}.md").splitlines()
        failing = {m.group(1) for ln in rows
                   if (m := BASELINE_ROW.match(ln)) and m.group(2) != "0"}
        passing = [c for c in cmds if c not in failing]
        if not passing:
            raise Halt(f"every verification command of WS-{ws} already fails in "
                       f"baseline-ws{ws}.md, so the mutation gate has no command "
                       "that could tell a killed mutant from a broken base: fix "
                       "the base or the brief's commands")
        return passing

    def gate_driven(self, ws: int, rnd: int) -> bool:
        """Whether round `rnd` was asked for by the gate, not by stream review.

        A round after an approved triage can only have come from the Codex gate.
        A round after a rework verdict is stream rework; one after a verifier
        FAIL (no triage yet) inherits what the round before it was.
        """
        if rnd <= 1:
            return False
        tri = self.r.phase_file("triage", ws, rnd - 1)
        if tri is None:
            return self.gate_driven(ws, rnd - 1)
        return verdict(tri) in APPROVED_LIKE

    def log_decisions(self, tri: Path) -> None:
        """Append a NEEDS_DECISION triage's `recommended:` rows, once each."""
        log = self.run / "decisions-log.md"
        existing = log.read_text(errors="replace") if log.exists() else ""
        rows = [f"- {tri.name}: {clean(m)}" for m in
                RECOMMENDED.findall(tri.read_text(errors="replace")) if clean(m)]
        new = [row for row in rows if row not in existing]
        if new:
            head = existing if existing else "# Decisions log\n\n"
            log.write_text(head.rstrip("\n") + "\n" + "\n".join(new) + "\n")

    def log_earlier_decisions(self, ws: int, rnd: int) -> None:
        for k in range(1, rnd):
            tri = self.r.phase_file("triage", ws, k)
            if tri is not None and verdict(tri) in LOGGED:
                self.log_decisions(tri)

    def log_gate_decisions(self) -> None:
        for tri in sorted(self.run.glob("triage-gate-r*.md")):
            if verdict(tri) in LOGGED:
                self.log_decisions(tri)

    # --- commits -------------------------------------------------------------

    def listed_commits(self, rep: Path) -> list[str]:
        text = rep.read_text(errors="replace")
        sec = COMMITS.search(text)
        found: list[str] = []
        if sec:
            for ln in sec.group(1).splitlines():
                m = re.match(r"^[\s\-*`]*([0-9a-f]{7,40})\b", ln)
                if m:
                    found.append(m.group(1))
        if not found:
            lines = [ln for ln in text.splitlines() if ln.startswith("commits:")]
            if lines:
                found = HEX.findall(lines[-1])
        return found

    def check_commits(self, rep: Path) -> list[str]:
        """The report's commits as full SHAs, or a Halt naming the bad one."""
        listed = self.listed_commits(rep)
        if not listed:
            raise Halt(f"{rep.name} lists no commits (## Commits or `commits:`)")
        base, head = self.base(), self.head()
        full: list[str] = []
        for tok in listed:
            sha = self.resolve(tok)
            if not sha:
                raise Halt(f"{rep.name} lists {tok}, which git does not have")
            if sha == base or not self.is_ancestor(base, sha):
                raise Halt(f"{rep.name} lists {tok}, which does not descend from "
                           f"the base {base[:9]}")
            if not self.is_ancestor(sha, head):
                raise Halt(f"{rep.name} lists {tok}, which is not on HEAD's "
                           f"history ({head[:9]})")
            if sha not in full:
                full.append(sha)
        return full

    def red_hashes(self, rep: Path) -> list[str]:
        found: list[str] = []
        for ln in rep.read_text(errors="replace").splitlines():
            m = re.match(r"^red:\s*(.*)$", ln)
            if m:
                found += [s for tok in HEX.findall(m.group(1))
                          if (s := self.resolve(tok))]
        return found

    def new_reds(self, ws: int, rnd: int, rep: Path) -> list[str]:
        """This round's RED commits: an earlier round's predates its tests."""
        earlier: set[str] = set()
        for k in range(1, rnd):
            prior = self.r.report(ws, k)
            if prior is not None:
                earlier.update(self.red_hashes(prior))
        out: list[str] = []
        for sha in self.red_hashes(rep):
            if sha not in earlier and sha not in out:
                out.append(sha)
        return out

    def check_docs_fix(self, out: Path) -> None:
        found = DOCS_FIXED.findall(out.read_text(errors="replace"))
        if not found:
            raise Halt(f"{out.name} has no `DOCS_FIXED rows=<n> commit=<sha>` line")
        sha = self.resolve(found[-1])
        if not sha:
            raise Halt(f"{out.name} names commit {found[-1]}, which git lacks")
        base = self.base()
        if sha == base or not self.is_ancestor(base, sha) \
                or not self.is_ancestor(sha, self.head()):
            raise Halt(f"{out.name}: commit {sha[:9]} is not between the base and "
                       "HEAD")
        subject = self.subject(sha)
        if not subject.startswith("docs-fix:"):
            raise Halt(f"{out.name}: commit {sha[:9]} has the subject {subject!r}; "
                       "a docs-only writer's subject starts with `docs-fix:`, so "
                       "this one changed something it was not allowed to")

    # --- one stream ----------------------------------------------------------

    def cap_msg(self, rnd: int) -> str:
        return (f"rework cap reached: round {rnd} still needs rework past a cap of "
                f"{self.r.cap}, so the plan or the spec is wrong, not the coder. "
                "STOP and take it to the user")

    def analyse(self, ws: int, seen: tuple[int, ...] = ()) -> Need | None:
        """What this stream needs next, or None once it is settled."""
        r = self.r
        rnd = r.round_of(ws)
        if rnd > 1 and cap_reached(rnd - 1, r.cap):
            raise Halt(self.cap_msg(rnd - 1))
        self.log_earlier_decisions(ws, rnd)
        rep = r.report(ws, rnd)
        if rep is None:
            if rnd == 1:
                baseline = self.run / f"baseline-ws{ws}.md"
                if not baseline.exists():
                    return Need("baseline", ws, 1)
                if (verdict(baseline) == "CANNOT_RUN"
                        and not self.absent_at_base(baseline)):
                    raise Halt(f"{baseline.name} is CANNOT_RUN: the verification "
                               "commands cannot run at the base, which is an "
                               "environment problem, not a code failure (a row "
                               "`CANNOT_RUN(absent at base: <path>)` for a path "
                               "the run creates does not stop it)")
                for dep in self.deps(ws):
                    if dep in r.roster and dep != ws and (
                            dep in seen
                            or self.analyse(dep, seen + (ws,)) is not None):
                        return Need("wait", ws, rnd)
            return Need("implement", ws, rnd)
        st = verdict(rep)
        if st in ("BLOCKED", "PARTIAL"):
            raise Halt(f"{rep.name} is {st.lower()}: its one question is yours to "
                       "resolve, with the user if the spec is what is unclear")
        if not st:
            raise Halt(f"{rep.name} has no `status:` line, so nothing can route on "
                       "it")
        ver = r.phase_file("verifier", ws, rnd)
        if ver is None:
            self.check_commits(rep)
            return Need("verify", ws, rnd)
        tri = r.phase_file("triage", ws, rnd)
        if tri is None:
            return self.after_verifier(ws, rnd, rep, ver)
        tv = verdict(tri)
        if not tv:
            raise Halt(f"{tri.name} has no `VERDICT:` line: decide the verdict "
                       "yourself and append it, then call again")
        if tv == "STOP":
            raise Halt(f"{tri.name} says STOP: read it and take it to the user")
        docs = self.run / "briefs" / f"docs-ws{ws}-r{rnd}.md"
        if tv in LOGGED:
            self.log_decisions(tri)
        if tv == "NEEDS_DECISION":
            tv = "NEEDS_REWORK" if docs.exists() else "APPROVED_WITH_NOTES"
        if tv != "NEEDS_REWORK":
            return None
        if docs.exists():
            out = self.run / f"docs-fix-ws{ws}-r{rnd}.md"
            if not out.exists():
                return Need("writer", ws, rnd)
            self.check_docs_fix(out)
            return None
        if cap_reached(rnd, r.cap):
            raise Halt(self.cap_msg(rnd))
        return Need("triage-redo", ws, rnd)

    def after_verifier(self, ws: int, rnd: int, rep: Path,
                       ver: Path) -> Need | None:
        outcome = verdict(ver)
        if outcome == "CANNOT_RUN":
            raise Halt(f"{ver.name} is CANNOT_RUN: an environment problem, not a "
                       "code failure. Fix the command in the brief or ask the user")
        if outcome not in ("PASS", "FAIL"):
            raise Halt(f"{ver.name} has no `OUTCOME:` line")
        mut = self.mutation(ws, rnd)
        if mut == "FAIL" or (outcome == "FAIL" and not self.pre_existing(ver)):
            return self.rework(ws, rnd, rep, ver)
        if not mut:
            raise Halt(f"{ver.name} is {outcome} but there is no `MUTATION:` line "
                       f"in mutation-{self.r.tag(ws, rnd)}.md: the mutation gate "
                       "did not run, and a pass without it measures nothing")
        if self.gate_driven(ws, rnd):
            return None
        adaptive = workflow_profile.selection(self.run)[0] == "adaptive"
        snapshot = SNAPSHOT_HEAD.search(ver.read_text(errors="replace"))
        adaptive_stale = (adaptive and snapshot is not None
                          and self.resolve(snapshot.group(1)) != self.head())
        if adaptive_stale or self.stale(ws, rnd, ver):
            # Another stream's rework moved HEAD after this report: reviewers
            # would stop on its `head:`, so verify the new HEAD first.
            try:
                archive_reports.archive_reports(self.run, [ver])
            except (OSError, ValueError) as exc:
                raise Halt(f"{ver.name} names an earlier HEAD and could not be "
                           f"archived: {exc}") from exc
            return Need("verify", ws, rnd)
        if adaptive:
            if outcome != "PASS" or not snapshot:
                return self.review_need(ws, rnd)
            return None
        return self.review_need(ws, rnd)

    def stale(self, ws: int, rnd: int, ver: Path) -> bool:
        """The report's `head:` is not HEAD, and no reviewer was sent yet."""
        tag = self.r.tag(ws, rnd)
        if (self.run / "briefs" / f"review-{tag}-code.md").exists():
            return False
        m = SNAPSHOT_HEAD.search(ver.read_text(errors="replace"))
        return bool(m) and self.resolve(m.group(1)) != self.head()

    def rework(self, ws: int, rnd: int, rep: Path, ver: Path) -> Need | None:
        """A failed gate is a rework: write the brief, then the round after."""
        if cap_reached(rnd, self.r.cap):
            raise Halt(self.cap_msg(rnd))
        nxt = self.r.brief(ws, rnd + 1)
        if not nxt.exists():
            _, _, section = self.brief_commands(ws, rnd)
            tag = self.r.tag(ws, rnd)
            nxt.parent.mkdir(exist_ok=True)
            nxt.write_text(
                f"# Implementer brief — WS-{ws} — round {rnd + 1}\n\n"
                f"Rework after the verification gate of round {rnd}. Written by "
                "next.py; follow \"## Rework rounds\" in your role file.\n\n"
                "## Inputs\n\n"
                f"- Previous brief: $RUN/briefs/{self.r.brief(ws, rnd).name} (goal, "
                "scope fence and acceptance carry over unchanged)\n"
                f"- Previous report: $RUN/{rep.name}\n"
                f"- Verifier report: $RUN/{ver.name} (the FAIL commands, with "
                "their output)\n"
                f"- Mutation report: $RUN/mutation-{tag}.md (every SURVIVED or NOT "
                "APPLIED row is a test that pins nothing)\n\n"
                "## What to fix\n\n"
                "Make every command in the verifier report pass and kill every "
                "non-equivalent mutant with an observable requirement. Investigate "
                "invalid or equivalent mutations before prescribing tests. Do not "
                "change assertions merely to match a suggested fix.\n\n"
                + section + "\n")
        cause = "mutation" if self.mutation(ws, rnd) == "FAIL" else "verification"
        run_metrics.event(self.run, "rework", f"ws{ws}-r{rnd + 1}",
                          cause, ver.name)
        return self.analyse(ws)

    def review_need(self, ws: int, rnd: int) -> Need:
        tag = self.r.tag(ws, rnd)
        code_brief = self.run / "briefs" / f"review-{tag}-code.md"
        missing = [a for a in self.r.axes(ws, rnd)
                   if not self.r.phase_file("review", ws, rnd, f"-{a}")]
        if not code_brief.exists() or missing:
            return Need("review", ws, rnd)
        return Need("triage", ws, rnd)

    # --- prompts -------------------------------------------------------------

    def head_line(self) -> str:
        return f"$RUN = {self.run}. Repo: {self.repo}."

    def infix_line(self) -> str:
        if self.r.multi:
            return "Several workstreams share this run: use the ws<N>- infix."
        return "One workstream in this run: no ws<N>- infix."

    def implementer(self, ws: int, rnd: int) -> Spawn:
        out = self.run / f"implementer-{self.r.tag(ws, rnd)}.md"
        view = current_brief.write(self.run, ws, rnd)
        if rnd > 1 and not any(
                e["kind"] == "rework" and e["id"] == f"ws{ws}-r{rnd}"
                for e in run_metrics.read(self.run)["events"]):
            cause = re.search(r"^rework cause:\s*(.+)$",
                              self.r.brief(ws, rnd).read_text(), re.M)
            run_metrics.event(self.run, "rework", f"ws{ws}-r{rnd}",
                              cause.group(1) if cause else
                              "review finding; detailed attribution unavailable",
                              self.r.brief(ws, rnd).name)
        lines = [
            self.head_line(),
            f"Workstream: WS-{ws} ({review_briefs.ws_name(self.r, ws)}). Round: "
            f"{rnd}. Your brief: {self.r.brief(ws, rnd)}. "
            f"Read the current view {view} first; it includes inherited constraints "
            "and current decisions. Earlier files remain the audit trail.",
        ]
        if rnd >= 2:
            lines.append("This is a rework round — follow \"## Rework rounds\"; the "
                         "brief points at the previous brief, report and findings.")
        lines.append(f"Output: write {out} ENDING with the fenced status block, "
                     "and repeat that block + the file line as your reply.")
        if self.r.multi:
            lines.append("Others work in this tree on other workstreams — stage "
                         "only your files by path (never git add -A), never touch "
                         "files outside your scope.")
        return Spawn("teamlead:implementer", "\n".join(lines), out)

    @staticmethod
    def label_lines(labels: list[str]) -> list[str]:
        if not labels:
            return []
        return ["Some commands run from another directory. Write each command's "
                "exact string below as the row's `<command>` under `## Commands`:",
                *[f"- {c}" for c in labels]]

    def baseline(self, ws: int) -> Spawn:
        base, head = self.base(), self.head()
        out = self.run / f"baseline-ws{ws}.md"
        try:
            labels = self.effective_commands(ws, 1, False)[2]
        except Halt:
            labels = []
        prompt = "\n".join([
            self.head_line(),
            f"Workstream: WS-{ws}. Baseline check before any implementer has "
            f"started: the base SHA is {base}.",
            f"Expected HEAD: {head}.",
            f"Inputs: {self.r.brief(ws, 1)} (## Verification commands), "
            f"{self.run}/repo.txt.",
            "Run the brief's verification commands exactly as your role file says. "
            "Run no RED run and no mutation gate: nothing is implemented yet. A "
            "failure here is pre-existing; it is the baseline later rounds are "
            "compared against. A command that cannot run only because a "
            "directory or file the run's workstreams will create is absent at "
            "the base gets the row `<command> → CANNOT_RUN(absent at base: "
            "<repo-relative path>)`; next.py checks that path against the base.",
            *self.label_lines(labels),
            f"Output: write {out} in the verifier report shape (OUTCOME: PASS | "
            "FAIL | CANNOT_RUN), return the OUTCOME block + file line.",
        ])
        return Spawn("teamlead:verifier", prompt, out)

    def script(self, name: str) -> str:
        """`python3 <plugin>/scripts/<name>`, the path one shell word."""
        return f"python3 {q(self.plugin / 'scripts' / name)}"

    def verifier_commands(self, cmd: str, check: str, base: str, commits: list[str],
                          out: Path, reds: list[str]) -> list[str]:
        lines: list[str] = []
        if reds:
            lines.append(f"{self.script('red_freeze.py')} --repo {q(self.repo)} "
                         f"--run {shlex.quote(cmd)} " + " ".join(reds))
        probes = out.with_name(out.name.replace("mutation-", "probes-")
                               .replace(".md", ".json"))
        lines.append(
            f"{self.script('mutate.py')} --repo {q(self.repo)} --base {base} "
            f"--cmd {shlex.quote(cmd)} --commits {' '.join(commits)}"
            + (f" --check-cmd {shlex.quote(check)}" if check else "")
            + (f" --probes {q(probes)}" if probes.exists() else "")
            + f" --out {q(out)}")
        return lines

    def verifier_prompt(self, ws: int, rnd: int, commands: str, check: str,
                        commits: list[str], reds: list[str], out: Path,
                        mutation_out: Path, inputs: str, label: str,
                        labels: list[str]) -> str:
        base = self.base()
        steps = self.verifier_commands(commands, check, base, commits,
                                       mutation_out, reds)
        n = 1
        extra: list[str] = []
        if reds:
            extra.append(f"{n}. RED run — quote its output under `## RED run`:\n"
                         f"   {steps[0]}")
            n += 1
        extra.append(f"{n}. Mutation gate — run it after every command that is not "
                     "pre-existing passed, quote its last `MUTATION:` line under "
                     "`## Mutation`:\n"
                     f"   {steps[-1]}")
        baseline = self.run / f"baseline-ws{ws}.md"
        lines = [
            self.head_line(),
            label,
            f"Expected HEAD: {self.head()}. Base: {base}.",
            inputs,
            f"Baseline at the base: {baseline}. Compare the failure and affected "
            "callers; old code newly exposed by this change is still a regression.",
            *self.label_lines(labels),
            "After the brief's commands, run these in order, from the repo, while "
            "no writer is active (they move HEAD and restore it):",
            *extra,
            f"Output: write {out}, return the OUTCOME block + file line. "
            "mutate.py writes the mutation report itself; do not edit it.",
        ]
        return "\n".join(lines)

    def verifier(self, ws: int, rnd: int) -> Spawn:
        rep = self.r.report(ws, rnd)
        assert rep is not None
        cmds, check, labels = self.effective_commands(ws, rnd, True)
        commits = self.check_commits(rep)
        tag = self.r.tag(ws, rnd)
        out = self.run / f"verifier-{tag}.md"
        prompt = self.verifier_prompt(
            ws, rnd, " && ".join(self.gate_commands(ws, cmds)), check, commits,
            self.new_reds(ws, rnd, rep),
            out, self.run / f"mutation-{tag}.md",
            f"Inputs: {self.r.brief(ws, rnd)} (## Verification commands), "
            f"{rep} (commits:), {self.run}/repo.txt.",
            f"Workstream: WS-{ws}. Round: {rnd}. {self.infix_line()}", labels)
        return Spawn("teamlead:verifier", prompt, out)

    def reviewers(self, ws: int, rnd: int) -> list[Spawn]:
        rep = self.r.report(ws, rnd)
        assert rep is not None
        commits = " ".join(self.check_commits(rep))
        lines = review_briefs.write_briefs(
            self.run, ws, rnd, self.tags(ws), commits, self.settled(ws, rnd))
        out: list[Spawn] = []
        for line in lines:
            axis, how = line.split()[:2]
            if how == "skip":
                continue
            fields = dict(p.split("=", 1) for p in line.split() if "=" in p)
            expect = self.run / f"review-{self.r.tag(ws, rnd)}-{axis}.md"
            if self.r.phase_file("review", ws, rnd, f"-{axis}"):
                continue
            kind = re.search(r"type=(\S+)", line)
            out.append(Spawn(kind.group(1) if kind else "code-review",
                             f"Read and follow {fields['brief']}.", expect,
                             fields.get("model", "")))
        return out

    def triage_prompt(self, ws: int, rnd: int, redo: bool) -> Spawn:
        tag = self.r.tag(ws, rnd)
        reviews = [self.r.phase_file("review", ws, rnd, f"-{a}")
                   for a in self.r.axes(ws, rnd)]
        prev = self.r.phase_file("triage", ws, rnd - 1) if rnd > 1 else None
        out = self.run / f"triage-{tag}.md"
        nxt = self.r.brief(ws, rnd + 1)
        lines = [
            self.head_line(),
            f"Workstream: WS-{ws}. Round: {rnd}. {self.infix_line()}",
            "Reviews: " + ", ".join(str(p) for p in reviews if p) + ". Previous "
            f"triage: {prev if prev else 'none in round 1'}.",
            f"Current decisions: {current_brief.write_decisions(self.run)}. "
            "Preserve fix/decline/defer decisions unless new evidence changes them.",
            f"Rework count before this round: {rnd - 1}. reworkCap: {self.r.cap}.",
            f"Output: write {out} and, on NEEDS_REWORK, {nxt}; return the "
            "two-line VERDICT block.",
        ]
        if redo:
            lines.insert(3, f"{out.name} already says NEEDS_REWORK but {nxt} "
                         "does not exist: write the rework brief now (or change "
                         "the verdict if there is nothing to rework).")
        return Spawn("teamlead:triage", "\n".join(lines),
                     nxt if redo else out)

    def writer(self, ws: int, rnd: int) -> Spawn:
        brief = self.run / "briefs" / f"docs-ws{ws}-r{rnd}.md"
        out = self.run / f"docs-fix-ws{ws}-r{rnd}.md"
        prompt = "\n".join([
            self.head_line(),
            f"Workstream: WS-{ws}. Round: {rnd}. Your brief: {brief} — read it in "
            "full first.",
            "Make only the documentation changes it lists. Commit them in ONE "
            "commit whose subject starts with `docs-fix:`, staging only your "
            "files by path (never git add -A).",
            f"Output: write {out} ending with `DOCS_FIXED rows=<n> commit=<sha>`; "
            "return that line + the file line.",
        ])
        return Spawn("teamlead:writer", prompt, out)

    # --- one dispatch --------------------------------------------------------

    def stream_plan(self) -> Plan | None:
        """The batch of the lowest stage any stream is at, or None if all settled."""
        needs = [n for ws in self.r.roster if (n := self.analyse(ws))]
        if not needs:
            return None
        active = [n for n in needs if n.kind != "wait"]
        if not active:
            raise Halt("every unsettled workstream waits on another: the deps: "
                       "lines in questions.md form a cycle")
        low = min(n.rank for n in active)
        batch = [n for n in active if n.rank == low]
        shared_database = batch[0].kind == "baseline" and any(
            "verification resource: shared-database" in
            self.r.brief(n.ws, n.rnd).read_text()
            for n in batch)
        if batch[0].kind == "verify" or shared_database:
            batch = batch[:1]
        plan = Plan(step=f"{batch[0].kind} — " + ", ".join(
            f"WS-{n.ws} round {n.rnd}" for n in batch))
        plan.step = f"{STAGE_LABEL[batch[0].kind]} — " + ", ".join(
            f"WS-{n.ws} round {n.rnd}" for n in batch)
        for n in batch:
            if n.kind == "baseline":
                plan.spawns.append(self.baseline(n.ws))
            elif n.kind == "implement":
                plan.spawns.append(self.implementer(n.ws, n.rnd))
            elif n.kind == "verify":
                plan.spawns.append(self.verifier(n.ws, n.rnd))
            elif n.kind == "review":
                plan.spawns += self.reviewers(n.ws, n.rnd)
            elif n.kind == "triage":
                plan.spawns.append(self.triage_prompt(n.ws, n.rnd, False))
            elif n.kind == "triage-redo":
                plan.spawns.append(self.triage_prompt(n.ws, n.rnd, True))
            elif n.kind == "writer":
                plan.spawns.append(self.writer(n.ws, n.rnd))
        if any(s.kind == "security-review" for s in plan.spawns):
            plan.notes.append("security-review may not be a registered agent type: "
                              "use general-purpose with the same model and prompt "
                              "if the spawn is refused")
        return plan

    # --- coordinator edits ---------------------------------------------------

    def all_commands(self) -> tuple[list[str], str, list[str]]:
        cmds: list[str] = []
        labels: list[str] = []
        check = ""
        for ws in self.r.roster:
            c, ck, lab = self.effective_commands(ws, self.r.round_of(ws), True)
            cmds += [x for x in self.gate_commands(ws, c) if x not in cmds]
            labels += [x for x in lab if x not in labels]
            check = check or ck
        return cmds, check, labels

    def fix_plan(self) -> Plan | None:
        """Verify commits the coordinator made itself, before the gate (D17)."""
        base, head = self.base(), self.head()
        fixes = [c for c, s in self.between(base, head)
                 if s.startswith("coordinator-fix:")]
        if not fixes:
            return None
        recs = [as_dict(x) for x in self.state.get("fixes", [])
                if isinstance(self.state.get("fixes"), list)]
        passed = ""
        for rec in recs:
            k = as_int(rec.get("k"))
            ver = self.run / f"verifier-fix-{k}.md"
            if verdict(ver) == "PASS" and self.mutation_file(
                    self.run / f"mutation-fix-{k}.md") == "PASS":
                passed = str(rec.get("head", ""))
        todo = [c for c in fixes if not (passed and self.is_ancestor(c, passed))]
        if not todo:
            return None
        k = len(recs) + 1
        if recs:
            last = recs[-1]
            lk = as_int(last.get("k"))
            if (self.run / f"verifier-fix-{lk}.md").exists():
                if last.get("head") == head:
                    raise Halt(f"verifier-fix-{lk}.md did not pass and HEAD has "
                               "not moved: fix the coordinator-fix commit (or its "
                               "tests), commit, and call again")
            else:
                k = lk
        cmds, check, labels = self.all_commands()
        out = self.run / f"verifier-fix-{k}.md"
        prompt = self.verifier_prompt(
            0, 0, " && ".join(cmds), check, todo, [], out,
            self.run / f"mutation-fix-{k}.md",
            f"Inputs: the `## Verification commands` of every brief in "
            f"{self.run}/briefs/ (latest round), {self.run}/repo.txt. The commits "
            "under test were made by the coordinator after the streams were "
            "approved.",
            f"Coordinator fix verification {k}. {self.infix_line()}", labels)
        plan = Plan(step=f"verifier gate — coordinator-fix commits (verification {k})")
        plan.spawns.append(Spawn("teamlead:verifier", prompt, out))
        plan.state["fixes"] = [*[dict(x) for x in recs[:k - 1]],
                               {"k": k, "head": head}]
        return plan

    # --- the Codex gate ------------------------------------------------------

    def gates(self) -> dict[str, object]:
        return as_dict(self.state.get("gates"))

    def gate_record(self, g: int) -> dict[str, object]:
        return as_dict(self.gates().get(str(g)))

    def last_gate_triage(self) -> int:
        found = [int(m.group(1)) for p in self.run.glob("triage-gate-r*.md")
                 if (m := re.match(r"triage-gate-r(\d+)\.md$", p.name))]
        return max(found) if found else 0

    def set_gate(self, plan: Plan, g: int, **rec: object) -> None:
        gates = dict(self.gates())
        gates[str(g)] = {**self.gate_record(g), **rec}
        plan.state["gates"] = gates

    def gate_review_path(self, g: int) -> str:
        rec = self.gate_record(g)
        if rec.get("review"):
            return str(rec["review"])
        pkg = self.run / "codex-gate-package"
        seen = as_int(rec.get("attempts_seen"))
        new = terminals(pkg / "codex-gate-attempts.log")[seen:]
        if new and new[-1][0] == "done":
            return new[-1][1]
        opus = pkg / f"opus-review-r{g}.md"
        return str(opus) if opus.exists() else ""

    def require_gate_complete(self, review: str) -> None:
        path = Path(review)
        text = path.read_text(errors="replace") if path.is_file() else ""
        statuses = re.findall(r"^Verification: (COMPLETE|CANNOT_RUN)[ \t]*$",
                              text, re.MULTILINE)
        if statuses != ["COMPLETE"]:
            unresolved = re.search(r"^Unresolved check: (.+)$", text, re.MULTILINE)
            detail = (unresolved.group(1) if unresolved else
                      "missing or invalid verification status")
            raise Halt(f"Gate verification incomplete: {detail}. Resolve the execution "
                       "blocker, then run next.py <run> --retry-gate. This does not "
                       "consume a code-rework round.")

    def archive_gate_briefs(self, g: int) -> Plan | None:
        """Retire pending briefs from the superseded gate, preserving their text."""
        started = as_int(self.gate_record(g).get("started_ns"))
        pending: list[Path] = []
        for brief in (self.run / "briefs").glob("*-ws*-r*.md"):
            match = re.fullmatch(r"(impl|docs)-ws(\d+)-r(\d+)\.md", brief.name)
            if not match or brief.stat().st_mtime_ns < started:
                continue
            kind, ws, rnd = match.group(1), int(match.group(2)), int(match.group(3))
            if kind == "impl":
                if rnd == 1 or self.r.report(ws, rnd) is not None:
                    continue
                output = self.run / f"implementer-{self.r.tag(ws, rnd)}.md"
            else:
                output = self.run / f"docs-fix-ws{ws}-r{rnd}.md"
                if (output.exists()
                        and output.stat().st_mtime_ns >= brief.stat().st_mtime_ns):
                    continue
            # A dispatched writer may still be working even without a report.
            expects = as_dict(self.state.get("dispatch")).get("expects", [])
            if str(output) in expects:
                return Plan(
                    halt=f"Cannot retry gate while {output.name} is pending; "
                         "wait for the dispatched writer first", code=1,
                    expects=[Path(str(path)) for path in expects])
            pending.append(brief)
        if pending:
            archive = self.run / "archive" / f"gate-r{g}-retry-{time.time_ns()}"
            archive.mkdir(parents=True)
            for brief in pending:
                brief.rename(archive / brief.name)
        return None

    def gate_plan(self) -> Plan:
        opts = run_state.options(self.r)
        codex = str(opts.get("codexCodeReview", paths.DEFAULTS["codexCodeReview"]))
        if codex == "off":
            return self.close()
        k = self.last_gate_triage()
        if self.args.retry_gate:
            gates = self.gates()
            if not gates:
                raise Halt("No gate to retry")
            g = max(int(n) for n in gates)
            pkg = self.run / "codex-gate-package"
            log = pkg / "codex-gate-attempts.log"
            blocked = self.archive_gate_briefs(g)
            if blocked is not None:
                return blocked
            # Preserve evidence, but old triage and briefs cannot schedule new work.
            return self.gate_start(g + 1, pkg, log, len(terminals(log)), fresh=True)
        latest = max((int(n) for n in self.gates()), default=0)
        if latest > k:
            return self.gate_run(latest)
        if k:
            tri = self.run / f"triage-gate-r{k}.md"
            self.require_gate_complete(self.gate_review_path(k))
            tv = verdict(tri)
            if not tv:
                raise Halt(f"{tri.name} has no `VERDICT:` line: decide the verdict "
                           "yourself and append it, then call again")
            if tv == "STOP":
                raise Halt(f"{tri.name} says STOP: read it and take it to the user")
            rec = self.gate_record(k)
            gate_head = str(rec.get("head") or self.head())
            past = self.between(gate_head, self.head())
            changed = [c for c, s in past if not s.startswith("docs-fix:")]
            if not changed:
                if tv in APPROVED_LIKE:
                    return self.close()
                plan = self.gate_docs(k, rec)
                if plan is not None:
                    return plan
                if tv == "NEEDS_DECISION":
                    return self.close()
                if tv == "NEEDS_REWORK":
                    return self.gate_triage_redo(k)
        return self.gate_run(k + 1)

    def gate_docs(self, k: int, rec: dict[str, object]) -> Plan | None:
        """The writer a gate triage asked for; the next gate once it has run."""
        started = as_int(rec.get("started_ns"))
        pending: list[Spawn] = []
        done = False
        for ws in self.r.roster:
            rnd = self.r.round_of(ws)
            brief = self.run / "briefs" / f"docs-ws{ws}-r{rnd}.md"
            if not brief.exists() or brief.stat().st_mtime_ns < started:
                continue
            out = self.run / f"docs-fix-ws{ws}-r{rnd}.md"
            if out.exists() and out.stat().st_mtime_ns >= brief.stat().st_mtime_ns:
                self.check_docs_fix(out)
                done = True
            else:
                pending.append(self.writer(ws, rnd))
        if pending:
            plan = Plan(step=f"docs-fix writer — gate {k}")
            plan.spawns = pending
            return plan
        return self.gate_run(k + 1) if done else None

    def gate_prompt(self, g: int, review: str, redo: bool) -> Spawn:
        out = self.run / f"triage-gate-r{g}.md"
        rounds = {ws: self.r.round_of(ws) for ws in self.r.roster}
        rows = "; ".join(
            f"WS-{ws}: briefs/impl-ws{ws}-r{rnd + 1}.md (docs only: "
            f"briefs/docs-ws{ws}-r{rnd}.md)" for ws, rnd in rounds.items())
        lines = [
            self.head_line(),
            f"Gate review: {review}. Gate: {g}. Reviewed HEAD: {self.head()}. "
            f"Verification / rework base: {self.base()}. Review base: see PROMPT.md.",
            "This is the independent review of the whole diff after verification "
            "and any required stream reviews. Triage it with your role file.",
            f"Current decisions: {current_brief.write_decisions(self.run)}.",
            f"Rework briefs, per workstream, if any row needs one: {rows}.",
            f"Rework count before this round: {max(rounds.values()) - 1}. "
            f"reworkCap: {self.r.cap}.",
            f"Output: write {out} and, on NEEDS_REWORK, the briefs above; return "
            "the two-line VERDICT block.",
        ]
        if redo:
            lines.insert(3, f"{out.name} already says NEEDS_REWORK but no rework "
                         "brief exists: write the briefs now (or change the "
                         "verdict if there is nothing to rework).")
        return Spawn("teamlead:triage", "\n".join(lines), out)

    def gate_triage_redo(self, g: int) -> Plan:
        deepest = max(self.r.round_of(ws) for ws in self.r.roster)
        if cap_reached(deepest, self.r.cap):
            raise Halt(self.cap_msg(deepest))
        review = str(self.gate_record(g).get("review") or
                     self.run / "codex-gate-package")
        spawn = self.gate_prompt(g, review, True)
        plan = Plan(step=f"triage (rework brief missing) — gate {g}")
        plan.spawns.append(spawn)
        tri = self.run / f"triage-gate-r{g}.md"
        plan.spawns[0].expect = tri
        plan.rewritten[str(tri)] = tri.stat().st_mtime_ns
        return plan

    def gate_run(self, g: int) -> Plan:
        pkg = self.run / "codex-gate-package"
        log = pkg / "codex-gate-attempts.log"
        rec = self.gate_record(g)
        have = terminals(log)
        opus_file = pkg / f"opus-review-r{g}.md"
        head = self.head()
        if not rec or (rec.get("head") != head
                       and len(have) <= as_int(rec.get("attempts_seen"))
                       and not opus_file.exists()):
            return self.gate_start(g, pkg, log, len(have), fresh=True)
        seen = as_int(rec.get("attempts_seen"))
        new = have[seen:]
        if new and new[-1][0] == "done":
            review = new[-1][1]
        elif opus_file.exists():
            review = str(opus_file)
        elif new:
            return self.gate_fallback(g, pkg, opus_file, new[-1][1])
        else:
            return self.gate_start(g, pkg, log, seen, fresh=False)
        self.require_gate_complete(review)
        plan = Plan(step=f"triage — gate {g}")
        spawn = self.gate_prompt(g, review, False)
        plan.spawns.append(spawn)
        if Path(review).name.startswith("opus-review-"):
            plan.cmds.append(("run", f"{self.script('fallback_review_tree.py')} "
                              f"{q(pkg / 'PROMPT.md')} {q(pkg / f'opus-tree-r{g}')} "
                              "--cleanup"))
        self.set_gate(plan, g, review=review)
        return plan

    def gate_start(self, g: int, pkg: Path, log: Path, seen: int,
                   fresh: bool) -> Plan:
        plan = Plan(step=f"Codex gate {g} — the whole diff, every stream approved")
        # Resolve review base separately; never change the pinned verifier base.
        plan.cmds.append(("run", f"{self.script('review_package.py')} "
                          f"{q(self.run)} --final-gate "
                          f"--verification-base {self.base()} "
                          f"--out {q(pkg)}"))
        plan.cmds.append(("run-background",
                          f"{self.script('run_codex_review.py')} "
                          f"{q(pkg / 'PROMPT.md')} --artifact-stem codex-gate"))
        plan.notes.append(f"wait for {log} to gain a done: or failed: line; "
                          "next.py does that on the next call")
        plan.gate_log, plan.gate_seen = str(log), seen
        if fresh:
            self.set_gate(plan, g, head=self.head(), attempts_seen=seen,
                          started_ns=time.time_ns())
        return plan

    def gate_fallback(self, g: int, pkg: Path, opus_file: Path, why: str) -> Plan:
        opts = run_state.options(self.r)
        opus = str(opts.get("opusCodeReview", paths.DEFAULTS["opusCodeReview"]))
        if opus == "off":
            raise Halt(f"Codex could not run ({why}) and opusCodeReview=off: the "
                       "change has no independent review. Fix Codex and call "
                       "again, or tell the user")
        prompt = "\n".join([
            f"PROMPT.md: {pkg}/PROMPT.md",
            f"Repo: {self.repo}",
            f"Answer: {opus_file}",
            "Before reviewing, prepare an isolated tree with: "
            f"{self.script('fallback_review_tree.py')} {q(pkg / 'PROMPT.md')} "
            f"{q(pkg / f'opus-tree-r{g}')}. Read the emitted PROMPT.md instead. "
            "If preparation fails, write Verification: CANNOT_RUN and name "
            "the unresolved isolation check. Never probe in the shared checkout.",
            f"Codex could not run ({why}), so this is the only review of this "
            "change.",
        ])
        plan = Plan(step=f"Opus fallback review — gate {g}")
        plan.spawns.append(Spawn("teamlead:code-reviewer", prompt, opus_file))
        return plan

    # --- close ---------------------------------------------------------------

    def close(self) -> Plan:
        current_brief.write_decisions(self.run)
        plan = Plan(step="11 — every workstream approved, nothing left to review")
        if (self.run / "deferred-rows.md").exists():
            plan.cmds.append(("run", f"{self.script('ledger.py')} apply "
                              f"{q(self.run)} --ledger "
                              f"{q(self.repo / 'docs' / 'deferred-work.md')}"))
        plan.notes.append(
            f"write {self.run}/final-report.md (references/roles/scribe.md), "
            "include the entries of decisions-log.md and the deferred rows, then "
            "send it to the user")
        return plan

    # --- the whole decision --------------------------------------------------

    def plan(self) -> Plan:
        if self.args.retry_gate:
            self.base()
            return self.gate_plan()
        if (self.run / "final-report.md").exists():
            owed = run_state.followup_rereview_owed(self.r)
            if owed:
                return Plan(step="11 — final report written; the re-review is "
                            "still owed", notes=[owed])
            return Plan(step="11 — final report written; the loop is complete",
                        notes=["send the final report to the user if you have "
                               "not already"])
        gap = run_state.plan_next(self.r)
        if gap:
            step, label, action, needs_user = gap
            return Plan(step=f"{step} — {label}", notes=[action],
                        code=1 if needs_user else 0)
        self.base()
        self.log_gate_decisions()
        latest = max((int(n) for n in self.gates()), default=0)
        if latest and not self.args.retry_gate and self.gate_review_path(latest):
            self.require_gate_complete(self.gate_review_path(latest))
        plan = self.stream_plan()
        if plan is None:
            plan = self.fix_plan() or self.gate_plan()
        return plan


# ---------------------------------------------------------------------- output

def render(plan: Plan) -> list[str]:
    out: list[str] = []
    if plan.step:
        out.append(f"step: {plan.step}")
    for s in plan.spawns:
        out.append(f"spawn: {s.kind}" + (f" model={s.model}" if s.model else ""))
        out += ["<<<", *s.prompt.rstrip("\n").splitlines(), ">>>"]
        out.append(f"expect: {s.expect}")
    for how, cmd in plan.cmds:
        out.append(f"{how}: {cmd}")
    if plan.gate_log:
        out.append(f"expect: {plan.gate_log} (a new done: or failed: line)")
    out += [f"next: {n}" for n in plan.notes]
    if plan.halt:
        out.append(f"halt: {plan.halt}")
    return out


def retry_line(run: Path, args: argparse.Namespace) -> str:
    cmd = [sys.executable, str(Path(__file__).resolve()), str(run),
           "--timeout", str(args.timeout), "--poll", str(args.poll)]
    return "RETRY: " + shlex.join(cmd)


def wait_pending(router: Router, args: argparse.Namespace) -> int | None:
    """Wait for the dispatch the last call printed; 3 on timeout, else None."""
    sent = as_dict(router.state.get("dispatch"))
    files = [str(p) for p in sent.get("expects", []) if isinstance(p, str)] \
        if isinstance(sent.get("expects"), list) else []
    gate = as_dict(sent.get("gate"))
    if not files and not gate:
        return None
    if gate:
        log, seen = Path(str(gate.get("log"))), as_int(gate.get("count"))
        end = time.monotonic() + args.timeout
        while len(terminals(log)) <= seen:
            if time.monotonic() >= end:
                print(f"TIMEOUT after {args.timeout}s; missing: {log.name} (no new "
                      "done: or failed: line yet)")
                print(retry_line(router.run, args))
                return 3
            time.sleep(args.poll)
    if files:
        rewritten = as_dict(sent.get("rewritten"))
        code, lines = wait_for.wait(
            files, timeout=args.timeout, poll=args.poll,
            rewritten=list(rewritten),
            baseline=[(k, str(as_int(v))) for k, v in rewritten.items()])
        if code == 2:
            print("\n".join(ln for ln in lines if not ln.startswith("RETRY:")))
            print(retry_line(router.run, args))
            return 3
        if code == 1:
            print("\n".join(f"note: {ln}" for ln in lines))
    phase = sent.get("metricPhase")
    if isinstance(phase, str):
        run_metrics.finish(router.run, phase)
        if gate:
            attempts = terminals(Path(str(gate.get("log"))))
            recent = attempts[as_int(gate.get("count")):]
            if recent and all(status == "done" for status, _ in recent):
                run_metrics.codex_usage(router.run, phase,
                                        [Path(p).with_suffix(".jsonl")
                                         for _, p in recent])
    router.state.pop("dispatch", None)
    router.save_state()
    return None


def remember(router: Router, plan: Plan) -> None:
    router.state.update(plan.state)
    expects = [str(s.expect) for s in plan.spawns] + [str(p) for p in plan.expects]
    dispatch: dict[str, object] = {}
    if expects:
        dispatch["expects"] = expects
    if plan.rewritten:
        dispatch["rewritten"] = plan.rewritten
    if plan.gate_log:
        dispatch["gate"] = {"log": plan.gate_log, "count": plan.gate_seen}
    if dispatch:
        previous = as_dict(router.state.get("dispatch"))
        same = {k: v for k, v in previous.items() if k != "metricPhase"} == dispatch
        phase = previous.get("metricPhase") if same else None
        if not isinstance(phase, str):
            phase = f"{plan.step} [{time.time_ns()}]"
        run_metrics.start(router.run, phase)
        dispatch["metricPhase"] = phase
        router.state["dispatch"] = dispatch
    else:
        router.state.pop("dispatch", None)
    router.save_state()


def decide(run: Path, argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="next.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--poll", type=int, default=5,
                    help="seconds between polls while waiting (default 5)")
    ap.add_argument("--timeout", type=int, default=480,
                    help="seconds to wait before exit 3 (default 480)")
    ap.add_argument("--redo", action="store_true",
                    help="print the current dispatch again instead of waiting")
    ap.add_argument("--retry-gate", action="store_true",
                    help="rerun final review after resolving an execution blocker")
    ap.add_argument("--base", metavar="SHA",
                    help="pin the base SHA (default: HEAD on the first call)")
    args = ap.parse_args(argv)
    run = Path(os.path.abspath(run.expanduser()))
    if not (run / "repo.txt").exists():
        print(f"{run} is not a run directory (no repo.txt)")
        return 2
    router = Router(run, args)
    print(f"RUN={run}")
    print(f"repo={router.repo}")
    if not args.redo and not args.retry_gate:
        waited = wait_pending(router, args)
        if waited is not None:
            return waited
    try:
        plan = router.plan()
    except (Halt, ValueError) as exc:
        plan = Plan(halt=str(exc), code=1)
    profile, reason = workflow_profile.selection(run)
    print(f"workflow: {profile} — {reason}")
    print("\n".join(render(plan)))
    remember(router, plan)
    return plan.code


def main(argv: list[str]) -> int:
    return decide(Path(argv[1]) if len(argv) > 1 else Path("."), argv[2:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
