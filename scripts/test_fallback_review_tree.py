#!/usr/bin/env python3
"""Exercise fallback probes against an independent clone, preserving the source."""
from __future__ import annotations

import subprocess
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
        (repo / "value").write_text("old")
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "old")
        old = git(repo, "rev-parse", "HEAD")
        (repo / "value").write_text("new")
        git(repo, "commit", "-qam", "new")
        prompt = root / "PROMPT.md"
        prompt.write_text(f"- Repo / worktree: `{repo}`\n"
                          f"- Head commit: `{old}`\n"
                          f"git -C {repo} diff BASE..HEAD\n")
        tree = root / "opus-tree-r1"
        rewritten = prepare(prompt, tree)
        assert (tree / "value").read_text() == "old"
        assert str(repo) not in rewritten.read_text()
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
