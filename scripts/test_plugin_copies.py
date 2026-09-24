#!/usr/bin/env python3
"""Regression suite for plugin_copies.py:  python3 scripts/test_plugin_copies.py

The failure this pins: a linked worktree of this plugin, left in
`~/.claude/skills/`, registered as a second plugin named `teamlead`, and every
session for a week loaded `delegate` and `cycle` from it — a branch cut before
the options card and the plan design review existed. Thirteen runs in a row had
no `config.json` and no plan review, and each looked like a coordinator skipping
steps, because the coordinator was faithfully following a skill that had none.

So the cases are directory layouts: a lone copy is fine, a second copy with the
same plugin name is refused, a *differently*-named plugin beside it is not, and
kickoff (`new_run.py`) creates nothing while the ambiguity stands.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import plugin_copies  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def mkplugin(where: Path, name: str = "teamlead") -> Path:
    (where / ".claude-plugin").mkdir(parents=True)
    (where / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": name, "version": "0.1.0"}))
    return where


def case_lone_copy(tmp: Path) -> None:
    skills = tmp / "skills"
    root = mkplugin(skills / "teamlead")
    got = plugin_copies.other_copies(root, [skills])
    check("the only copy in the skills dir → no other copies", got == [],
          f"got={got}")


def case_worktree_beside_it(tmp: Path) -> None:
    skills = tmp / "skills"
    root = mkplugin(skills / "teamlead")
    stale = mkplugin(skills / "teamlead-snapshot-granularity")
    got = plugin_copies.other_copies(root, [skills])
    check("a sibling worktree with the same plugin name is reported",
          got == [stale.resolve()], f"got={got}")


def case_other_plugin_ignored(tmp: Path) -> None:
    skills = tmp / "skills"
    root = mkplugin(skills / "teamlead")
    mkplugin(skills / "other", name="something-else")
    (skills / "plain-skill").mkdir()
    (skills / "plain-skill" / "SKILL.md").write_text("---\nname: x\n---\n")
    got = plugin_copies.other_copies(root, [skills])
    check("another plugin, or a plain skill, is not a copy", got == [],
          f"got={got}")


def case_loaded_from_elsewhere(tmp: Path) -> None:
    """A marketplace install plus a skills-dir checkout is the same ambiguity."""
    skills = tmp / "skills"
    root = mkplugin(tmp / "cache" / "teamlead" / "0.1.0")
    stale = mkplugin(skills / "teamlead")
    got = plugin_copies.other_copies(root, [skills])
    check("a copy in the skills dir shadows one loaded from elsewhere",
          got == [stale.resolve()], f"got={got}")


def case_unreadable_manifest(tmp: Path) -> None:
    """A broken manifest beside us names no plugin, so it is no copy — never a crash."""
    skills = tmp / "skills"
    root = mkplugin(skills / "teamlead")
    bad = skills / "broken" / ".claude-plugin"
    bad.mkdir(parents=True)
    (bad / "plugin.json").write_text("{not json")
    got = plugin_copies.other_copies(root, [skills])
    check("an unreadable plugin.json is skipped, not raised", got == [],
          f"got={got}")


def case_missing_search_dir(tmp: Path) -> None:
    root = mkplugin(tmp / "teamlead")
    got = plugin_copies.other_copies(root, [tmp / "does-not-exist"])
    check("a search dir that does not exist is simply empty", got == [],
          f"got={got}")


def case_refusal_names_the_fix(tmp: Path) -> None:
    skills = tmp / "skills"
    root = mkplugin(skills / "teamlead")
    stale = mkplugin(skills / "teamlead-old")
    msg = plugin_copies.refusal(root, [stale])
    ok = (str(stale) in msg and str(root) in msg and "--plugin-dir" in msg
          and "git worktree move" in msg)
    check("the refusal names both trees and both ways out", ok, msg)


def case_new_run_refuses(tmp: Path) -> None:
    """Kickoff is where every run passes, so it is where the ambiguity must stop."""
    skills = tmp / "skills"
    mkplugin(skills / "teamlead-a")
    mkplugin(skills / "teamlead-b")
    home = tmp / "home"
    repo = tmp / "repo"
    repo.mkdir()
    # The suite's own checkout is the loaded copy; point the search at a dir
    # holding another plugin by the same name as ours.
    ours = json.loads((HERE.parent / ".claude-plugin" / "plugin.json").read_text())
    mkplugin(skills / "shadow", name=ours["name"])
    env = dict(os.environ, TEAMLEAD_HOME=str(home),
               TEAMLEAD_PLUGIN_SEARCH_DIRS=str(skills))
    r = subprocess.run([sys.executable, str(HERE / "new_run.py"), str(repo), "x"],
                       capture_output=True, text=True, env=env, check=False)
    runs = home / "runs"
    made = list(runs.rglob("repo.txt")) if runs.exists() else []
    ok = (r.returncode == 3 and "RUN_DIR=" not in r.stdout and not made
          and "shadow" in r.stdout)
    check("new_run.py exits 3 and creates no run while a copy shadows it", ok,
          f"exit={r.returncode} made={made}\n      out={r.stdout.strip()!r}"
          f"\n      err={r.stderr.strip()[:300]!r}")


def case_new_run_proceeds_alone(tmp: Path) -> None:
    home = tmp / "home"
    repo = tmp / "repo"
    repo.mkdir()
    env = dict(os.environ, TEAMLEAD_HOME=str(home),
               TEAMLEAD_PLUGIN_SEARCH_DIRS=str(tmp / "empty"))
    r = subprocess.run([sys.executable, str(HERE / "new_run.py"), str(repo), "x"],
                       capture_output=True, text=True, env=env, check=False)
    check("new_run.py still creates the run when no copy shadows it",
          r.returncode == 0 and "RUN_DIR=" in r.stdout,
          f"exit={r.returncode} out={r.stdout.strip()!r} "
          f"err={r.stderr.strip()[:300]!r}")


def main() -> int:
    cases = [v for k, v in globals().items() if k.startswith("case_")]
    for case in cases:
        with tempfile.TemporaryDirectory() as d:
            case(Path(d))
    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            print(f"      {detail}")
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
