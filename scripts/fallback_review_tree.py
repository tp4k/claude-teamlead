#!/usr/bin/env python3
"""Prepare an independent disposable clone for an Opus gate, or remove it."""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from run_codex_review import Fail, prompt_for_review_tree, repo_from_prompt


def prepare(prompt: Path, dest: Path) -> Path:
    text = prompt.read_text()
    repo = repo_from_prompt(text).resolve()
    dest = dest.resolve()
    if dest == repo or repo in dest.parents:
        raise Fail("fallback tree must be outside the shared checkout")
    if dest.exists():
        raise Fail(f"fallback destination already exists: {dest}")
    # Copy object storage too: probes cannot change shared git state.
    subprocess.run(["git", "clone", "--no-local", "--no-checkout", str(repo),
                    str(dest)], check=True, capture_output=True)
    head = next(line.split('`')[1] for line in text.splitlines()
                if line.startswith("- Head commit: `"))
    subprocess.run(["git", "-C", str(dest), "checkout", "--detach", head],
                   check=True, capture_output=True)
    output = dest / "TEAMLEAD-REVIEW-PROMPT.md"
    output.write_text(prompt_for_review_tree(text, dest))
    return output


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("prompt", type=Path)
    ap.add_argument("dest", type=Path)
    ap.add_argument("--cleanup", action="store_true")
    args = ap.parse_args()
    if args.cleanup:
        dest = args.dest.resolve()
        if (dest.parent != args.prompt.resolve().parent
                or not dest.name.startswith("opus-tree-r")):
            raise Fail("cleanup requires a package sibling named opus-tree-r<N>")
        if dest.exists():
            shutil.rmtree(dest)
    else:
        print(prepare(args.prompt.resolve(), args.dest))


if __name__ == "__main__":
    main()
