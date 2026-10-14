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
          snapshots(log) == [want] and "the ret clause" in out
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
    for snap in snapshots(log):
        try:
            idx, new = changed_line(OPS_LINES, snap)
        except AssertionError as exc:
            stacked = str(exc)
            break
        got[OPS_LINES[idx]].add(new)
    want = {ln: ({None} | exp) for ln, exp in OPS_EXPECTED.items()}
    check("each mutant changes one line of a clean file, never stacking on the last",
          stacked == "" and len(snapshots(log)) > 0, stacked + out)
    bad = {ln: (got[ln], want[ln]) for ln in OPS_LINES if got[ln] != want[ln]}
    check("== != < <= && || true false, return and await flip both ways, "
          "and nothing else is generated", not bad, f"{bad}\n{out}")
    check("the working tree is clean once all mutants ran",
          len(snapshots(log)) > 0 and repo.status() == "", out)


def case_sampling_deterministic_and_capped(tmp: Path) -> None:
    repo, log1, code1, out1 = run_ops(tmp, "--max-generic", "5", hashseed="0",
                                      name="log1")
    log2 = tmp / "log2"
    commit = repo.git("rev-parse", "HEAD")
    code2, out2, err2 = mutate(
        repo, "--cmd", snapshot_cmd(log2, "ops.txt"), "--commits", commit,
        "--max-generic", "5", env={**ENV, "PYTHONHASHSEED": "1"})
    check("two runs, even under different hash seeds, pick the same mutants in order",
          snapshots(log1) == snapshots(log2) and len(snapshots(log1)) > 0,
          out1 + out2 + err2)
    check("generic mutants never exceed --max-generic when more are available",
          len(snapshots(log1)) == 5, str(len(snapshots(log1))))
    log3 = tmp / "log3"
    patch = write_probes(repo, [
        {"probe": "p1", "file": "ops.txt", "old": "plain = 1", "new": "plain = 2"},
        {"probe": "p2", "file": "ops.txt", "old": "t_a = true", "new": "t_a = 3"}])
    code3, out3, err3 = mutate(
        repo, "--cmd", snapshot_cmd(log3, "ops.txt"), "--commits", commit,
        "--max-generic", "5", "--probes", patch)
    check("brief probes run first and do not count against --max-generic",
          len(snapshots(log3)) == 7 and "plain = 2" in snapshots(log3)[0]
          and "t_a = 3" in snapshots(log3)[1], out3 + err3)


def case_time_box_reports_not_run(tmp: Path) -> None:
    repo = Repo(tmp / "repo")
    repo.append("lib.py", "\n" + LIB_ADDED + "def above(n):\n    return n > 1\n")
    commit = repo.commit("stream")
    start = time.monotonic()
    code, out, err = mutate(repo, "--cmd", "sleep 0.6; false", "--commits", commit,
                            "--max-generic", "1000", "--time-box", "1.0")
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
    code, out, err = mutate(repo, "--cmd", "false", "--commits", commit,
                            "--max-generic", "1000")
    verdict, n = summary(out)
    check("a .py mutant that does not compile is INVALID, not killed or survived",
          n.get("invalid") == 2 and n.get("killed") == 2 and n.get("survived") == 0
          and "INVALID" in out, out + err)

    repo = Repo(tmp / "repo2")
    repo.write("m.txt", "a == b\n")
    commit = repo.commit("stream")
    code, out, err = mutate(repo, "--cmd", "false", "--commits", commit)
    verdict, n = summary(out)
    check("a failing non-.py mutant with no --check-cmd is UNCLASSIFIED, never killed, "
          "and does not fail the gate",
          n.get("unclassified") == 2 and n.get("killed") == 0 and code == 0
          and verdict == "PASS" and "UNCLASSIFIED" in out, out + err)
    code, out, err = mutate(repo, "--cmd", "false", "--commits", commit,
                            "--check-cmd", "test -s {file}")
    verdict, n = summary(out)
    check("--check-cmd exiting non-zero is INVALID; a passing one lets the test "
          "command's failure count as killed",
          n.get("invalid") == 1 and n.get("killed") == 1 and n.get("unclassified") == 0,
          out + err)


def case_restore_on_signal(tmp: Path) -> None:
    for sig in (signal.SIGTERM, signal.SIGINT):
        repo = Repo(tmp / f"repo{int(sig)}")
        commit = repo.stream()
        original = (repo.root / "lib.py").read_text()
        marker = tmp / f"started{int(sig)}"
        cmd = f"touch {shlex.quote(str(marker))}; sleep 30"
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
