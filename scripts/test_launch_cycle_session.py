#!/usr/bin/env python3
"""Regression suite for scripts/launch_cycle_session.py.

Run it with:  python3 scripts/test_launch_cycle_session.py

The script exists so a cycle never ends with "now cd there and relaunch Claude
yourself". Fake `cmux` and `tmux` binaries on PATH record their argv, so each
case checks the exact command a multiplexer is handed, and that the resume
command still reads as one word after the multiplexer's shell splits it.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "launch_cycle_session.py"
SLUG = "1291-openai-cache-tokens"
RESUME = f"claude '/teamlead:cycle --resume {SLUG}'"

results: list[tuple[str, bool, str]] = []

FAKE = """\
#!/bin/sh
for a in "$@"; do printf '%s\\n' "$a"; done > "$ARGV_LOG"
printf '%s\\n' "${FAKE_OUT:-}"
exit "${FAKE_RC:-0}"
"""


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def fake_bin(tmp: Path, *names: str) -> Path:
    bin_dir = tmp / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name in names:
        (bin_dir / name).write_text(FAKE)
        (bin_dir / name).chmod(0o755)
    return bin_dir


def launch(tmp: Path, tree: Path, slug: str, env: dict[str, str],
           ) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    log = tmp / "argv.log"
    base = {k: v for k, v in os.environ.items()
            if not k.startswith(("CMUX_", "TMUX"))}
    base["PATH"] = f"{env.pop('BIN')}{os.pathsep}/usr/bin:/bin"
    proc = subprocess.run([sys.executable, str(SCRIPT), str(tree), slug],
                          env={**base, "ARGV_LOG": str(log), **env},
                          capture_output=True, text=True, check=False)
    argv = log.read_text().splitlines() if log.exists() else []
    return proc, argv


def tree_in(tmp: Path, name: str = "iap-tree") -> Path:
    tree = tmp / name
    tree.mkdir()
    return tree


def case_cmux_opens_a_workspace_in_the_tree(tmp: Path) -> None:
    tree = tree_in(tmp)
    proc, argv = launch(tmp, tree, SLUG, {"BIN": str(fake_bin(tmp, "cmux", "tmux")),
                                          "CMUX_SOCKET_PATH": "/x.sock",
                                          "FAKE_OUT": "OK workspace:7"})
    want = ["new-workspace", "--name", SLUG, "--cwd", str(tree),
            "--command", RESUME, "--focus", "true"]
    check("inside cmux, a workspace opens in the tree running the resume command, "
          "and the launch is reported",
          proc.returncode == 0 and argv == want
          and f"LAUNCHED cmux {tree}" in proc.stdout,
          f"rc={proc.returncode} argv={argv} out={proc.stdout!r} err={proc.stderr!r}")


def case_tmux_opens_a_window_in_the_tree(tmp: Path) -> None:
    tree = tree_in(tmp)
    proc, argv = launch(tmp, tree, SLUG, {"BIN": str(fake_bin(tmp, "tmux")),
                                          "TMUX": "/tmp/tmux-1/default,1,0"})
    want = ["new-window", "-c", str(tree), "-n", SLUG, RESUME]
    check("inside tmux (and not cmux), a window opens in the tree running the "
          "resume command",
          proc.returncode == 0 and argv == want
          and f"LAUNCHED tmux {tree}" in proc.stdout,
          f"rc={proc.returncode} argv={argv} out={proc.stdout!r}")


def case_resume_command_survives_the_shell(tmp: Path) -> None:
    tree = tree_in(tmp, "dir with space")
    proc, argv = launch(tmp, tree, SLUG, {"BIN": str(fake_bin(tmp, "cmux")),
                                          "CMUX_SOCKET_PATH": "/x.sock"})
    command = argv[argv.index("--command") + 1] if "--command" in argv else ""
    check("the multiplexer's shell splits the command into claude and one prompt, "
          "and a tree path with a space stays one --cwd argument",
          proc.returncode == 0
          and shlex.split(command) == ["claude", f"/teamlead:cycle --resume {SLUG}"]
          and argv[argv.index("--cwd") + 1] == str(tree),
          f"rc={proc.returncode} argv={argv}")


def case_no_multiplexer_prints_the_command(tmp: Path) -> None:
    tree = tree_in(tmp)
    proc, argv = launch(tmp, tree, SLUG, {"BIN": str(fake_bin(tmp, "cmux", "tmux"))})
    check("outside cmux and tmux nothing is launched; the manual command is "
          "printed and the exit is 1",
          proc.returncode == 1 and argv == []
          and f"MANUAL: cd {shlex.quote(str(tree))} && {RESUME}" in proc.stdout,
          f"rc={proc.returncode} argv={argv} out={proc.stdout!r}")


def case_failed_launch_falls_back_to_manual(tmp: Path) -> None:
    tree = tree_in(tmp)
    proc, _ = launch(tmp, tree, SLUG, {"BIN": str(fake_bin(tmp, "cmux")),
                                       "CMUX_SOCKET_PATH": "/x.sock",
                                       "FAKE_RC": "1"})
    check("a multiplexer that refuses the launch is reported, and the manual "
          "command is printed with exit 1",
          proc.returncode == 1 and "MANUAL: " in proc.stdout
          and "cmux" in proc.stderr,
          f"rc={proc.returncode} out={proc.stdout!r} err={proc.stderr!r}")


def case_bad_input_refused(tmp: Path) -> None:
    tree = tree_in(tmp)
    bin_dir = str(fake_bin(tmp, "cmux"))
    bad_slug, argv1 = launch(tmp, tree, "x'; rm -rf ~; '",
                             {"BIN": bin_dir, "CMUX_SOCKET_PATH": "/x.sock"})
    missing, argv2 = launch(tmp, tmp / "nope", SLUG,
                            {"BIN": bin_dir, "CMUX_SOCKET_PATH": "/x.sock"})
    check("a slug outside [a-z0-9-] or a tree that is not a directory exits 2 "
          "and launches nothing",
          bad_slug.returncode == 2 and missing.returncode == 2
          and argv1 == [] and argv2 == [],
          f"{bad_slug.returncode} {missing.returncode} {argv1} {argv2}")


CASES = [
    case_cmux_opens_a_workspace_in_the_tree,
    case_tmux_opens_a_window_in_the_tree,
    case_resume_command_survives_the_shell,
    case_no_multiplexer_prints_the_command,
    case_failed_launch_falls_back_to_manual,
    case_bad_input_refused,
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
