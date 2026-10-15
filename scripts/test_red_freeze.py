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
import time
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
    run(repo, red, cmd=f"{CHECK_CMD}; echo junk >> src/limit.py")
    status = repo.git("status", "--porcelain")
    check("--run restores a clean tree even if the command edits a tracked file",
          status == "" and "junk" not in (repo.root / "src/limit.py").read_text(),
          status)


def case_run_sees_untracked_deps(tmp: Path) -> None:
    repo = Repo(tmp)
    repo.write(".gitignore", "deps/\n")
    repo.write("tests/check.py",
               "print('dep says', open('deps/lib.txt').read().strip())\n" + CHECK)
    red = repo.red()
    repo.write("src/limit.py", "def hit(**kw):\n    return Resp(429)\n")
    repo.commit("green")
    repo.write("deps/lib.txt", "installed")
    repo.write("notes.txt", "scratch")
    code, out = run(repo, red, cmd=CHECK_CMD)
    check("--run sees an ignored, untracked dependency directory of the worktree",
          f"RED run {red[:9]}: exit 1" in out and "dep says installed" in out
          and "expected 429, got NotImplementedError" in out, out)
    check("an untracked, non-ignored file does not block --run and survives it",
          code == 0 and (repo.root / "notes.txt").read_text() == "scratch", out)


def case_run_restores_branch_and_head(tmp: Path) -> None:
    repo = Repo(tmp)
    repo.write("tests/check.py", CHECK)
    red = repo.red()
    repo.write("src/limit.py", "def hit(**kw):\n    return Resp(429)\n")
    green = repo.commit("green")
    code, out = run(repo, red, cmd=f"{CHECK_CMD}; git rev-parse HEAD")
    block = out.split("RED run", 1)[-1]
    check("--run runs on the RED commit in place, then restores branch and HEAD",
          red in block and repo.git("symbolic-ref", "--short", "HEAD") == "main"
          and repo.git("rev-parse", "HEAD") == green
          and repo.git("status", "--porcelain") == "", out)
    # A command that exits non-zero must not leave HEAD on the RED commit either.
    run(repo, red, cmd="exit 3")
    check("branch and HEAD are restored after a failing command too",
          repo.git("symbolic-ref", "--short", "HEAD") == "main"
          and repo.git("rev-parse", "HEAD") == green, repo.git("status", "-sb"))
    code, out = run(repo, red, cmd="echo ERR-LINE >&2; echo OUT-LINE; exit 3")
    check("a failing command keeps its exit code and its stderr+stdout tail",
          f"RED run {red[:9]}: exit 3" in out and "ERR-LINE\nOUT-LINE" in out, out)


def case_run_refuses_dirty_tree(tmp: Path) -> None:
    repo = Repo(tmp)
    repo.write("tests/check.py", CHECK)
    red = repo.red()
    head = repo.commit("more")
    repo.write("src/limit.py", "def hit(**kw):\n    return 'local edit'\n")
    code, out = run(repo, red, cmd=f"{CHECK_CMD}; touch ran.txt")
    check("--run refuses a dirty tree: clear message, no checkout, edit kept",
          code == 2 and "clean" in out and "RED run" not in out
          and repo.git("symbolic-ref", "--short", "HEAD") == "main"
          and repo.git("rev-parse", "HEAD") == head
          and "local edit" in (repo.root / "src/limit.py").read_text()
          and not (repo.root / "ran.txt").exists(), out)


def case_run_refuses_staged_change(tmp: Path) -> None:
    repo = Repo(tmp)
    repo.write("tests/check.py", CHECK)
    red = repo.red()
    repo.commit("more")
    repo.write("src/limit.py", "def hit(**kw):\n    return 'local edit'\n")
    repo.git("add", "src/limit.py")
    code, out = run(repo, red, cmd=CHECK_CMD)
    check("--run refuses a tree whose only change is staged, and keeps it staged",
          code == 2 and "clean" in out and "RED run" not in out
          and "local edit" in (repo.root / "src/limit.py").read_text()
          and repo.git("diff", "--cached", "--name-only") == "src/limit.py", out)


