#!/usr/bin/env python3
"""Regression suite for scripts/mutate.py:  python3 scripts/test_mutate.py

The mutation gate is the check on the tests themselves: a verifier PASS says the
brief's commands are green, the gate says they would go red if a changed line
were wrong. So the cases that matter most are the ways a gate lies: a mutant
that stacks on the previous one, a mutant it never restores, a leftover counted
as killed, a line from another stream's commit mutated, a flipped `<` that is
really `<=`.

Each case builds a throwaway repo with git's global and system config switched
off. Mutants are observed from outside: the test command appends a snapshot of
the mutated file to a log kept outside the repo, so no case depends on how
mutate.py names its operators.

No pytest dependency — the skill's scripts run with bare python3, and a suite
that needs an install is a suite nobody runs.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path
import tempfile

SCRIPT = Path(__file__).resolve().parent / "mutate.py"
ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
       "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
       "PYTHONDONTWRITEBYTECODE": "1"}

LIB_BASE = "BASE = 1\n"
LIB_ADDED = "def below(n):\n    return n < 10\n"
WEAK_TEST = ("import os, sys\n"
             "root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\n"
             "sys.path.insert(0, root)\n"
             "import lib\n"
             "lib.below(5)\n")
STRONG_TEST = WEAK_TEST + "assert lib.below(9) is True\nassert lib.below(10) is False\n"
TEST_CMD = "python3 tests/test_lib.py"
SNAP_END = "@@@@\n"

OPS_LINES = [
    "eq_a == eq_b", "ne_a != ne_b", "lt_a < lt_b", "le_a <= le_b", "shl_a << shl_b",
    "and_a && and_b", "or_a || or_b", "t_a = true", "f_a = false", "return ret_x",
    "await aw_f()", "gt_a > gt_b", "ge_a >= ge_b", "plain = 1",
]
# Every line can be deleted (None); these are the only other mutants of each.
OPS_ORIGINAL = "\n".join(OPS_LINES) + "\n"
OPS_EXPECTED = {
    "eq_a == eq_b": {"eq_a != eq_b"}, "ne_a != ne_b": {"ne_a == ne_b"},
    "lt_a < lt_b": {"lt_a <= lt_b"}, "le_a <= le_b": {"le_a < le_b"},
    "shl_a << shl_b": set(), "and_a && and_b": {"and_a || and_b"},
    "or_a || or_b": {"or_a && or_b"}, "t_a = true": {"t_a = false"},
    "f_a = false": {"f_a = true"}, "return ret_x": {"ret_x"},
    "await aw_f()": {"aw_f()"}, "gt_a > gt_b": set(), "ge_a >= ge_b": set(),
    "plain = 1": set(),
}

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


class Repo:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True)
        self.git("init", "-q", "-b", "main")
        self.write("lib.py", LIB_BASE)
        self.write("shared.py", "def shared():\n    return 0\n")
        self.base = self.commit("base")

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.root), *args], env=ENV,
                              check=True, capture_output=True, text=True).stdout.strip()

    def write(self, rel: str, text: str) -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def append(self, rel: str, text: str) -> None:
        with (self.root / rel).open("a") as fh:
            fh.write(text)

    def commit(self, msg: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", msg)
        return self.git("rev-parse", "HEAD")

    def status(self) -> str:
        return self.git("status", "--porcelain")

    def stream(self, test: str = WEAK_TEST) -> str:
        """A stream commit: `below` appended to lib.py, plus a test file."""
        self.append("lib.py", "\n" + LIB_ADDED)
        self.write("tests/test_lib.py", test)
        return self.commit("stream: below")

    def line_of(self, rel: str, needle: str) -> int:
        for n, ln in enumerate((self.root / rel).read_text().splitlines(), 1):
            if needle in ln:
                return n
        raise AssertionError((rel, needle))


def mutate(repo: Repo, *args: str, env: dict[str, str] | None = None,
           ) -> tuple[int, str, str]:
    proc = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(repo.root),
                           "--base", repo.base, *args], env=env or ENV,
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


SUMMARY = re.compile(r"^MUTATION: (PASS|FAIL) killed=(\d+) survived=(\d+) "
                     r"invalid=(\d+) "
                     r"unclassified=(\d+) not_run=(\d+) not_applied=(\d+)$")
FIELDS = ("killed", "survived", "invalid", "unclassified", "not_run", "not_applied")


def summary(out: str) -> tuple[str, dict[str, int]]:
    last = out.strip().splitlines()[-1] if out.strip() else ""
    m = SUMMARY.match(last)
    if not m:
        return "", {}
    return m.group(1), dict(zip(FIELDS, map(int, m.groups()[1:])))


def write_probes(repo: Repo, probes: list[dict[str, str]]) -> str:
    path = repo.root.parent / "probes.json"
    path.write_text(json.dumps(probes))
    return str(path)


def snapshot_cmd(log: Path, file: str, result: str = "true") -> str:
    return f"cat {shlex.quote(file)} >> {shlex.quote(str(log))}; " \
           f"echo '@@@@' >> {shlex.quote(str(log))}; {result}"


def snapshots(log: Path) -> list[str]:
    if not log.exists():
        return []
    return [s for s in log.read_text().split(SNAP_END) if s != ""]


def mutant_snapshots(log: Path, original: str) -> list[str]:
    """The snapshots after the first, which must be the unmutated file (the pre-run)."""
    snaps = snapshots(log)
    assert snaps and snaps[0] == original, snaps[:1]
    return snaps[1:]


def same_as_saved(repo: Repo, tmp: Path, rel: str = "lib.py") -> str:
    """A test command that passes on the current `rel` and fails on any mutant of it."""
    saved = tmp / f"saved-{rel.replace('/', '_')}"
    saved.write_bytes((repo.root / rel).read_bytes())
    return f"cmp -s {shlex.quote(rel)} {shlex.quote(str(saved))}"


def changed_line(original: list[str], snap: str) -> tuple[int, str | None]:
    """The one line `snap` differs from `original` in: (index, new text or None)."""
    lines = snap.splitlines()
    if len(lines) == len(original) - 1:
        for i, ln in enumerate(original):
            if i >= len(lines) or lines[i] != ln:
                assert lines == original[:i] + original[i + 1:], snap
                return i, None
    assert len(lines) == len(original), snap
    diff = [i for i, (a, b) in enumerate(zip(original, lines)) if a != b]
    assert len(diff) == 1, (diff, snap)
    return diff[0], lines[diff[0]]


def ops_repo(tmp: Path) -> tuple[Repo, str]:
    repo = Repo(tmp / "repo")
    repo.write("ops.txt", "\n".join(OPS_LINES) + "\n")
    return repo, repo.commit("stream: ops")


def case_survivor_fails_gate(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    commit = repo.stream(WEAK_TEST)
    patch = write_probes(repo, [{"probe": "boundary", "file": "lib.py",
                                 "old": "n < 10", "new": "n <= 10"}])
    code, out, err = mutate(repo, "--cmd", TEST_CMD, "--commits", commit,
                            "--probes", patch, "--max-generic", "0")
    verdict, n = summary(out)
    check("an uncaught mutant is SURVIVED, the summary FAIL, the exit 1",
          code == 1 and verdict == "FAIL" and n.get("survived") == 1
          and "SURVIVED" in out and repo.status() == "", out + err)
    code, out, err = mutate(repo, "--cmd", TEST_CMD, "--commits", commit)
    verdict, n = summary(out)
    check("a generic `<` flip survives a test that never asserts the boundary",
          code == 1 and verdict == "FAIL" and n.get("survived", 0) >= 1
          and re.search(r"SURVIVED.*lib\.py:%d" % repo.line_of("lib.py", "n < 10"), out)
          and repo.status() == "", out + err)


def case_all_killed_passes(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    commit = repo.stream(STRONG_TEST)
    patch = write_probes(repo, [{"probe": "boundary", "file": "lib.py",
                                 "old": "n < 10", "new": "n <= 10"}])
    code, out, err = mutate(repo, "--cmd", TEST_CMD, "--commits", commit,
                            "--probes", patch)
    verdict, n = summary(out)
    check("every mutant killed gives PASS, exit 0, and a clean tree",
          code == 0 and verdict == "PASS" and n.get("survived") == 0
          and n.get("killed", 0) >= 3 and repo.status() == "", out + err)


def case_probe_patch_applied_exactly(tmp: Path) -> None:
    repo, commit = ops_repo(tmp)
    log = tmp / "log"
    new_ret = "return ret_y  # patched"
    patch = write_probes(repo, [{"probe": "the ret clause", "file": "ops.txt",
                                 "old": "return ret_x", "new": new_ret}])
    code, out, err = mutate(repo, "--cmd", snapshot_cmd(log, "ops.txt"),
                            "--commits", commit, "--probes", patch,
                            "--max-generic", "0")
    want = "\n".join(OPS_LINES).replace("return ret_x", new_ret) + "\n"
    check("a probe's old text is replaced by its new text verbatim, under its clause",
          mutant_snapshots(log, OPS_ORIGINAL) == [want] and "the ret clause" in out
          and (repo.root / "ops.txt").read_text() == "\n".join(OPS_LINES) + "\n",
          out + err + repr(snapshots(log)))

    repo = Repo(tmp / "repo2")
    commit = repo.stream(STRONG_TEST)
    patch = write_probes(repo, [
        {"probe": "applies", "file": "lib.py", "old": "n < 10", "new": "n <= 10"},
        {"probe": "text that is not there", "file": "lib.py",
         "old": "no such text", "new": "x"}])
    code, out, err = mutate(repo, "--cmd", TEST_CMD, "--commits", commit,
                            "--probes", patch, "--max-generic", "0")
    verdict, n = summary(out)
    check("a probe whose old text is absent is NOT APPLIED and fails the gate",
          code == 1 and verdict == "FAIL" and n.get("not_applied") == 1
          and n.get("killed") == 1 and n.get("survived") == 0
          and "NOT APPLIED" in out and "text that is not there" in out, out + err)


def case_generic_ops_changed_lines_only(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    repo.append("lib.py", "\n\n# flag == True stays a comment\n"
                "def fresh(x):\n    return x < 5\n")
    repo.write("tests/test_new.py", "assert 1 < 2\n")
    repo.write("spec_helper.py", "ok = 1 < 2\n")
    commit = repo.commit("stream")
    code, out, err = mutate(repo, "--cmd", "true", "--commits", commit,
                            "--max-generic", "1000")
    hit = set(re.findall(r"(\S+\.py):(\d+)", out))
    fresh = repo.line_of("lib.py", "return x < 5")
    body = {(f, int(n)) for f, n in hit}
    check("only changed, non-blank, non-comment lines outside test files are mutated",
          body and {f for f, _ in body} == {"lib.py"}
          and {n for _, n in body} <= {fresh - 1, fresh}
          and fresh in {n for _, n in body}, out + err)
    check("generic ops leave an untouched base line alone",
          bool(body) and not any(n <= 2 for _, n in body), out)


def case_stream_scope_only(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    repo.append("shared.py", "def fa(x):\n    return x < 3\n")
    a1 = repo.commit("A: shared")
    repo.append("shared.py", "def fb(x):\n    return x == 4\n")
    repo.write("b.py", "def gb(x):\n    return x != 6\n")
    repo.commit("B: shared and own file")
    repo.write("a.py", "def ga(x):\n    return x > 7 and x < 8\n")
    repo.write("pkg/deep.py", "def gd(x):\n    return x < 9\n")
    a2 = repo.commit("A: own files")
    fa = repo.line_of("shared.py", "return x < 3")
    fb = repo.line_of("shared.py", "return x == 4")

    code, out, err = mutate(repo, "--cmd", "true", "--commits", a1, a2,
                            "--max-generic", "1000")
    hit = {(f, int(n)) for f, n in re.findall(r"(\S+\.py):(\d+)", out)}
    check("--commits mutates this stream's lines, even in a file both streams changed",
          ("shared.py", fa) in hit and ("a.py", 2) in hit, out + err)
    check("--commits never mutates a line another stream's commit wrote",
          ("shared.py", fa) in hit and not any(f == "b.py" for f, _ in hit)
          and not any(f == "shared.py" and n in (fb - 1, fb) for f, n in hit)
          and not any(f == "shared.py" and n <= 2 for f, n in hit), out)

    code, out, err = mutate(repo, "--cmd", "true", "--files", "a.py", "pkg/",
                            "--max-generic", "1000")
    files = {f for f, _ in re.findall(r"(\S+\.py):(\d+)", out)}
    check("--files mutates the listed files and those under a listed directory only",
          files == {"a.py", "pkg/deep.py"}, out + err)
    hit_files = {(f, int(n)) for f, n in re.findall(r"(\S+\.py):(\d+)", out)}
    check("--files takes every line of a multi-line hunk, not only its first",
          ("a.py", 2) in hit_files and ("pkg/deep.py", 2) in hit_files, out + err)

    both = ["--commits", a1, "--files", "a.py"]
    for label, args in (("neither", []), ("both", both)):
        code, out, err = mutate(repo, "--cmd", "true", *args)
        check(f"{label} of --commits / --files is a usage error, exit 2",
              code == 2 and repo.status() == "", out + err)
    code, out, err = mutate(repo, "--cmd", "true", "--commits", "not-a-commit")
    check("an unknown commit is a usage error, exit 2", code == 2, out + err)


def run_ops(tmp: Path, *extra: str, hashseed: str = "0", name: str = "log",
            ) -> tuple[Repo, Path, int, str]:
    repo, commit = ops_repo(tmp)
    log = tmp / name
    code, out, err = mutate(repo, "--cmd", snapshot_cmd(log, "ops.txt"),
                            "--commits", commit, *extra,
                            env={**ENV, "PYTHONHASHSEED": hashseed})
    return repo, log, code, out + err


def case_each_op_flips_both_ways(tmp: Path) -> None:
    repo, log, code, out = run_ops(tmp, "--max-generic", "1000")
    got: dict[str, set[str | None]] = {ln: set() for ln in OPS_LINES}
    stacked = ""
    mutants = mutant_snapshots(log, OPS_ORIGINAL)
    for snap in mutants:
        try:
            idx, new = changed_line(OPS_LINES, snap)
        except AssertionError as exc:
            stacked = str(exc)
            break
        got[OPS_LINES[idx]].add(new)
    want = {ln: ({None} | exp) for ln, exp in OPS_EXPECTED.items()}
    check("each mutant changes one line of a clean file, never stacking on the last",
          stacked == "" and len(mutants) > 0, stacked + out)
    bad = {ln: (got[ln], want[ln]) for ln in OPS_LINES if got[ln] != want[ln]}
    check("== != < <= && || true false, return and await flip both ways, "
          "and nothing else is generated", not bad, f"{bad}\n{out}")
    check("the working tree is clean once all mutants ran",
          len(mutants) > 0 and repo.status() == "", out)


def case_sampling_deterministic_and_capped(tmp: Path) -> None:
    repo, log1, code1, out1 = run_ops(tmp, "--max-generic", "5", hashseed="0",
                                      name="log1")
    log2 = tmp / "log2"
    commit = repo.git("rev-parse", "HEAD")
    code2, out2, err2 = mutate(
        repo, "--cmd", snapshot_cmd(log2, "ops.txt"), "--commits", commit,
        "--max-generic", "5", env={**ENV, "PYTHONHASHSEED": "1"})
    mutants1 = mutant_snapshots(log1, OPS_ORIGINAL)
    mutants2 = mutant_snapshots(log2, OPS_ORIGINAL)
    check("two runs, even under different hash seeds, pick the same mutants in order",
          mutants1 == mutants2 and len(mutants1) > 0, out1 + out2 + err2)
    check("generic mutants never exceed --max-generic when more are available",
          len(mutants1) == 5, str(len(mutants1)))
    log3 = tmp / "log3"
    patch = write_probes(repo, [
        {"probe": "p1", "file": "ops.txt", "old": "plain = 1", "new": "plain = 2"},
        {"probe": "p2", "file": "ops.txt", "old": "t_a = true", "new": "t_a = 3"}])
    code3, out3, err3 = mutate(
        repo, "--cmd", snapshot_cmd(log3, "ops.txt"), "--commits", commit,
        "--max-generic", "5", "--probes", patch)
    mutants3 = mutant_snapshots(log3, OPS_ORIGINAL)
    check("brief probes run first and do not count against --max-generic",
          len(mutants3) == 7 and "plain = 2" in mutants3[0]
          and "t_a = 3" in mutants3[1], out3 + err3)


def case_time_box_reports_not_run(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    repo.append("lib.py", "\n" + LIB_ADDED + "def above(n):\n    return n > 1\n")
    commit = repo.commit("stream")
    cmd = f"sleep 0.6; {same_as_saved(repo, tmp)}"
    start = time.monotonic()
    code, out, err = mutate(repo, "--cmd", cmd, "--commits", commit,
                            "--max-generic", "1000", "--time-box", "1.5")
    took = time.monotonic() - start
    verdict, n = summary(out)
    check("mutants left when the time box expires are NOT RUN, never killed",
          n.get("killed") == 1 and n.get("not_run", 0) >= 1
          and sum(n.values()) == 7 and "NOT RUN" in out, out + err)
    check("an expired time box stops the run; no survivor, so no failure",
          took < 5 and code == 0 and verdict == "PASS" and repo.status() == "",
          f"{took:.1f}s {out}{err}")


def case_invalid_mutant(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    commit = repo.stream(STRONG_TEST)
    code, out, err = mutate(repo, "--cmd", same_as_saved(repo, tmp), "--commits",
                            commit, "--max-generic", "1000")
    verdict, n = summary(out)
    check("a .py mutant that does not compile is INVALID, not killed or survived",
          n.get("invalid") == 2 and n.get("killed") == 2 and n.get("survived") == 0
          and "INVALID" in out, out + err)

    repo = Repo(tmp / "repo2")
    repo.write("m.txt", "a == b\n")
    commit = repo.commit("stream")
    fails = same_as_saved(repo, tmp, "m.txt")
    code, out, err = mutate(repo, "--cmd", fails, "--commits", commit)
    verdict, n = summary(out)
    check("a failing non-.py mutant with no --check-cmd is UNCLASSIFIED, never killed, "
          "and does not fail the gate",
          n.get("unclassified") == 2 and n.get("killed") == 0 and code == 0
          and verdict == "PASS" and "UNCLASSIFIED" in out, out + err)
    code, out, err = mutate(repo, "--cmd", fails, "--commits", commit,
                            "--check-cmd", "test -s {file}")
    verdict, n = summary(out)
    check("--check-cmd exiting non-zero is INVALID; a passing one lets the test "
          "command's failure count as killed",
          n.get("invalid") == 1 and n.get("killed") == 1 and n.get("unclassified") == 0,
          out + err)
    check("with --check-cmd the failing check marks the delete-line row INVALID and "
          "the passing one lets the eq->ne row be KILLED",
          re.search(r"^INVALID\s+m\.txt:1\s+op=delete-line$", out, re.M)
          and re.search(r"^KILLED\s+m\.txt:1\s+op=eq->ne$", out, re.M), out + err)


def case_restore_on_signal(tmp: Path) -> None:
    for sig in (signal.SIGTERM, signal.SIGINT):
        repo = Repo(tmp / f"repo{int(sig)}")
        commit = repo.stream()
        original = (repo.root / "lib.py").read_text()
        marker = tmp / f"started{int(sig)}"
        cmd = (f"{same_as_saved(repo, tmp)} && exit 0; "
               f"touch {shlex.quote(str(marker))}; sleep 30")
        proc = subprocess.Popen(
            [sys.executable, str(SCRIPT), "--repo", str(repo.root), "--base", repo.base,
             "--cmd", cmd, "--commits", commit], env=ENV,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        mid_run = (repo.root / "lib.py").read_text() != original
        proc.send_signal(sig)
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        check(f"{sig.name} during the test command leaves the tree clean",
              mid_run and repo.status() == ""
              and (repo.root / "lib.py").read_text() == original
              and proc.returncode not in (0, 1, 2),
              f"mid_run={mid_run} rc={proc.returncode}")
    repo = Repo(tmp / "repo-twice")
    commit = repo.stream()
    original = (repo.root / "lib.py").read_text()
    marker = tmp / "started-twice"
    cmd = (f"{same_as_saved(repo, tmp)} && exit 0; "
           f"touch {shlex.quote(str(marker))}; sleep 30")
    proc = subprocess.Popen(
        [sys.executable, str(SCRIPT), "--repo", str(repo.root), "--base", repo.base,
         "--cmd", cmd, "--commits", commit],
        env=ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 10
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    proc.send_signal(signal.SIGTERM)
    time.sleep(0.005)
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    check("a second SIGTERM while the file is being restored leaves the tree clean "
          "and the exit 3",
          repo.status() == "" and (repo.root / "lib.py").read_text() == original
          and proc.returncode == 3, f"rc={proc.returncode} {repo.status()}")


def case_dirty_tree_refused(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    commit = repo.stream()
    log = tmp / "log"
    repo.append("lib.py", "# local edit\n")
    before = (repo.root / "lib.py").read_text()
    code, out, err = mutate(repo, "--cmd", snapshot_cmd(log, "lib.py"),
                            "--commits", commit)
    check("a dirty tree at start exits 3 and changes no file",
          code == 3 and (repo.root / "lib.py").read_text() == before
          and snapshots(log) == [] and "MUTATION:" not in out, out + err)

    repo = Repo(tmp / "repo2")
    commit = repo.stream()
    code, out, err = mutate(repo, "--cmd", "touch stray.txt", "--commits", commit)
    check("a tree left dirty at the end is exit 3, not a PASS",
          code == 3 and "MUTATION: PASS" not in out
          and (repo.root / "stray.txt").exists(),
          out + err)


def case_out_report(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    commit = repo.stream(STRONG_TEST)
    report = tmp / "mutation.md"
    patch = write_probes(repo, [{"probe": "boundary clause", "file": "lib.py",
                                 "old": "n < 10", "new": "n <= 10"}])
    code, out, err = mutate(repo, "--cmd", TEST_CMD, "--commits", commit,
                            "--probes", patch, "--out", str(report))
    verdict, n = summary(out)
    rows = [ln for ln in report.read_text().splitlines()
            if "lib.py" in ln] if report.exists() else []
    result_word = re.compile(
        r"KILLED|SURVIVED|INVALID|UNCLASSIFIED|NOT RUN|NOT APPLIED")
    probe_rows = [r for r in rows if "boundary clause" in r]
    line = str(repo.line_of("lib.py", "n < 10"))
    check("--out writes one row per mutant with file, line, clause or op, and result",
          len(rows) == sum(n.values()) and len(probe_rows) == 1
          and "KILLED" in probe_rows[0] and line in probe_rows[0]
          and all(result_word.search(r) for r in rows), out + err + "\n".join(rows))


def case_time_box_zero_runs_nothing(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    commit = repo.stream(STRONG_TEST)
    log = tmp / "log"
    cmd = snapshot_cmd(log, "lib.py", same_as_saved(repo, tmp))
    code, out, err = mutate(repo, "--cmd", cmd, "--commits", commit,
                            "--max-generic", "1000", "--time-box", "0")
    check("with no time left the unmutated pre-run is refused (exit 3) and nothing "
          "runs or is applied",
          code == 3 and err.startswith("cannot run:") and "MUTATION:" not in out
          and snapshots(log) == [] and repo.status() == "", f"{code} {out}{err}")


def case_one_survivor_among_kills_fails(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    commit = repo.stream(STRONG_TEST)
    patch = write_probes(repo, [{"probe": "no-op edit", "file": "lib.py",
                                 "old": "n < 10", "new": "n < 10  # same"}])
    code, out, err = mutate(repo, "--cmd", TEST_CMD, "--commits", commit,
                            "--probes", patch)
    verdict, n = summary(out)
    check("one survivor fails the gate even when more mutants were killed",
          code == 1 and verdict == "FAIL" and n.get("survived") == 1
          and n.get("killed", 0) >= 2, out + err)


def case_sampling_is_not_file_order(tmp: Path) -> None:
    repo, log, code, out = run_ops(tmp, "--max-generic", "5")
    mutants = mutant_snapshots(log, OPS_ORIGINAL)
    picked = {changed_line(OPS_LINES, s)[0] for s in mutants}
    per_line = [i for i in range(len(OPS_LINES))
                for _ in range(1 + len(OPS_EXPECTED[OPS_LINES[i]]))]
    check("the sample is neither the first nor the last mutants in file order",
          len(mutants) == 5 and picked != set(per_line[:5])
          and picked != set(per_line[-5:]), f"{picked}\n{out}")


def case_interrupt_exit_code(tmp: Path) -> None:
    for sig in (signal.SIGTERM, signal.SIGINT):
        repo = Repo(tmp / f"repo{int(sig)}")
        commit = repo.stream()
        marker = tmp / f"started{int(sig)}"
        pidfile = tmp / f"pid{int(sig)}"
        cmd = (f"{same_as_saved(repo, tmp)} && exit 0; "
               f"echo $$ > {shlex.quote(str(pidfile))}; "
               f"touch {shlex.quote(str(marker))}; sleep 30")
        proc = subprocess.Popen(
            [sys.executable, str(SCRIPT), "--repo", str(repo.root), "--base", repo.base,
             "--cmd", cmd, "--commits", commit], env=ENV,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        proc.send_signal(sig)
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        check(f"{sig.name} makes the gate exit 3 (cannot run), not a signal death",
              marker.exists() and proc.returncode == 3, f"rc={proc.returncode}")
        pid = int(pidfile.read_text())
        try:
            os.kill(pid, 0)
            alive = True
        except ProcessLookupError:
            alive = False
        if alive:
            os.kill(pid, signal.SIGKILL)
        check(f"{sig.name} also kills the running test command, in its own session",
              not alive, f"pid {pid} still running")


def case_prose_lines_not_mutated(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    repo.write("doc.py", '"""Module notes\nthe flag is true\n"""\nX = 1 < 2\n')
    repo.write("notes.md", "the flag is true\nread more == here\n")
    repo.write("guide.rst", "read more == here\n")
    repo.write("intro.markdown", "read more == here\n")
    commit = repo.commit("stream: docs")
    code, out, err = mutate(repo, "--cmd", "true", "--commits", commit,
                            "--max-generic", "1000")
    hit = {(f, int(n)) for f, n in
           re.findall(r"(\S+\.(?:py|md|rst|markdown)):(\d+)", out)}
    check("a docstring line and a Markdown line are never mutated; code still is",
          ("doc.py", 4) in hit
          and not any(f == "doc.py" and n <= 3 for f, n in hit)
          and not any(f == "notes.md" for f, _ in hit)
          and not any(f in ("guide.rst", "intro.markdown") for f, _ in hit),
          out + err)


def case_untracked_or_linked_targets_refused(tmp: Path) -> None:
    outside = tmp / "outside.txt"
    outside.write_text("secret == value\n")
    repo = Repo(tmp / "repo")
    os.symlink(outside, repo.root / "link.txt")
    repo.write(".gitignore", "ignored.txt\n")
    repo.write("ignored.txt", "secret == value\n")
    commit = repo.commit("stream: link")
    for name, target in (("a committed symlink", "link.txt"),
                         ("an ignored file", "ignored.txt")):
        patch = write_probes(repo, [{"probe": "p", "file": target,
                                     "old": "secret", "new": "public"}])
        code, out, err = mutate(repo, "--cmd", "true", "--commits", commit,
                                "--probes", patch, "--max-generic", "0")
        check(f"a probe on {name} is a usage error that touches no file",
              code == 2 and outside.read_text() == "secret == value\n"
              and (repo.root / "ignored.txt").read_text() == "secret == value\n"
              and "MUTATION:" not in out, f"{code} {out}{err}")
    repo = Repo(tmp / "repo2")
    os.symlink(outside, repo.root / "link.txt")
    commit = repo.commit("stream: link only")
    code, out, err = mutate(repo, "--cmd", "true", "--commits", commit,
                            "--max-generic", "1000")
    check("a generic run whose only changed path is a symlink mutates nothing",
          outside.read_text() == "secret == value\n" and "link.txt" not in out
          and repo.status() == "", f"{code} {out}{err}")
    repo = Repo(tmp / "repo3")
    repo.write("sub/a.py", "secret = 1\n")
    commit = repo.commit("stream: sub/a.py")
    patch = write_probes(repo, [{"probe": "p", "file": "sub",
                                 "old": "secret", "new": "public"}])
    code, out, err = mutate(repo, "--cmd", "true", "--commits", commit,
                            "--probes", patch, "--max-generic", "0")
    check("a probe whose file is a directory is a usage error that touches no file",
          code == 2 and (repo.root / "sub" / "a.py").read_text() == "secret = 1\n",
          f"{code} {out}{err}")


def case_deleted_file_in_stream(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    repo.write("gone.py", "def g():\n    return 1 < 2\n")
    repo.base = repo.commit("base: gone.py")
    os.remove(repo.root / "gone.py")
    repo.append("lib.py", "Y = 1 < 2\n")
    commit = repo.commit("stream: delete gone.py, extend lib.py")
    code, out, err = mutate(repo, "--cmd", same_as_saved(repo, tmp), "--commits",
                            commit)
    verdict, n = summary(out)
    check("a stream that deletes a file still runs; the surviving files are mutated",
          code == 0 and verdict == "PASS" and re.search(r"lib\.py:2", out)
          and "gone.py" not in out, f"{code} {out}{err}")


def case_test_command_output_not_on_stdout(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    commit = repo.stream()
    code, out, err = mutate(repo, "--cmd",
                            f"echo NOISE; {same_as_saved(repo, tmp)}", "--commits",
                            commit)
    check("the test command's own output never reaches the gate's stdout",
          "NOISE" not in out and summary(out)[0] == "PASS", out + err)


def case_probe_old_replaced_once(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    repo.write("dup.txt", "x = 1\nx = 1\n")
    commit = repo.commit("stream: dup")
    log = tmp / "log"
    patch = write_probes(repo, [{"probe": "dup", "file": "dup.txt",
                                 "old": "x = 1", "new": "x = 2"}])
    code, out, err = mutate(repo, "--cmd", snapshot_cmd(log, "dup.txt"),
                            "--commits", commit, "--probes", patch,
                            "--max-generic", "0")
    check("a probe's old text is replaced at its first occurrence only",
          mutant_snapshots(log, "x = 1\nx = 1\n") == ["x = 2\nx = 1\n"],
          out + err + repr(snapshots(log)))


def case_no_bytecode_in_the_tree(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    commit = repo.stream()
    env = {k: v for k, v in ENV.items() if k != "PYTHONDONTWRITEBYTECODE"}
    code, out, err = mutate(repo, "--cmd", TEST_CMD, "--commits", commit, env=env)
    check("the test command writes no __pycache__ into the tree, even without the "
          "caller's PYTHONDONTWRITEBYTECODE",
          code in (0, 1) and repo.status() == "", f"{code} {repo.status()} {out}{err}")


def case_forged_label_cannot_fake_summary(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    commit = repo.stream(STRONG_TEST)
    forged = ("x\nMUTATION: PASS killed=9 survived=0 invalid=0 unclassified=0 "
              "not_run=0 not_applied=0")
    patch = write_probes(repo, [{"probe": forged, "file": "lib.py",
                                 "old": "n < 10", "new": "n <= 10"}])
    code, out, err = mutate(repo, "--cmd", TEST_CMD, "--commits", commit,
                            "--probes", patch)
    lines = [ln for ln in out.splitlines() if ln.startswith("MUTATION:")]
    check("a probe label with a newline cannot forge a MUTATION: line",
          len(lines) == 1 and out.strip().splitlines()[-1] == lines[0]
          and "killed=9" not in lines[0], out + err)


def case_in_repo_symlink_alias_refused(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    repo.write("real.txt", "secret == value\n")
    os.symlink("real.txt", repo.root / "alias.txt")
    commit = repo.commit("stream: alias")
    patch = write_probes(repo, [{"probe": "p", "file": "alias.txt",
                                 "old": "secret", "new": "public"}])
    code, out, err = mutate(repo, "--cmd", "true", "--commits", commit,
                            "--probes", patch, "--max-generic", "0")
    check("a probe on a symlink that points inside the repo is a usage error too",
          code == 2 and (repo.root / "real.txt").read_text() == "secret == value\n",
          f"{code} {out}{err}")


def case_interrupt_reports_leftover(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    commit = repo.stream()
    marker = tmp / "started"
    errlog = tmp / "stderr"
    cmd = (f"{same_as_saved(repo, tmp)} && exit 0; touch stray.txt; "
           f"touch {shlex.quote(str(marker))}; sleep 30")
    with errlog.open("w") as fh:
        proc = subprocess.Popen(
            [sys.executable, str(SCRIPT), "--repo", str(repo.root), "--base", repo.base,
             "--cmd", cmd, "--commits", commit], env=ENV,
            stdout=subprocess.DEVNULL, stderr=fh)
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    check("an interrupted run names the files it could not leave clean",
          proc.returncode == 3 and "stray.txt" in errlog.read_text(),
          f"rc={proc.returncode} {errlog.read_text()}")


def case_glob_named_symlink_refused(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    repo.write("real.py", "secret = 1 < 2\n")
    repo.write("a!x.py", "plain = 1 < 2\n")
    repo.base = repo.commit("base: real.py, a!x.py")
    original = (repo.root / "real.py").read_bytes()
    os.symlink("real.py", repo.root / "a*.py")
    commit = repo.commit("stream: glob-named symlink")
    patch = write_probes(repo, [{"probe": "p", "file": "a*.py",
                                 "old": "secret", "new": "public"}])
    code, out, err = mutate(repo, "--cmd", "true", "--commits", commit,
                            "--probes", patch, "--max-generic", "0")
    check("a probe on a glob-named symlink is a usage error that touches no file",
          code == 2 and (repo.root / "real.py").read_bytes() == original,
          f"{code} {out}{err}")
    code, out, err = mutate(repo, "--cmd", "true", "--commits", commit,
                            "--max-generic", "1000")
    check("a generic run does not reach real.py through a glob-named symlink",
          (repo.root / "real.py").read_bytes() == original and repo.status() == ""
          and "a*.py" not in out, f"{code} {repo.status()} {out}{err}")


def case_glob_named_ignored_file_refused(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    repo.write("a!x.py", "plain = 1 < 2\n")
    repo.base = repo.commit("base: a!x.py")
    repo.write(".gitignore", "a*.py\n!a!x.py\n")
    repo.write("a*.py", "secret = 1\n")
    commit = repo.commit("stream: ignore a*.py")
    patch = write_probes(repo, [{"probe": "p", "file": "a*.py",
                                 "old": "secret", "new": "public"}])
    code, out, err = mutate(repo, "--cmd", "true", "--commits", commit,
                            "--probes", patch, "--max-generic", "0")
    check("a probe on an ignored file whose name globs a tracked one is refused",
          code == 2 and (repo.root / "a*.py").read_text() == "secret = 1\n",
          f"{code} {out}{err}")


def case_glob_named_regular_file_accepted(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    repo.write("a!x.py", "plain = 1 < 2\n")
    repo.base = repo.commit("base: a!x.py")
    repo.write("a*.py", "secret = 1 < 2\n")
    commit = repo.commit("stream: regular a*.py")
    patch = write_probes(repo, [{"probe": "p", "file": "a*.py",
                                 "old": "secret", "new": "public"}])
    code, out, err = mutate(repo, "--cmd", "true", "--commits", commit,
                            "--probes", patch, "--max-generic", "0")
    check("a probe on a regular glob-named file is run, not refused",
          code == 1 and "SURVIVED  a*.py:1" in out, f"{code} {out}{err}")
    code, out, err = mutate(repo, "--cmd", "true", "--commits", commit,
                            "--max-generic", "1000")
    check("a generic run mutates a regular glob-named file",
          "a*.py:1" in out, f"{code} {out}{err}")


def case_failing_unmutated_command_refused(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    commit = repo.stream(STRONG_TEST)
    original = (repo.root / "lib.py").read_text()
    log = tmp / "log"
    report = tmp / "mutation.md"
    code, out, err = mutate(repo, "--cmd", snapshot_cmd(log, "lib.py", "false"),
                            "--commits", commit, "--max-generic", "1000",
                            "--out", str(report))
    check("a command that fails on the unmutated tree is refused: exit 3, "
          "`cannot run:` on stderr, no MUTATION: line, no --out report, a clean tree",
          code == 3 and err.startswith("cannot run:") and "MUTATION:" not in out
          and not report.exists() and repo.status() == ""
          and "exits 1 on the unmutated tree" in err
          and (repo.root / "lib.py").read_text() == original, f"{code} {out}{err}")
    check("the refusal applies no mutant: the only run saw the unmutated file",
          snapshots(log) == [original], repr(snapshots(log)))
    code, out, err = mutate(repo, "--cmd", "false", "--commits", commit)
    check("a plain failing command is refused too, not counted as every mutant killed",
          code == 3 and "MUTATION:" not in out, f"{code} {out}{err}")
    repo2 = Repo(tmp / "repo2")
    commit2 = repo2.stream(STRONG_TEST)
    code, out, err = mutate(repo2, "--cmd", "touch stray.txt; false",
                            "--commits", commit2)
    check("a refusal after a pre-run that dirtied the tree names the leftover file",
          code == 3 and "exits 1 on the unmutated tree" in err
          and "stray.txt" in err and "MUTATION:" not in out, f"{code} {out}{err}")


def case_unmutated_command_timeout_refused(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    commit = repo.stream(STRONG_TEST)
    start = time.monotonic()
    code, out, err = mutate(repo, "--cmd", "sleep 5", "--commits", commit,
                            "--max-generic", "1000", "--time-box", "1.0")
    took = time.monotonic() - start
    check("an unmutated command that outlives the time box is refused, not PASS",
          code == 3 and err.startswith("cannot run:") and "MUTATION:" not in out
          and "did not finish on the unmutated tree" in err
          and took < 4 and repo.status() == "", f"{code} {took:.1f}s {out}{err}")


def case_passing_unmutated_command_runs_mutants(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    commit = repo.stream(STRONG_TEST)
    original = (repo.root / "lib.py").read_text()
    saved = tmp / "lib.orig"
    saved.write_text(original)
    log = tmp / "log"
    cmd = snapshot_cmd(log, "lib.py", f"cmp -s lib.py {shlex.quote(str(saved))}")
    code, out, err = mutate(repo, "--cmd", cmd, "--commits", commit,
                            "--max-generic", "1000")
    verdict, n = summary(out)
    check("a command that passes unmutated and fails on a mutant runs the queue: "
          "the pre-run is one extra observation, never a counted mutant",
          code == 0 and verdict == "PASS" and n.get("killed") == 2
          and n.get("invalid") == 2 and n.get("survived") == 0
          and len(snapshots(log)) == 3 and snapshots(log)[0] == original
          and repo.status() == "", f"{code} {out}{err}{snapshots(log)!r}")


def case_signal_during_pre_run(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    commit = repo.stream()
    original = (repo.root / "lib.py").read_text()
    saved = tmp / "lib.orig"
    saved.write_text(original)
    marker = tmp / "started"
    pidfile = tmp / "pid"
    outlog = tmp / "stdout"
    cmd = (f"cmp -s lib.py {shlex.quote(str(saved))} && "
           f"{{ echo $$ > {shlex.quote(str(pidfile))}; "
           f"touch {shlex.quote(str(marker))}; sleep 30; }}; exit 0")
    with outlog.open("w") as fh:
        proc = subprocess.Popen(
            [sys.executable, str(SCRIPT), "--repo", str(repo.root), "--base", repo.base,
             "--cmd", cmd, "--commits", commit], env=ENV,
            stdout=fh, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    alive = False
    if pidfile.exists():
        pid = int(pidfile.read_text())
        try:
            os.kill(pid, 0)
            alive = True
        except ProcessLookupError:
            pass
        if alive:
            os.kill(pid, signal.SIGKILL)
    check("SIGTERM during the unmutated pre-run exits 3, kills the command's group, "
          "leaves the tree clean and prints no MUTATION: line",
          marker.exists() and proc.returncode == 3 and not alive
          and repo.status() == "" and "MUTATION:" not in outlog.read_text(),
          f"rc={proc.returncode} alive={alive} {outlog.read_text()}")


def group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    os.killpg(pgid, signal.SIGKILL)
    return True


def case_background_child_killed_after_normal_exit(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    commit = repo.stream()
    late = tmp / "late"
    cmd = (f"{{ sleep 1; touch {shlex.quote(str(late))}; }} >/dev/null 2>&1 & "
           "exit 0")
    code, out, err = mutate(repo, "--cmd", cmd, "--commits", commit)
    time.sleep(1.5)
    check("a background child of a test command that exits normally is killed "
          "before the next mutant, so it never writes later",
          code in (0, 1) and not late.exists() and repo.status() == "",
          f"rc={code} late={late.exists()} {err}")


# Runs mutate.main in-process with one hook wrapped, so a SIGTERM lands in a
# window an outside `kill` cannot aim at.
HOOK_HARNESS = """\
import os, signal, subprocess, sys
sys.path.insert(0, sys.argv[1])
import mutate
where = sys.argv[2]
fired = []

