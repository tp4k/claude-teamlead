#!/usr/bin/env python3
"""Regression suite for scripts/red_freeze.py:  python3 scripts/test_red_freeze.py

The freeze is the one mechanical guard between "the implementer wrote its tests
first" and "the implementer wrote its tests first and then loosened them until
the code passed". So the cases that matter most are the weakenings a real GREEN
phase produces — an assertion widened, a test deleted, a file dropped — and the
additions it must *not* flag, because a check that fires on every new test
above a frozen one is a check the implementer learns to ignore.

Each case builds a throwaway repo with git's global and system config switched
off, so a user's hooks, signing or templates never reach it.

No pytest dependency — the skill's scripts run with bare python3, and a suite
that needs an install is a suite nobody runs.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "red_freeze.py"
ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
       "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}

RED_TEST = """\
def test_over_limit_rejected():
    r = hit(limit=2, times=3)
    assert r.status == 429


def test_window_resets():
    assert hit(limit=1, times=1, after=61).status == 200
"""
EXTRA_ABOVE = "import pytest\n\n\ndef test_extra():\n    assert hit(limit=0) is None\n"
EXTRA_BELOW = "def test_boundary():\n    assert hit(limit=2, times=2).status == 200\n"

results: list[tuple[str, bool, str]] = []


class Repo:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.git("init", "-q", "-b", "main")
        self.write("src/limit.py", "def hit(**kw):\n    raise NotImplementedError\n")
        self.base = self.commit("base")

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.root), *args], env=ENV,
                              check=True, capture_output=True, text=True).stdout.strip()

    def write(self, rel: str, text: str) -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def commit(self, msg: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", msg)
        return self.git("rev-parse", "HEAD")

    def red(self) -> str:
        self.write("tests/test_limit.py", RED_TEST)
        return self.commit("red: rate-limit tests")

    def edit(self, rel: str, old: str, new: str) -> None:
        p = self.root / rel
        text = p.read_text()
        assert old in text, (rel, old)
        p.write_text(text.replace(old, new, 1))


def run(repo: Repo, *reds: str, cmd: str | None = None) -> tuple[int, str]:
    args = [sys.executable, str(SCRIPT), "--repo", str(repo.root), *reds]
    if cmd is not None:
        args[2:2] = ["--run", cmd]
    proc = subprocess.run(args, env=ENV, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def case_untouched_red_is_frozen(tmp: Path) -> None:
    repo = Repo(tmp)
    red = repo.red()
    repo.write("src/limit.py", "def hit(**kw):\n    return Resp(429)\n")
    repo.commit("green")
    code, out = run(repo, red)
    check("untouched RED lines pass after a production-only GREEN",
          code == 0 and out.startswith("RED_FROZEN"), out)


def case_added_tests_are_allowed(tmp: Path) -> None:
    repo = Repo(tmp)
    red = repo.red()
    repo.write("tests/test_limit.py",
               EXTRA_ABOVE + "\n\n" + RED_TEST + "\n\n" + EXTRA_BELOW)
    repo.commit("extra tests")
    code, out = run(repo, red)
    check("tests added above and below frozen ones do not flag them", code == 0, out)


def case_reindent_is_allowed(tmp: Path) -> None:
    repo = Repo(tmp)
    red = repo.red()
    body = "\n".join(("    " + ln) if ln else ln for ln in RED_TEST.splitlines())
    body = body.replace("():", "(self):")
    repo.write("tests/test_limit.py", "class TestLimit:\n" + body + "\n")
    repo.commit("wrap in a class")
    code, out = run(repo, red)
    # The two `def` lines gained `self`, so they are edits; the asserts only moved.
    check("re-indented asserts are not flagged, changed signatures are",
          code == 1 and "assert r.status == 429" not in out
          and "def test_over_limit_rejected():" in out, out)


def case_weakened_assertion_is_caught(tmp: Path) -> None:
    repo = Repo(tmp)
    red = repo.red()
    repo.edit("tests/test_limit.py", "assert r.status == 429",
              "assert r.status in (200, 429)")
    repo.commit("green (loosened)")
    code, out = run(repo, red)
    check("a widened assertion is reported with its original text",
          code == 1 and out.startswith("RED_CHANGED")
          and "tests/test_limit.py: assert r.status == 429" in out, out)


def case_deleted_test_is_caught(tmp: Path) -> None:
    repo = Repo(tmp)
    red = repo.red()
    repo.write("tests/test_limit.py", RED_TEST.split("\n\n\n")[0] + "\n")
    repo.commit("drop the flaky one")
    code, out = run(repo, red)
    check("a deleted frozen test is reported",
          code == 1 and "def test_window_resets():" in out, out)


def case_deleted_file_is_caught(tmp: Path) -> None:
    repo = Repo(tmp)
    red = repo.red()
    repo.git("rm", "-q", "tests/test_limit.py")
    repo.commit("remove tests")
    code, out = run(repo, red)
    check("a deleted RED test file is reported",
          code == 1 and "no longer exists" in out, out)


def case_duplicate_line_counts_twice(tmp: Path) -> None:
    repo = Repo(tmp)
    twice = "    assert ok()\n    assert ok()\n"
    repo.write("tests/test_twice.py", "def test_twice():\n" + twice)
    red = repo.commit("red")
    repo.edit("tests/test_twice.py", twice, "    assert ok()\n")
    repo.commit("one is enough")
    code, out = run(repo, red)
    check("removing one of two identical frozen lines is reported",
          code == 1 and out.count("assert ok()") == 1, out)


def case_each_missing_copy_is_listed(tmp: Path) -> None:
    repo = Repo(tmp)
    thrice = "    assert ok()\n" * 3
    repo.write("tests/test_thrice.py", "def test_thrice():\n" + thrice)
    red = repo.commit("red")
    repo.edit("tests/test_thrice.py", thrice, "    assert ok()\n")
    repo.commit("keep one")
    code, out = run(repo, red)
    check("two of three identical frozen lines removed lists both",
          code == 1 and out.count("assert ok()") == 2
          and out.startswith("RED_CHANGED — 2 of 4"), out)


def case_every_red_commit_is_checked(tmp: Path) -> None:
    repo = Repo(tmp)
    red1 = repo.red()
    repo.write("tests/test_retry.py",
               "def test_no_retry_on_400():\n    assert calls(400) == 1\n")
    red2 = repo.commit("red: rework row 2")
    repo.edit("tests/test_retry.py", "== 1", ">= 1")
    repo.commit("green")
    code, out = run(repo, red1, red2)
    check("the second RED commit's lines are checked too",
          code == 1 and "tests/test_retry.py: assert calls(400) == 1" in out, out)


def case_non_test_file_is_a_note(tmp: Path) -> None:
    repo = Repo(tmp)
    repo.write("tests/test_limit.py", RED_TEST)
    repo.write("src/limit.py", "LIMIT = 2\n")
    red = repo.commit("red, with a production edit")
    code, out = run(repo, red)
    notes = out.split("note:", 1)[-1]
    check("a production file in the RED commit is a note, not a failure",
          code == 0 and "note:" in out and "src/limit.py" in notes
          and "tests/test_limit.py" not in notes, out)


def case_test_path_shapes(tmp: Path) -> None:
    repo = Repo(tmp)
    shapes = ("pkg/limit_test.go", "web/src/limit.spec.ts",
              "web/__tests__/limit.tsx", "spec/limit_spec.rb")
    for rel in shapes:
        repo.write(rel, "x\n")
    red = repo.commit("red across languages")
    code, out = run(repo, red)
    check("go, ts spec, __tests__ and rspec paths all count as tests",
          code == 0 and "note:" not in out, out)


def case_root_commit_red(tmp: Path) -> None:
    root = tmp / "fresh"
    root.mkdir()
    for args in (("init", "-q", "-b", "main"), ("add", "-A"),
                 ("commit", "-q", "-m", "red")):
        if args[0] == "add":
            (root / "test_a.py").write_text("def test_a():\n    assert 1\n")
        subprocess.run(["git", "-C", str(root), *args], env=ENV, check=True)
    proc = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(root), "HEAD"],
                          env=ENV, capture_output=True, text=True)
    check("a RED commit with no parent is read, not skipped",
          proc.returncode == 0 and "2 frozen lines" in proc.stdout,
          proc.stdout + proc.stderr)


def case_non_ancestor_is_usage_error(tmp: Path) -> None:
    repo = Repo(tmp)
    repo.git("checkout", "-q", "-b", "side")
    side = repo.red()
    repo.git("checkout", "-q", "main")
    code, out = run(repo, side)
    check("a RED commit off the branch is exit 2",
          code == 2 and "not an ancestor" in out, out)


def case_bad_revision_is_usage_error(tmp: Path) -> None:
    repo = Repo(tmp)
    code, out = run(repo, "deadbeef")
    check("an unknown revision is exit 2",
          code == 2 and out.startswith("red_freeze:"), out)


# A stand-in test runner: fails with a behavioural message until the code
# returns 429, and says so differently once it does.
CHECK = ("src = open('src/limit.py').read()\n"
         "assert 'Resp(429)' in src, 'expected 429, got NotImplementedError'\n"
         "print('1 passed')\n")
CHECK_CMD = f"{shlex.quote(sys.executable)} tests/check.py"


def case_run_reports_the_red_commit_failure(tmp: Path) -> None:
    repo = Repo(tmp)
    repo.write("tests/check.py", CHECK)
    red = repo.red()
    repo.write("src/limit.py", "def hit(**kw):\n    return Resp(429)\n")
    repo.commit("green")
    code, out = run(repo, red, cmd=CHECK_CMD)
    # At HEAD the command passes; only a run of the RED tree prints the failure.
    check("--run prints the failure the RED commit produced, not HEAD's result",
          code == 0 and out.startswith("RED_FROZEN")
          and f"RED run {red[:9]}: exit 1" in out
          and "expected 429, got NotImplementedError" in out
          and "1 passed" not in out, out)


def case_run_catches_a_red_that_passes(tmp: Path) -> None:
    repo = Repo(tmp)
    repo.write("src/limit.py", "def hit(**kw):\n    return Resp(429)\n")
    repo.commit("behaviour already there")
    repo.write("tests/check.py", CHECK)
    red = repo.commit("red that is green on arrival")
    code, out = run(repo, red, cmd=CHECK_CMD)
    check("a RED commit whose tests pass is RED_PASSES, exit 1",
          code == 1 and f"RED_PASSES {red[:9]}" in out, out)


def case_run_leaves_the_repo_alone(tmp: Path) -> None:
    repo = Repo(tmp)
    repo.write("tests/check.py", CHECK)
    red = repo.red()
    repo.write("src/limit.py", "def hit(**kw):\n    return Resp(429)\n")
    repo.commit("green")
    run(repo, red, cmd=f"{CHECK_CMD}; echo junk > stray.txt")
    status = repo.git("status", "--porcelain")
    check("--run works in an export: the repo's tree and status are untouched",
          status == "" and not (repo.root / "stray.txt").exists(), status)


LONG = ("for i in range(1, 301):\n    print(f'line {i}')\n"
        "raise SystemExit(1)\n")


def case_run_marks_omitted_lines(tmp: Path) -> None:
    repo = Repo(tmp)
    repo.write("tests/check.py", LONG)
    red = repo.red()
    _, out = run(repo, red, cmd=CHECK_CMD)
    block = out.split(f"RED run {red[:9]}: exit 1", 1)[-1]
    check("--run marks a cut tail, so a test absent from it is not read as passing",
          "earlier lines omitted" in block and "line 300" in block
          and "line 1\n" not in block, out)


CASES = [
    case_untouched_red_is_frozen,
    case_added_tests_are_allowed,
    case_reindent_is_allowed,
    case_weakened_assertion_is_caught,
    case_deleted_test_is_caught,
    case_deleted_file_is_caught,
    case_duplicate_line_counts_twice,
    case_each_missing_copy_is_listed,
    case_every_red_commit_is_checked,
    case_non_test_file_is_a_note,
    case_test_path_shapes,
    case_root_commit_red,
    case_non_ancestor_is_usage_error,
    case_bad_revision_is_usage_error,
    case_run_reports_the_red_commit_failure,
    case_run_catches_a_red_that_passes,
    case_run_leaves_the_repo_alone,
    case_run_marks_omitted_lines,
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