def case_run_keeps_ignored_files(tmp: Path) -> None:
    repo = Repo(tmp)
    repo.write("local.cfg", "fixture\n")
    repo.write("tests/check.py", CHECK)
    red = repo.red()
    repo.git("rm", "-q", "local.cfg")
    repo.write(".gitignore", "local.cfg\n")
    head = repo.commit("untrack local.cfg")
    repo.write("local.cfg", "MY-REAL-SECRET\n")
    code, out = run(repo, red, cmd="cat local.cfg")
    cfg = repo.root / "local.cfg"
    check("--run never overwrites an ignored file that RED tracked: exit 2, file kept",
          code == 2 and cfg.exists() and cfg.read_text() == "MY-REAL-SECRET\n"
          and "RED run" not in out
          and repo.git("symbolic-ref", "--short", "HEAD") == "main"
          and repo.git("rev-parse", "HEAD") == head, out)


def case_run_restores_on_sigterm(tmp: Path) -> None:
    repo = Repo(tmp)
    repo.write("tests/check.py", CHECK)
    red = repo.red()
    green = repo.commit("more")
    args = [sys.executable, str(SCRIPT), "--repo", str(repo.root),
            "--run", "exec sleep 30", red]
    with subprocess.Popen(args, env=ENV, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT) as proc:
        deadline = time.monotonic() + 20
        while (repo.git("branch", "--show-current") != ""
               and time.monotonic() < deadline):
            time.sleep(0.05)
        proc.terminate()
        proc.wait(timeout=20)
    check("SIGTERM during --run still puts the branch and HEAD back",
          repo.git("branch", "--show-current") == "main"
          and repo.git("rev-parse", "HEAD") == green
          and repo.git("status", "--porcelain") == "", repo.git("status", "-sb"))


def case_run_restores_a_detached_head(tmp: Path) -> None:
    repo = Repo(tmp)
    repo.write("tests/check.py", CHECK)
    red = repo.red()
    green = repo.commit("more")
    repo.git("checkout", "-q", "--detach", green)
    run(repo, red, cmd=CHECK_CMD)
    check("--run started on a detached HEAD puts that commit back, still detached",
          repo.git("branch", "--show-current") == ""
          and repo.git("rev-parse", "HEAD") == green
          and repo.git("status", "--porcelain") == "", repo.git("status", "-sb"))

LATE_WRITE = "AFTER RESTORE"


def late_writer(delay: float, pidfile: str | None = None) -> str:
    """Shell words for a python child that sleeps, then overwrites a tracked file."""
    pid = f"open({pidfile!r}, 'w').write(str(os.getpid())); " if pidfile else ""
    code = (f"import os, time; {pid}time.sleep({delay}); "
            f"open('src/limit.py', 'w').write({LATE_WRITE!r})")
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"


def case_sigterm_kills_compound_command_descendants(tmp: Path) -> None:
    repo = Repo(tmp)
    repo.write("tests/check.py", CHECK)
    red = repo.red()
    green = repo.commit("more")
    delay = 1.5
    # Written by the descendant itself, outside the repo (an untracked file in it
    # would fail the clean-status check below), so SIGTERM cannot land before a
    # descendant exists.
    ready = tmp.parent / f"{tmp.name}.ready"
    args = [sys.executable, str(SCRIPT), "--repo", str(repo.root),
            "--run", f"{late_writer(delay, str(ready))}; :", red]
    with subprocess.Popen(args, env=ENV, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT) as proc:
        deadline = time.monotonic() + 20
        while (not (ready.exists() and ready.read_text().isdigit())
               and time.monotonic() < deadline):
            time.sleep(0.05)
        proc.terminate()
        proc.wait(timeout=20)
    time.sleep(delay + 1.0)
    status = repo.git("status", "--porcelain")
    check("SIGTERM during `child; :` kills the child, so the restored tree stays clean",
          status == "" and repo.git("branch", "--show-current") == "main"
          and repo.git("rev-parse", "HEAD") == green
          and LATE_WRITE not in (repo.root / "src/limit.py").read_text(), status)


POPEN_HARNESS = """\
import os, signal, subprocess, sys
sys.path.insert(0, sys.argv[1])
import red_freeze
real_init = subprocess.Popen.__init__
kept = []
def init(self, *args, **kwargs):
    real_init(self, *args, **kwargs)
    kept.append(self)
    if kwargs.get("shell"):
        os.kill(os.getpid(), signal.SIGTERM)
subprocess.Popen.__init__ = init
try:
    red_freeze.run_red(sys.argv[2], sys.argv[3], sys.argv[4])
    print("RETURNED")
except SystemExit as e:
    print("EXIT", e.code)
try:
    os.waitpid(-1, os.WNOHANG)
    print("CHILD-NOT-REAPED")
except ChildProcessError:
    print("REAPED")
"""


