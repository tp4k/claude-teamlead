#!/usr/bin/env python3
"""Check that a workstream's RED tests survived GREEN unchanged.

Usage: python3 red_freeze.py --repo <repo> [--head <rev>] <red-commit> [<red> ...]

The implementer writes its tests first, commits them alone (the RED commit), and
only then writes production code. The moment the code resists is exactly when a
loosened assertion looks reasonable, so every line a RED commit added is frozen
until `done`. This script is the whole enforcement: each non-blank line a RED
commit added must still be present, as written, in the same file at `--head`.

Additions after RED are allowed — a new test, a stronger fixture, an extra
import on its own line. A frozen line that was edited, moved into a helper with
different text, or deleted is reported. Matching is on stripped content with
multiplicity, not on position, so tests added above a frozen line do not flag
it. The blind spot is the same text surviving elsewhere in the same file: an
assertion cut from its test but left in a helper nothing calls still counts as
present, so the reviewer checks that frozen assertions still sit in live tests.

Prints `RED_FROZEN` (exit 0) or `RED_CHANGED` plus one line per missing frozen
line (exit 1). A bad revision, or a RED commit that is not an ancestor of
`--head`, is a usage error (exit 2). A RED commit touching a file that does not
look like a test is a `note:`, not a failure — the reviewer judges that one.

`--run "<test command>"` also runs that command in a clean export of each RED
commit and prints `RED run <sha>: exit <n>` with the output's tail. That is the
failure the report's `red:` lines quote: a report written after GREEN has only
HEAD's and the probes' output at hand, and quotes one of those instead. A RED
run that exits 0 is `RED_PASSES <sha>` (exit 1) — tests green on arrival. Only
the exit code is read, so one test passing beside failing ones is not flagged:
it shows as a `red:` line with no matching failure in the block — unless
the block opens with `(... N earlier lines omitted)`, when the failure may sit
above the tail and the reviewer reruns the command to see it. Every RED
given gets the same command, so on a rework round pass `--run` this round's RED
alone — an earlier RED predates this round's tests. The export holds tracked
files only, so the command must work from a fresh clone.

No dependencies beyond git, for the same reason as the rest of `scripts/`.
"""
from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
import tarfile
import tempfile
from collections import Counter

TEST_PATH = re.compile(
    r"(^|[/_.-])(tests?|specs?|__tests__)([/_.-]|$)", re.IGNORECASE
)


class GitError(Exception):
    pass


def git(repo: str, *args: str) -> str:
    proc = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if proc.returncode != 0:
        why = proc.stderr.strip() or f"exited {proc.returncode}"
        raise GitError(f"git {' '.join(args)}: {why}")
    return proc.stdout


def is_ancestor(repo: str, sha: str, head: str) -> bool:
    cmd = ["git", "-C", repo, "merge-base", "--is-ancestor", sha, head]
    return subprocess.run(cmd).returncode == 0


def added_lines(repo: str, sha: str) -> dict[str, Counter[str]]:
    """Non-blank lines `sha` added, stripped, per file path."""
    names = git(repo, "diff-tree", "--root", "--no-commit-id", "--no-renames",
                "-r", "--name-only", "-z", sha).split("\0")
    out: dict[str, Counter[str]] = {}
    for path in filter(None, names):
        diff = git(repo, "show", "--format=", "--no-color", "--no-ext-diff",
                   "--no-renames", "-U0", sha, "--", path)
        out[path] = Counter(
            ln[1:].strip() for ln in diff.splitlines()
            if ln.startswith("+") and not ln.startswith("+++") and ln[1:].strip()
        )
    return out


def lines_at(repo: str, head: str, path: str) -> Counter[str] | None:
    try:
        text = git(repo, "show", f"{head}:{path}")
    except GitError:
        return None
    return Counter(ln.strip() for ln in text.splitlines() if ln.strip())


def check(repo: str, head: str, reds: list[str]) -> tuple[list[str], list[str], int]:
    """Return (missing lines, notes, frozen line count)."""
    missing: list[str] = []
    notes: list[str] = []
    frozen = 0
    for red in reds:
        sha = git(repo, "rev-parse", "--verify", f"{red}^{{commit}}").strip()
        short = sha[:9]
        if not is_ancestor(repo, sha, head):
            raise GitError(f"{short} is not an ancestor of {head}")
        for path, want in added_lines(repo, sha).items():
            if not TEST_PATH.search(path):
                notes.append(f"note: {short} {path} is in a RED commit "
                             "but does not look like a test file")
            frozen += sum(want.values())
            have = lines_at(repo, head, path)
            if have is None:
                missing.append(f"{short} {path}: file no longer exists at {head}")
                continue
            for line, n in (want - have).items():
                missing.extend(f"{short} {path}: {line}" for _ in range(n))
    return missing, notes, frozen


TAIL = 200


def run_red(repo: str, red: str, cmd: str) -> tuple[int, str]:
    """Run `cmd` in an export of `red`; return (exit code, output tail)."""
    tar = subprocess.run(["git", "-C", repo, "archive", "--format=tar", red],
                         capture_output=True)
    if tar.returncode != 0:
        raise GitError(f"git archive {red}: {tar.stderr.decode().strip()}")
    with tempfile.TemporaryDirectory() as tree:
        with tarfile.open(fileobj=io.BytesIO(tar.stdout)) as tf:
            # The data filter exists from 3.9.17/3.12; older 3.9s extract as before.
            if hasattr(tarfile, "data_filter"):
                tf.extractall(tree, filter="data")
            else:
                tf.extractall(tree)
        proc = subprocess.run(cmd, shell=True, cwd=tree, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines = proc.stdout.rstrip("\n").splitlines()
    if len(lines) > TAIL:
        cut = len(lines) - TAIL
        lines = [f"(... {cut} earlier lines omitted)", *lines[-TAIL:]]
    return proc.returncode, "\n".join(lines)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Check that RED-commit test lines survive to HEAD."
    )
    ap.add_argument("--repo", default=".")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--run", metavar="CMD",
                    help="test command to run in an export of each RED commit")
    ap.add_argument("reds", nargs="+", metavar="red-commit")
    args = ap.parse_args(argv)
    runs: list[tuple[str, int, str]] = []
    try:
        missing, notes, frozen = check(args.repo, args.head, args.reds)
        if args.run:
            for red in args.reds:
                short = git(args.repo, "rev-parse", "--short=9", red).strip()
                runs.append((short, *run_red(args.repo, red, args.run)))
    except GitError as e:
        print(f"red_freeze: {e}", file=sys.stderr)
        return 2
    passing = [short for short, code, _ in runs if code == 0]
    if missing:
        print(f"RED_CHANGED — {len(missing)} of {frozen} frozen lines "
              f"missing at {args.head}")
        print("\n".join(missing))
    else:
        print(f"RED_FROZEN — {len(args.reds)} RED commit(s), {frozen} frozen "
              f"lines, all present at {args.head}")
    if notes:
        print("\n".join(notes))
    for short, code, tail in runs:
        print(f"\nRED run {short}: exit {code}\n{tail}")
    for short in passing:
        print(f"RED_PASSES {short} — its tests pass at the RED commit")
    return 1 if missing or passing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
