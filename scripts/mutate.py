#!/usr/bin/env python3
"""In-place mutation gate: does the stream's test command notice a broken line?

Usage: python3 mutate.py --repo <worktree> --base <sha> --cmd "<test command>"
           (--commits <sha> [<sha> ...] | --files <path> [<path> ...])
           [--probes <probes.json>] [--check-cmd "<cmd with {file}>"]
           [--max-generic 20] [--time-box 600] [--out <report.md>]

The verifier runs this after every brief command passes and while every
repository writer is idle. Before any mutant the test command runs once on the
unmodified tree, inside the time box; a failure or timeout there is a refusal,
because a command that fails for any reason would otherwise kill every mutant.
It works in the given worktree, one mutant at a
time: patch one file, run the test command, restore the file with
`git checkout -- <file>`. A survivor (the command still passes on broken code)
means the tests do not pin that line.

Mutants, in run order:
  * probes — `--probes` is a JSON list of {"probe", "file", "old", "new"}: the
    implementer's concrete patch per brief `probe:` line. `old` is replaced once,
    verbatim. An `old` absent from the file is NOT APPLIED and fails the gate,
    because an unapplied probe measures nothing. `file` must be a tracked regular
    file (not a symlink, not untracked or ignored) inside the repo, or the run is
    a usage error. Probes do not count against `--max-generic`.
  * generic — text ops on this stream's changed lines only: delete the line,
    flip `==`/`!=`, `<`/`<=`, `&&`/`||`, `true`/`false`, drop `return`, drop
    `await`. Blank lines, comment-only lines, bare-string/docstring lines in `.py`
    files, files ending `.md`/`.markdown`/`.rst`, test files, and paths that are
    not tracked regular files inside the repo are skipped. They are sampled by
    sha256 of `file:line` (stable across runs and machines), at most
    `--max-generic` of them.

Stream scope: parallel implementers share one tree, so candidates are the lines
this stream changed, never the whole `<base>..HEAD` range. With `--commits`
that is every HEAD line `git blame <base>..HEAD` attributes to a listed commit;
with `--files` it is every line `git diff -U0 <base> HEAD` shows in the listed
paths (a directory covers the files beneath it).

Results: KILLED (test command failed), SURVIVED (it passed), INVALID (the mutant
does not parse: stdlib `compile()` for `.py`, or `--check-cmd` exiting non-zero),
UNCLASSIFIED (a non-`.py` mutant failed and no `--check-cmd` could say whether
it parses: never counted killed, not a gate failure), NOT RUN (the time box ran
out: never counted killed), NOT APPLIED (probe text absent).

The last stdout line is
`MUTATION: PASS|FAIL killed=<n> survived=<n> invalid=<n> unclassified=<n>
not_run=<n> not_applied=<n>` on one line.
Exit 0 PASS, 1 FAIL (any survivor or unapplied probe), 2 usage error (including
neither or both of `--commits` / `--files`, or a probe file that is not a
tracked regular file), 3 cannot run (dirty tree at start, the test command
failing or not finishing on the unmutated tree, restore failed, interrupted, or
a dirty tree at the end). SIGTERM and SIGINT
kill the test command's process group and restore the file being mutated
before exiting. The group is also killed when the command exits on its own, so
nothing it backgrounded survives into the restore or the next mutant.

No dependencies beyond git, for the same reason as the rest of `scripts/`.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
import tokenize
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Union

from red_freeze import TEST_PATH, GitError, git

EXIT_PASS, EXIT_FAIL, EXIT_USAGE, EXIT_CANNOT_RUN = 0, 1, 2, 3
DEFAULT_MAX_GENERIC = 20
DEFAULT_TIME_BOX = 600.0
COMMENT_PREFIXES = ("#", "//", "/*", "*", "--")
PROSE_SUFFIXES = (".md", ".markdown", ".rst")
REGULAR_FILE_MODES = ("100644", "100755")
KILL_GRACE = 5.0
# How often a running test command is checked for a recorded signal.
POLL_SECONDS = 0.1

KILLED, SURVIVED, INVALID = "KILLED", "SURVIVED", "INVALID"
UNCLASSIFIED, NOT_RUN, NOT_APPLIED = "UNCLASSIFIED", "NOT RUN", "NOT APPLIED"

Repl = Union[str, Callable[["re.Match[str]"], str]]


def _flip_bool(m: "re.Match[str]") -> str:
    word = m.group(0)
    flipped = {"true": "false", "false": "true", "True": "False", "False": "True"}
    return flipped[word]


# (name, pattern, replacement). Every flip is listed in both directions; a
# pattern must not match inside a longer operator (`<` in `<=` or `<<`).
OPS: list[tuple[str, "re.Pattern[str]", Repl]] = [
    ("eq->ne", re.compile(r"(?<![=!<>])==(?!=)"), "!="),
    ("ne->eq", re.compile(r"!=(?!=)"), "=="),
    ("lt->le", re.compile(r"(?<!<)<(?![<=])"), "<="),
    ("le->lt", re.compile(r"(?<!<)<=(?![=>])"), "<"),
    ("and->or", re.compile(r"&&"), "||"),
    ("or->and", re.compile(r"\|\|"), "&&"),
    ("true->false", re.compile(r"\b(?:true|True)\b"), _flip_bool),
    ("false->true", re.compile(r"\b(?:false|False)\b"), _flip_bool),
    ("drop-return", re.compile(r"\breturn\b[ \t]*"), ""),
    ("drop-await", re.compile(r"\bawait\b[ \t]*"), ""),
]
DELETE_LINE = "delete-line"


@dataclass(frozen=True)
class Mutant:
    file: str
    line: int
    label: str
    old: str = ""  # probes: exact text to replace
    new: str = ""  # probes: replacement
    replacement: Optional[str] = None  # generic: the whole new line, "" deletes
    is_probe: bool = False


class Terminated(BaseException):
    def __init__(self, signum: int) -> None:
        super().__init__(signum)
        self.signum = signum


class UsageError(Exception):
    pass


def generic_mutations(line: str) -> list[tuple[str, str]]:
    """(op name, mutated line text) for one line, without its line ending."""
    out: list[tuple[str, str]] = [(DELETE_LINE, "")]
    for name, pattern, repl in OPS:
        for m in pattern.finditer(line):
            new = repl(m) if callable(repl) else repl
            out.append((name, line[:m.start()] + new + line[m.end():]))
    return [(n, t) for n, t in out if n == DELETE_LINE or t != line]


def is_candidate_line(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped) and not stripped.startswith(COMMENT_PREFIXES)


def docstring_lines(text: str) -> set[int]:
    """Lines of `text` that hold a bare string statement (a docstring)."""
    found: set[int] = set()
    first = -1
    only_strings = True
    seen = False
    skip = (tokenize.NL, tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT)
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type in skip:
                continue
            if tok.type in (tokenize.NEWLINE, tokenize.ENDMARKER):
                if seen and only_strings:
                    found.update(range(first, tok.start[0] + 1))
                first, only_strings, seen = -1, True, False
                continue
            if not seen:
                first, seen = tok.start[0], True
            if tok.type != tokenize.STRING:
                only_strings = False
    except (tokenize.TokenError, SyntaxError):
        return found
    return found


def tracked_regular_file(repo: str, rel: str) -> bool:
    """`rel` is a tracked regular file that resolves inside the repo, not in .git."""
    try:
        listing = git(repo, "--literal-pathspecs", "ls-files", "-s", "-z", "--", rel)
    except GitError:
        return False
    entries = [e for e in listing.split("\0") if e]
    if len(entries) != 1:
        return False
    info, _, path = entries[0].partition("\t")
    if path != rel or info.split()[0] not in REGULAR_FILE_MODES:
        return False
    root = Path(repo).resolve()
    resolved = (root / rel).resolve()
    return root in resolved.parents and (root / ".git") not in (
        resolved, *resolved.parents)


def read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8", "surrogateescape")


def write_text(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8", "surrogateescape"))


def resolve_commit(repo: str, rev: str) -> str:
    return git(repo, "rev-parse", "--verify", f"{rev}^{{commit}}").strip()


def changed_files(repo: str, base: str) -> list[str]:
    out = git(repo, "-c", "core.quotepath=off", "diff", "--name-only", "-z",
              "--no-renames", "--diff-filter=d", base, "HEAD")
    return [p for p in out.split("\0") if p]


BLAME_HEADER = re.compile(r"^([0-9a-f]{40}) \d+ (\d+)(?: \d+)?$")


def blame_lines(repo: str, base: str, path: str, commits: set[str]) -> set[int]:
    """HEAD line numbers of `path` that one of `commits` last wrote."""
    out = git(repo, "blame", "--porcelain", f"{base}..HEAD", "--", path)
    lines: set[int] = set()
    for raw in out.splitlines():
        m = BLAME_HEADER.match(raw)
        if m and m.group(1) in commits:
            lines.add(int(m.group(2)))
    return lines


HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def diff_lines(repo: str, base: str, paths: list[str]) -> dict[str, set[int]]:
    """HEAD line numbers added or changed since `base` in `paths`."""
    out = git(repo, "-c", "core.quotepath=off", "diff", "-U0", "--no-color",
              "--no-ext-diff", "--no-renames", base, "HEAD", "--", *paths)
    found: dict[str, set[int]] = {}
    current: Optional[str] = None
    for raw in out.splitlines():
        if raw.startswith("+++ "):
            current = raw[6:] if raw.startswith("+++ b/") else None
            continue
        m = HUNK.match(raw)
        if m and current is not None:
            start = int(m.group(1))
            count = 1 if m.group(2) is None else int(m.group(2))
            found.setdefault(current, set()).update(range(start, start + count))
    return found


def stream_lines(repo: str, base: str, commits: list[str],
                 files: list[str]) -> dict[str, set[int]]:
    if files:
        return diff_lines(repo, base, files)
    wanted = {resolve_commit(repo, c) for c in commits}
    found: dict[str, set[int]] = {}
    for path in changed_files(repo, base):
        lines = blame_lines(repo, base, path, wanted)
        if lines:
            found[path] = lines
    return found


def sample_key(file: str, line: int) -> str:
    return hashlib.sha256(f"{file}:{line}".encode()).hexdigest()


def generic_mutants(repo: str, scope: dict[str, set[int]],
                    cap: int) -> list[Mutant]:
    keyed: list[tuple[str, str, int, int, Mutant]] = []
    for path, numbers in scope.items():
        if TEST_PATH.search(path) or path.endswith(PROSE_SUFFIXES):
            continue
        target = Path(repo) / path
        if not tracked_regular_file(repo, path) or not target.is_file():
            continue
        content = read_text(target)
        lines = content.splitlines(keepends=True)
        prose = docstring_lines(content) if path.endswith(".py") else set()
        for number in sorted(numbers):
            if not 1 <= number <= len(lines):
                continue
            raw = lines[number - 1]
            body = raw.rstrip("\r\n")
            ending = raw[len(body):]
            if number in prose or not is_candidate_line(body):
                continue
            for idx, (op, text) in enumerate(generic_mutations(body)):
                replacement = "" if op == DELETE_LINE else text + ending
                mutant = Mutant(path, number, op, replacement=replacement)
                keyed.append((sample_key(path, number), path, number, idx, mutant))
    keyed.sort(key=lambda row: row[:4])
    return [row[4] for row in keyed[:max(cap, 0)]]


def load_probes(path: str, repo: str) -> list[Mutant]:
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise UsageError(f"--probes {path}: {exc}") from exc
    if not isinstance(data, list):
        raise UsageError(f"--probes {path}: expected a JSON list")
    probes: list[Mutant] = []
    for i, item in enumerate(data):
        ok = isinstance(item, dict) and all(
            isinstance(item.get(k), str) for k in ("probe", "file", "old", "new"))
        if not ok or not item["old"]:
            raise UsageError(f"--probes {path}: entry {i} needs string "
                             "probe/file/new and a non-empty old")
        rel = Path(item["file"])
        if rel.is_absolute() or ".." in rel.parts:
            raise UsageError(f"--probes {path}: entry {i} file must be "
                             "repo-relative")
        if not tracked_regular_file(repo, item["file"]):
            raise UsageError(f"--probes {path}: entry {i} file must be a tracked "
                             "regular file inside the repo")
        probes.append(Mutant(item["file"], 0, item["probe"], old=item["old"],
                             new=item["new"], is_probe=True))
    return probes


def mutated_text(text: str, m: Mutant) -> Optional[str]:
    """The file text with `m` applied, or None when it does not apply."""
    if m.is_probe:
        return text.replace(m.old, m.new, 1) if m.old in text else None
    lines = text.splitlines(keepends=True)
    if m.replacement is None or not 1 <= m.line <= len(lines):
        return None
    lines[m.line - 1] = m.replacement
    return "".join(lines)


def status_porcelain(repo: str) -> str:
    return git(repo, "status", "--porcelain").strip()


def restore(repo: str, path: str) -> None:
    try:
        git(repo, "checkout", "--", path)
    except GitError as exc:
        raise RestoreError(f"could not restore {path}: {exc}") from exc


class RestoreError(Exception):
    pass


def run_shell(cmd: str, repo: str, timeout: float) -> Optional[int]:
    """Exit code of `cmd`, or None when it outlived `timeout` and was killed.

    The command's whole process group is killed however it ends, so a child it
    backgrounded cannot outlive it into the restore or the next mutant.
    """
    exit_if_signalled()
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.Popen(cmd, shell=True, cwd=repo, env=env,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        return wait_polling(proc, time.monotonic() + max(timeout, 0.0))
    finally:
        kill_group(proc)


def wait_polling(proc: "subprocess.Popen[bytes]", deadline: float) -> Optional[int]:
    """Wait for `proc`, raising Terminated within POLL_SECONDS of a signal."""
    while True:
        exit_if_signalled()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            return proc.wait(timeout=min(POLL_SECONDS, remaining))
        except subprocess.TimeoutExpired:
            continue


def kill_group(proc: "subprocess.Popen[bytes]") -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.wait(timeout=KILL_GRACE)
    except subprocess.TimeoutExpired:
        pass


@dataclass
class Row:
    mutant: Mutant
    result: str


def line_of(text: str, needle: str) -> int:
    return text[:text.index(needle)].count("\n") + 1


def evaluate(repo: str, m: Mutant, args: argparse.Namespace,
             deadline: float) -> tuple[Mutant, str]:
    """Apply `m`, classify it, and always restore the file."""
    target = Path(repo) / m.file
    if not target.is_file():
        return m, NOT_APPLIED
    original = read_text(target)
    text = mutated_text(original, m)
    if text is None:
        return m, NOT_APPLIED
    if m.is_probe:
        m = Mutant(m.file, line_of(original, m.old), m.label, m.old, m.new,
                   is_probe=True)
    try:
        write_text(target, text)
        return m, classify(repo, m, text, args, deadline)
    finally:
        restore(repo, m.file)


def classify(repo: str, m: Mutant, text: str, args: argparse.Namespace,
             deadline: float) -> str:
    is_python = m.file.endswith(".py")
    if is_python:
        try:
            compile(text, m.file, "exec")
        except (SyntaxError, ValueError):
            return INVALID
    if args.check_cmd:
        cmd = args.check_cmd.replace("{file}", shlex.quote(m.file))
        code = run_shell(cmd, repo, deadline - time.monotonic())
        if code is None:
            return NOT_RUN
        if code != 0:
            return INVALID
    code = run_shell(args.cmd, repo, deadline - time.monotonic())
    if code is None:
        return NOT_RUN
    if code == 0:
        return SURVIVED
    if is_python or args.check_cmd:
        return KILLED
    return UNCLASSIFIED


def one_line(text: str) -> str:
    return text.replace("\r", " ").replace("\n", " ")


def describe(row: Row) -> str:
    m = row.mutant
    file = one_line(m.file)
    where = f"{file}:{m.line}" if m.line else file
    kind = "probe" if m.is_probe else "op"
    return f"{row.result}  {where}  {kind}={one_line(m.label)}"


def write_report(path: str, rows: list[Row], summary: str) -> None:
    lines = ["| file | line | op / probe | result |", "|---|---|---|---|"]
    for r in rows:
        m = r.mutant
        label = m.label.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {m.file} | {m.line or '-'} | {label} | {r.result} |")
    Path(path).write_text("\n".join(lines) + f"\n\n{summary}\n")


def summarize(rows: list[Row]) -> tuple[str, int]:
    count = {r: sum(1 for row in rows if row.result == r)
             for r in (KILLED, SURVIVED, INVALID, UNCLASSIFIED, NOT_RUN, NOT_APPLIED)}
    failed = count[SURVIVED] > 0 or count[NOT_APPLIED] > 0
    line = (f"MUTATION: {'FAIL' if failed else 'PASS'} killed={count[KILLED]} "
            f"survived={count[SURVIVED]} invalid={count[INVALID]} "
            f"unclassified={count[UNCLASSIFIED]} not_run={count[NOT_RUN]} "
            f"not_applied={count[NOT_APPLIED]}")
    return line, EXIT_FAIL if failed else EXIT_PASS


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="In-place mutation gate.")
    p.add_argument("--repo", required=True)
    p.add_argument("--base", required=True)
    p.add_argument("--cmd", required=True)
    p.add_argument("--commits", nargs="+", default=[])
    p.add_argument("--files", nargs="+", default=[])
    p.add_argument("--probes")
    p.add_argument("--check-cmd")
    p.add_argument("--max-generic", type=int, default=DEFAULT_MAX_GENERIC)
    p.add_argument("--time-box", type=float, default=DEFAULT_TIME_BOX)
    p.add_argument("--out")
    args = p.parse_args(argv)
    if bool(args.commits) == bool(args.files):
        p.error("give exactly one of --commits or --files")
    return args


# Signals are only recorded by the handler and acted on at fixed points (before
# a command starts, while it is polled, between mutants), so no signal can land
# between Popen and its handle or between a mutation and its restore.
_signalled: list[int] = []


def on_signal(signum: int, _frame: object) -> None:
    _signalled.append(signum)


def exit_if_signalled() -> None:
    if _signalled:
        raise Terminated(_signalled[0])


def run(args: argparse.Namespace) -> int:
    repo = args.repo
    try:
        base = resolve_commit(repo, args.base)
        if status_porcelain(repo):
            print("cannot run: the working tree is not clean", file=sys.stderr)
            return EXIT_CANNOT_RUN
        probes = load_probes(args.probes, repo) if args.probes else []
        scope = stream_lines(repo, base, args.commits, args.files)
    except GitError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except UsageError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    queue = probes + generic_mutants(repo, scope, args.max_generic)
    _signalled.clear()
    old_handlers = {s: signal.signal(s, on_signal)
                    for s in (signal.SIGTERM, signal.SIGINT)}
    try:
        return run_queue(repo, queue, args)
    finally:
        for s, handler in old_handlers.items():
            signal.signal(s, handler)


def report_leftover(repo: str) -> str:
    leftover = status_porcelain(repo)
    if leftover:
        print(f"cannot run: the tree is not clean after the run:\n{leftover}",
              file=sys.stderr)
    return leftover


def unmutated_failure(repo: str, args: argparse.Namespace,
                      deadline: float) -> Optional[str]:
    """Why `--cmd` cannot be trusted on the unmodified tree, or None when it passes."""
    remaining = deadline - time.monotonic()
    code = run_shell(args.cmd, repo, remaining) if remaining > 0 else None
    if code is None:
        return "the test command did not finish on the unmutated tree in the time box"
    if code != 0:
        return f"the test command exits {code} on the unmutated tree"
    return None


def run_queue(repo: str, queue: list[Mutant], args: argparse.Namespace) -> int:
    deadline = time.monotonic() + args.time_box
    rows: list[Row] = []
    try:
        try:
            refusal = unmutated_failure(repo, args, deadline)
            if refusal:
                print(f"cannot run: {refusal}", file=sys.stderr)
                report_leftover(repo)
                return EXIT_CANNOT_RUN
            if report_leftover(repo):
                return EXIT_CANNOT_RUN
            for m in queue:
                exit_if_signalled()
                if time.monotonic() >= deadline:
                    rows.append(Row(m, NOT_RUN))
                    print(describe(rows[-1]), flush=True)
                    continue
                done, result = evaluate(repo, m, args, deadline)
                rows.append(Row(done, result))
                print(describe(rows[-1]), flush=True)
            exit_if_signalled()
        except Terminated as exc:
            print(f"cannot run: interrupted by signal {exc.signum}", file=sys.stderr)
            report_leftover(repo)
            return EXIT_CANNOT_RUN
        except RestoreError as exc:
            print(f"cannot run: {exc}", file=sys.stderr)
            return EXIT_CANNOT_RUN
        if report_leftover(repo):
            return EXIT_CANNOT_RUN
        summary, code = summarize(rows)
        if args.out:
            write_report(args.out, rows, summary)
        print(summary)
        return code
    except Terminated as exc:
        print(f"cannot run: interrupted by signal {exc.signum}", file=sys.stderr)
        return EXIT_CANNOT_RUN


def main(argv: Optional[list[str]] = None) -> int:
    return run(parse_args(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
