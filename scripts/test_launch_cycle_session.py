#!/usr/bin/env python3
"""Regression suite for scripts/launch_cycle_session.py.

Run it with:  python3 scripts/test_launch_cycle_session.py

The script exists so a cycle never ends with "now cd there and relaunch Claude
yourself", in whatever terminal the user runs. A fake `claude` records its
argv, its cwd and whether the caller's session identity leaked into its
environment, so each case checks exactly what Claude Code is asked to start.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "launch_cycle_session.py"
SLUG = "1291-openai-cache-tokens"
PROMPT = f"/teamlead:cycle --resume {SLUG}"

results: list[tuple[str, bool, str]] = []

# Mirrors what `claude --bg` prints on success (Claude Code 2.1.301).
FAKE = """\
#!/bin/sh
for a in "$@"; do printf '%s\\n' "$a"; done > "$LOG_DIR/argv"
pwd -P > "$LOG_DIR/cwd"
printf '%s' "${CLAUDE_CODE_SESSION_ID:-}${CLAUDECODE:-}" > "$LOG_DIR/leak"
if [ -n "${FAKE_ERR:-}" ]; then printf '%s\\n' "$FAKE_ERR" >&2; exit 1; fi
printf 'Starting background service…\\nbackgrounded · 1a2b3c4d · %s\\n' "${2#--name=}"
"""


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def fake_claude(tmp: Path, where: str) -> Path:
    path = tmp / where / "claude"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(FAKE)
    path.chmod(0o755)
    return path


def launch(tmp: Path, tree: Path, slug: str, env: dict[str, str],
           ) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
    base = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    base.update(PATH="/usr/bin:/bin", LOG_DIR=str(tmp),
                CLAUDECODE="1", CLAUDE_CODE_SESSION_ID="caller-session")
    proc = subprocess.run([sys.executable, str(SCRIPT), str(tree), slug],
                          env={**base, **env}, capture_output=True, text=True,
                          check=False)
    seen = {name: (tmp / name).read_text() for name in ("argv", "cwd", "leak")
            if (tmp / name).exists()}
    return proc, seen


def tree_in(tmp: Path, name: str = "iap tree") -> Path:
    tree = tmp / name
    tree.mkdir()
    return tree.resolve()


def case_starts_a_background_session_in_the_tree(tmp: Path) -> None:
    tree = tree_in(tmp)
    exe = fake_claude(tmp, "versions")
    proc, seen = launch(tmp, tree, SLUG, {"CLAUDE_CODE_EXECPATH": str(exe)})
    check("a background session starts in the tree (path with a space) running "
          "the resume prompt as one argument, and its attach command is printed",
          proc.returncode == 0
          and seen.get("argv", "").splitlines() == ["--bg", f"--name={SLUG}", PROMPT]
          and seen.get("cwd", "").strip() == str(tree)
          and f"LAUNCHED 1a2b3c4d {tree}" in proc.stdout
          and "claude attach 1a2b3c4d" in proc.stdout,
          f"rc={proc.returncode} seen={seen} out={proc.stdout!r} "
          f"err={proc.stderr!r}")


def case_caller_identity_does_not_leak(tmp: Path) -> None:
    tree = tree_in(tmp)
    exe = fake_claude(tmp, "versions")
    proc, seen = launch(tmp, tree, SLUG, {"CLAUDE_CODE_EXECPATH": str(exe)})
    check("the new session does not inherit the caller's session id or "
          "CLAUDECODE marker",
          proc.returncode == 0 and seen.get("leak") == "",
          f"rc={proc.returncode} leak={seen.get('leak')!r}")


def case_falls_back_to_claude_on_path(tmp: Path) -> None:
    tree = tree_in(tmp)
    bin_dir = fake_claude(tmp, "bin").parent
    proc, seen = launch(tmp, tree, SLUG,
                        {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin"})
    check("without CLAUDE_CODE_EXECPATH the `claude` on PATH is used",
          proc.returncode == 0 and "argv" in seen,
          f"rc={proc.returncode} seen={seen} err={proc.stderr!r}")


def case_refused_launch_falls_back_to_manual(tmp: Path) -> None:
    tree = tree_in(tmp)
    exe = fake_claude(tmp, "versions")
    proc, _ = launch(tmp, tree, SLUG, {"CLAUDE_CODE_EXECPATH": str(exe),
                                       "FAKE_ERR": "Workspace not trusted."})
    check("a refused launch (an untrusted tree) relays Claude's error and "
          "prints the manual command with exit 1",
          proc.returncode == 1 and "Workspace not trusted." in proc.stderr
          and f"MANUAL: cd '{tree}' && claude '{PROMPT}'" in proc.stdout,
          f"rc={proc.returncode} out={proc.stdout!r} err={proc.stderr!r}")


def case_no_claude_binary(tmp: Path) -> None:
    tree = tree_in(tmp)
    proc, seen = launch(tmp, tree, SLUG, {"CLAUDE_CODE_EXECPATH": str(tmp / "gone")})
    check("with no claude binary to run, the manual command is printed with "
          "exit 1",
          proc.returncode == 1 and "MANUAL: " in proc.stdout and not seen,
          f"rc={proc.returncode} out={proc.stdout!r}")


def case_leading_hyphen_slug_stays_a_name(tmp: Path) -> None:
    tree = tree_in(tmp)
    exe = fake_claude(tmp, "versions")
    proc, seen = launch(tmp, tree, "-cleanup", {"CLAUDE_CODE_EXECPATH": str(exe)})
    check("a slug with a leading hyphen, which cycle step 1 allows, launches as "
          "one --name= argument, not a flag",
          proc.returncode == 0
          and seen.get("argv", "").splitlines()[1:2] == ["--name=-cleanup"],
          f"rc={proc.returncode} seen={seen} err={proc.stderr!r}")


def case_bad_input_refused(tmp: Path) -> None:
    tree = tree_in(tmp)
    exe = str(fake_claude(tmp, "versions"))
    bad_slug, seen1 = launch(tmp, tree, "x'; rm -rf ~; '",
                             {"CLAUDE_CODE_EXECPATH": exe})
    missing, seen2 = launch(tmp, tmp / "nope", SLUG, {"CLAUDE_CODE_EXECPATH": exe})
    check("a slug outside [a-z0-9-] or a tree that is not a directory exits 2 "
          "and launches nothing",
          bad_slug.returncode == 2 and missing.returncode == 2
          and not seen1 and not seen2
          and "refused" in bad_slug.stderr and "refused" in missing.stderr,
          f"{bad_slug.returncode} {missing.returncode} {seen1} {seen2}")


CASES = [
    case_starts_a_background_session_in_the_tree,
    case_caller_identity_does_not_leak,
    case_falls_back_to_claude_on_path,
    case_refused_launch_falls_back_to_manual,
    case_no_claude_binary,
    case_leading_hyphen_slug_stays_a_name,
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