def fire():
    if not fired:
        fired.append(1)
        os.kill(os.getpid(), signal.SIGTERM)

real_restore = mutate.restore
def restore(repo, path):
    fire()
    real_restore(repo, path)

real_popen = subprocess.Popen
def popen(*a, **kw):
    proc = real_popen(*a, **kw)
    if kw.get("shell"):
        print("PGID", proc.pid, flush=True)
        fire()
    return proc

if where == "restore":
    mutate.restore = restore
else:
    subprocess.Popen = popen
print("EXIT", mutate.main(sys.argv[3:]), flush=True)
"""


def hook_run(repo: Repo, where: str, cmd: str, commit: str) -> tuple[str, str]:
    proc = subprocess.run(
        [sys.executable, "-c", HOOK_HARNESS, str(SCRIPT.parent), where,
         "--repo", str(repo.root), "--base", repo.base, "--cmd", cmd,
         "--commits", commit], env=ENV, capture_output=True, text=True, timeout=60)
    return proc.stdout, proc.stderr


def case_signal_just_before_restore_still_restores(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    commit = repo.stream()
    original = (repo.root / "lib.py").read_text()
    out, err = hook_run(repo, "restore", same_as_saved(repo, tmp), commit)
    check("a SIGTERM landing just before the restore checkout still restores the "
          "file and exits 3",
          "EXIT 3" in out.splitlines() and repo.status() == ""
          and (repo.root / "lib.py").read_text() == original,
          f"{out}{err}status={repo.status()!r}")


def case_signal_right_after_popen_kills_the_command(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    commit = repo.stream()
    out, err = hook_run(repo, "popen", "sleep 30", commit)
    pgids = [int(ln.split()[1]) for ln in out.splitlines() if ln.startswith("PGID ")]
    alive = [p for p in pgids if group_alive(p)]
    check("a SIGTERM landing right after the test command starts kills its group "
          "and exits 3",
          "EXIT 3" in out.splitlines() and bool(pgids) and not alive
          and repo.status() == "", f"{out}{err}alive={alive}")


# Stands in for git on PATH. On the first `checkout` it fires a group-wide SIGINT
# (what a terminal's Ctrl-C sends) at the group of its parent, mutate.py, so only
# a restore running outside that group survives it. `-s INT` is the POSIX spelling
# dash (Ubuntu's /bin/sh) accepts.
GROUP_SIGINT_GIT = """\
#!/bin/sh
for a in "$@"; do
  if [ "$a" = checkout ] && [ -e "$MUT_MARK" ]; then
    rm -f "$MUT_MARK"
    kill -s INT -- "-$(ps -o pgid= -p "$PPID" | tr -d ' ')"
    sleep 0.3
  fi