def case_sigterm_while_popen_starts_kills_the_child(tmp: Path) -> None:
    repo = Repo(tmp)
    repo.write("tests/check.py", CHECK)
    red = repo.red()
    green = repo.commit("more")
    delay = 1.0
    proc = subprocess.run(
        [sys.executable, "-c", POPEN_HARNESS, str(SCRIPT.parent), str(repo.root),
         red, f"{late_writer(delay)}; :"],
        env=ENV, capture_output=True, text=True, timeout=30)
    time.sleep(delay + 1.0)
    status = repo.git("status", "--porcelain")
    check("a SIGTERM landing while Popen starts still kills and reaps the child",
          proc.stdout.split() == ["EXIT", "143", "REAPED"] and status == ""
          and repo.git("branch", "--show-current") == "main"
          and repo.git("rev-parse", "HEAD") == green
          and LATE_WRITE not in (repo.root / "src/limit.py").read_text(),
          f"{proc.stdout}{proc.stderr}status={status!r}")


CLEANUP_HARNESS = """\
import os, signal, subprocess, sys
sys.path.insert(0, sys.argv[1])
import red_freeze
repo, red, cmd, at_kill, at_restore, mode = sys.argv[2:8]
os.environ["RF_PGID"] = str(os.getpid())
os.environ["RF_MARK"] = repo + ".mark"

def mine(*_):
    pass

signal.signal(signal.SIGINT, mine)
signal.signal(signal.SIGTERM, mine)

def fire(name):
    if name != "-":
        os.kill(os.getpid(), getattr(signal, "SIG" + name))

real_kill = red_freeze._kill_group
real_run = subprocess.run

def kill(proc):
    fire(at_kill)
    real_kill(proc)

def run(args, *a, **kw):
    if "-f" in args:
        fire(at_restore)
        if mode == "group":
            open(os.environ["RF_MARK"], "w").close()
        if mode == "restorefail":
            return subprocess.CompletedProcess(args, 1, "", "forced")
    return real_run(args, *a, **kw)

red_freeze._kill_group = kill
subprocess.run = run
try:
    print("RETURNED", red_freeze.run_red(repo, red, cmd)[0])
except SystemExit as e:
    print("EXIT", e.code)
except red_freeze.GitError:
    print("GITERROR")
print("HANDLERS", signal.getsignal(signal.SIGINT) is mine,
      signal.getsignal(signal.SIGTERM) is mine)
try:
    os.waitpid(-1, os.WNOHANG)
    print("CHILD-NOT-REAPED")
except ChildProcessError:
    print("REAPED")
if mode == "again":
    red_freeze._kill_group = real_kill
    try:
        print("SECOND RETURNED", red_freeze.run_red(repo, red, "exit 0")[0])
    except SystemExit as e:
        print("SECOND EXIT", e.code)
"""

# Fires a group-wide SIGINT (what a terminal's Ctrl-C sends) as git begins to
# update HEAD, so only a restore running outside the group survives it.
GROUP_SIGINT_HOOK = """\
#!/bin/sh
[ "$1" = prepared ] && [ -e "$RF_MARK" ] || exit 0
rm -f "$RF_MARK"
kill -INT -- "-$RF_PGID"
sleep 0.3
"""
DELAY_SLOW = 1.0
# SIGTERMs the harness (the shell's parent) mid-run, so an exit is already raised
# when cleanup starts.
MIDRUN_CMD = "kill -TERM $PPID; sleep 30"
# Output that is not UTF-8 makes communicate() raise, so cleanup is entered with the
# deferral flag still unset.
DECODE_CMD = f"printf '\\377'; {late_writer(DELAY_SLOW)} >/dev/null 2>&1 &"


