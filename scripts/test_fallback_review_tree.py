#!/usr/bin/env python3
"""Exercise fallback probes against an independent clone, preserving the source."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from fallback_review_tree import Fail, prepare


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        repo = root / "source"
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "config", "user.name", "t")
        git(repo, "config", "user.email", "t@t")
        (repo / "value").write_text("base")
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "base")
        base = git(repo, "rev-parse", "HEAD")
        (repo / "value").write_text("old")
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "old")
        old = git(repo, "rev-parse", "HEAD")
        (repo / "value").write_text("new")
        git(repo, "commit", "-qam", "new")
        package = root / "source-review"
        package.mkdir()
        plan = root / "plan.md"
        plan.write_text("requirements")
        subprocess.run(
            [sys.executable, str(Path(__file__).with_name("review_package.py")),
             str(repo), "--base", base, "--head", old, "--plan", str(plan),
             "--out", str(package), "--quiet"], check=True, capture_output=True,
            env={**os.environ, "TEAMLEAD_HOME": str(root / "home")})
        prompt = package / "PROMPT.md"
        tree = root / "opus-tree-r1"
        rewritten = prepare(prompt, tree)
        assert (tree / "value").read_text() == "old"
        assert f"Repo / worktree: `{tree}`" in rewritten.read_text()
        assert f"`{package / 'plan.md'}`" in rewritten.read_text()
        guidance = re.search(r"^Paths are relative to `([^`]+)` — e\.g\. `([^`]+)`\.$",
                             rewritten.read_text(), re.MULTILINE)
        assert guidance is not None
        assert Path(guidance.group(1)) == tree
        # Following the emitted file guidance must inspect the pinned snapshot,
        # whose content deliberately differs from the shared checkout.
        assert Path(guidance.group(2)).read_text() == "old"
        assert f"git -C {tree} diff" in rewritten.read_text()
        assert (tree / ".git").is_dir()
        assert not (tree / ".git/objects/info/alternates").exists()
        # An independent executable probe and git config edits stay in the clone.
        (tree / "value").write_text("probe")
        git(tree, "config", "review.probe", "yes")
        assert (repo / "value").read_text() == "new"
        assert git(repo, "status", "--porcelain") == ""
        assert "review.probe" not in git(repo, "config", "--list")
        try:
            prepare(prompt, repo / "nested")
        except Fail:
            pass
        else:
            raise AssertionError("allowed fallback inside shared tree")
    print("PASS fallback isolation, historical head, probe writes, shared state")


if __name__ == "__main__":
    main()