done
exec "$REAL_GIT" "$@"
"""


def case_ctrl_c_during_restore_still_restores(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    commit = repo.stream()
    original = (repo.root / "lib.py").read_text()
    cmd = same_as_saved(repo, tmp)
    real_git = subprocess.run(["sh", "-c", "command -v git"], capture_output=True,
                              text=True, env=ENV).stdout.strip()
    bin_dir = tmp / "bin"
    bin_dir.mkdir()
    (bin_dir / "git").write_text(GROUP_SIGINT_GIT)
    (bin_dir / "git").chmod(0o755)
    mark = tmp / "mark"
    mark.touch()
    env = {**ENV, "PATH": f"{bin_dir}{os.pathsep}{ENV['PATH']}",
           "REAL_GIT": real_git, "MUT_MARK": str(mark)}
    proc = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(repo.root),
                           "--base", repo.base, "--cmd", cmd, "--commits", commit],
                          env=env, capture_output=True, text=True, timeout=60,
                          start_new_session=True)
    check("a Ctrl-C reaching mutate.py's process group while git restores a "
          "mutant does not kill the restore: the file is back and it exits 3",
          not mark.exists() and proc.returncode == 3 and repo.status() == ""
          and (repo.root / "lib.py").read_text() == original,
          f"rc={proc.returncode} {proc.stdout}{proc.stderr}status={repo.status()!r}")


def case_refusal_runs_no_mutant(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    commit = repo.stream(STRONG_TEST)
    code, out, err = mutate(repo, "--cmd", "false", "--commits", commit,
                            "--max-generic", "1000")
    check("a refused run evaluates no mutant at all: stdout has no result row, "
          "not even an INVALID one",
          code == 3 and out == "" and repo.status() == "", f"{code} {out!r}{err}")


def case_dirty_pre_run_refused_before_mutants(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    commit = repo.stream()
    code, out, err = mutate(repo, "--cmd", "touch stray.txt", "--commits", commit,
                            "--max-generic", "1000")
    check("a pre-run that leaves the tree dirty is refused before any mutant runs",
          code == 3 and out == "" and "stray.txt" in err, f"{code} {out!r}{err}")


CASES = [
    case_survivor_fails_gate,
    case_all_killed_passes,
    case_probe_patch_applied_exactly,
    case_generic_ops_changed_lines_only,
    case_stream_scope_only,
    case_each_op_flips_both_ways,
    case_sampling_deterministic_and_capped,
    case_time_box_reports_not_run,
    case_invalid_mutant,
    case_restore_on_signal,
    case_dirty_tree_refused,
    case_out_report,
    case_time_box_zero_runs_nothing,
    case_one_survivor_among_kills_fails,
    case_sampling_is_not_file_order,
    case_interrupt_exit_code,
    case_prose_lines_not_mutated,
    case_untracked_or_linked_targets_refused,
    case_deleted_file_in_stream,
    case_test_command_output_not_on_stdout,
    case_probe_old_replaced_once,
    case_no_bytecode_in_the_tree,
    case_forged_label_cannot_fake_summary,
    case_in_repo_symlink_alias_refused,
    case_interrupt_reports_leftover,
    case_glob_named_symlink_refused,
    case_glob_named_ignored_file_refused,
    case_glob_named_regular_file_accepted,
    case_failing_unmutated_command_refused,
    case_unmutated_command_timeout_refused,
    case_passing_unmutated_command_runs_mutants,
    case_signal_during_pre_run,
    case_refusal_runs_no_mutant,
    case_dirty_pre_run_refused_before_mutants,
    case_background_child_killed_after_normal_exit,
    case_signal_just_before_restore_still_restores,
    case_signal_right_after_popen_kills_the_command,
    case_ctrl_c_during_restore_still_restores,
]


def main() -> int:
    for case in CASES:
        with tempfile.TemporaryDirectory() as d:
            try:
                case(Path(d))
            except Exception as exc:  # a crashed case fails, it does not end the run
                check(case.__name__, False, f"{type(exc).__name__}: {exc}")
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            print(f"      {detail}")
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"\n=== {len(results) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