def cleanup_run(tmp: Path, at_kill: str, at_restore: str, normal: bool = False,
                mode: str = "plain", hook: bool = False) -> tuple[str, str, bool]:
    """Run run_red in a harness that fires signals inside its cleanup.

    Returns (harness output, detail, True when the repo is back on `main` at the
    pre-run commit with a clean tree and the late-writing descendant never wrote).
    """
    tmp.mkdir(exist_ok=True)
    repo = Repo(tmp)
    repo.write("tests/check.py", CHECK)
    red = repo.red()
    green = repo.commit("more")
    if hook:
        path = repo.root / ".git/hooks/reference-transaction"
        path.write_text(GROUP_SIGINT_HOOK)
        path.chmod(0o755)
    cmd = "exit 1" if normal else f"{late_writer(DELAY_SLOW)}; :"
    cmd = MIDRUN_CMD if mode == "midrun" else cmd
    cmd = DECODE_CMD if mode == "decode" else cmd
    proc = subprocess.run(
        [sys.executable, "-c", CLEANUP_HARNESS, str(SCRIPT.parent), str(repo.root),
         red, cmd, at_kill, at_restore, mode],
        env=ENV, capture_output=True, text=True, timeout=30,
        start_new_session=True)
    time.sleep(DELAY_SLOW + 1.0)
    status = repo.git("status", "--porcelain")
    restored = (status == "" and repo.git("branch", "--show-current") == "main"
                and repo.git("rev-parse", "HEAD") == green
                and LATE_WRITE not in (repo.root / "src/limit.py").read_text())
    return proc.stdout, f"{proc.stdout}{proc.stderr}status={status!r}", restored


def case_sigterm_at_group_kill_start_still_cleans_up(tmp: Path) -> None:
    out, detail, restored = cleanup_run(tmp / "a", "TERM", "-")
    check("a SIGTERM landing as the group kill starts still kills the group, "
          "restores the checkout and exits 143",
          out.split()[:2] == ["EXIT", "143"] and "REAPED" in out and restored, detail)


def case_sigterm_during_restore_checkout_does_not_abort_it(tmp: Path) -> None:
    out, detail, restored = cleanup_run(tmp / "a", "-", "TERM")
    check("a SIGTERM landing during the restore checkout does not abort it; exit 143",
          out.split()[:2] == ["EXIT", "143"] and restored, detail)


def case_second_signal_in_cleanup_keeps_the_first_exit_code(tmp: Path) -> None:
    out, detail, restored = cleanup_run(tmp / "a", "TERM", "INT")
    check("a SIGINT after a SIGTERM in cleanup changes nothing: restored, exit 143",
          out.split()[:2] == ["EXIT", "143"] and restored, detail)
    out, detail, restored = cleanup_run(tmp / "b", "INT", "TERM")
    check("a SIGINT in cleanup is protected too, and its code 130 wins over a "
          "later SIGTERM",
          out.split()[:2] == ["EXIT", "130"] and restored, detail)


def case_signal_in_cleanup_after_a_normal_exit_is_not_swallowed(tmp: Path) -> None:
    out, detail, restored = cleanup_run(tmp / "a", "TERM", "-", normal=True)
    check("a SIGTERM in cleanup after the command exited normally still exits 143, "
          "after the restore",
          out.split()[:2] == ["EXIT", "143"] and restored, detail)


def case_handlers_are_the_callers_after_run_red(tmp: Path) -> None:
    out, detail, _ = cleanup_run(tmp / "a", "-", "-", normal=True)
    check("SIGINT and SIGTERM carry the caller's handlers again after run_red returns",
          out.split()[:2] == ["RETURNED", "1"] and "HANDLERS True True" in out, detail)
    out, detail, _ = cleanup_run(tmp / "b", "TERM", "INT", normal=True)
    check("SIGINT and SIGTERM carry the caller's handlers again after run_red raises",
          out.split()[:2] == ["EXIT", "143"] and "HANDLERS True True" in out, detail)


def case_signal_in_cleanup_does_not_replace_an_exit_already_raised(tmp: Path) -> None:
    # The command SIGTERMs run_red mid-run (exit 143 already propagating); a SIGINT
    # then lands in cleanup. The first exit's code stands.
    out, detail, restored = cleanup_run(tmp / "a", "INT", "-", mode="midrun")
    check("a SIGINT in cleanup after a mid-run SIGTERM keeps exit 143, not 130",
          out.split()[:2] == ["EXIT", "143"] and restored, detail)


def case_a_signal_in_one_run_does_not_leak_into_the_next(tmp: Path) -> None:
    out, detail, _ = cleanup_run(tmp / "a", "TERM", "-", normal=True, mode="again")
    check("a signal recorded in one run_red call does not abort the next call",
          out.split()[:2] == ["EXIT", "143"] and "SECOND RETURNED 0" in out, detail)


def case_group_sigint_during_restore_does_not_break_it(tmp: Path) -> None:
    out, detail, restored = cleanup_run(tmp / "a", "-", "-", normal=True, mode="group",
                                        hook=True)
    check("a SIGINT to red_freeze's whole process group during the restore "
          "checkout leaves branch, HEAD and tree restored; exit 130",
          out.split()[:2] == ["EXIT", "130"] and restored, detail)


def case_signal_in_cleanup_entered_with_the_flag_unset_still_cleans_up(
        tmp: Path) -> None:
    out, detail, restored = cleanup_run(tmp / "a", "TERM", "-", mode="decode")
    check("a SIGTERM in cleanup entered through a decode error still kills the "
          "group and restores the checkout",
          restored and "UnicodeDecodeError" in detail, detail)


def case_failed_restore_leaves_the_callers_handlers(tmp: Path) -> None:
    out, detail, _ = cleanup_run(tmp / "a", "-", "-", normal=True, mode="restorefail")
    check("a restore that raises GitError still puts the caller's handlers back",
          "GITERROR" in out and "HANDLERS True True" in out, detail)


def case_background_descendant_killed_after_normal_exit(tmp: Path) -> None:
    repo = Repo(tmp)
    repo.write("tests/check.py", CHECK)
    red = repo.red()
    repo.commit("more")
    delay = 3.0
    pidfile = tmp.parent / f"{tmp.name}.pid"
    cmd = (f"{late_writer(delay, str(pidfile))} >/dev/null 2>&1 & "
           f"while [ ! -s {shlex.quote(str(pidfile))} ]; do sleep 0.05; done")
    start = time.monotonic()
    code, out = run(repo, red, cmd=cmd)
    took = time.monotonic() - start
    pid = int(pidfile.read_text()) if pidfile.exists() and pidfile.read_text() else 0
    gone = False
    stop = time.monotonic() + 1.0
    while pid and time.monotonic() < stop:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            gone = True
            break
        time.sleep(0.05)
    time.sleep(max(0.0, start + delay + 1.0 - time.monotonic()))
    status = repo.git("status", "--porcelain")
    check("a backgrounded descendant is killed once the command returns",
          pid > 0 and took < delay - 1.0 and gone and status == ""
          and LATE_WRITE not in (repo.root / "src/limit.py").read_text(),
          f"pid={pid} took={took:.2f} gone={gone} status={status!r}\n{out}")


def case_descendant_is_dead_before_the_restore(tmp: Path) -> None:
    repo = Repo(tmp)
    repo.write("tests/check.py", CHECK)
    red = repo.red()
    repo.commit("more")
    spin = (f"end=$(( $(date +%s) + 5 )); while [ $(date +%s) -lt $end ]; "
            f"do echo {LATE_WRITE} > src/limit.py; done")
    run(repo, red, cmd=f"({spin}) >/dev/null 2>&1 & sleep 0.3")
    time.sleep(0.3)
    status = repo.git("status", "--porcelain")
    check("a descendant rewriting a tracked file nonstop is dead before the restore",
          status == "", status)


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
    case_run_sees_untracked_deps,
    case_run_restores_branch_and_head,
    case_run_refuses_dirty_tree,
    case_run_refuses_staged_change,
    case_run_keeps_ignored_files,
    case_run_restores_on_sigterm,
    case_sigterm_kills_compound_command_descendants,
    case_sigterm_while_popen_starts_kills_the_child,
    case_sigterm_at_group_kill_start_still_cleans_up,
    case_sigterm_during_restore_checkout_does_not_abort_it,
    case_second_signal_in_cleanup_keeps_the_first_exit_code,
    case_signal_in_cleanup_after_a_normal_exit_is_not_swallowed,
    case_handlers_are_the_callers_after_run_red,
    case_signal_in_cleanup_does_not_replace_an_exit_already_raised,
    case_a_signal_in_one_run_does_not_leak_into_the_next,
    case_group_sigint_during_restore_does_not_break_it,
    case_signal_in_cleanup_entered_with_the_flag_unset_still_cleans_up,
    case_failed_restore_leaves_the_callers_handlers,
    case_background_descendant_killed_after_normal_exit,
    case_descendant_is_dead_before_the_restore,
    case_run_restores_a_detached_head,
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
