#!/usr/bin/env python3
"""Every skills/*/SKILL.md follows the agentskills.io frontmatter rules.

Run it with:  python3 scripts/test_skill_spec.py

The rules are the reference validator's (`skills-ref validate`, agentskills/
agentskills `skills-ref/src/skills_ref/validator.py`), restated here because the
suite runs on bare python3 with no install. Claude Code-only keys such as
`argument-hint` live under `metadata`, which is the spec's place for them; a
new top-level key fails here before it fails someone else's validator.

The frontmatter is parsed by hand — `key: value` lines plus one level of
indented `metadata` — because PyYAML is not in the standard library.
"""
from __future__ import annotations

import sys
from pathlib import Path

SKILLS = Path(__file__).resolve().parent.parent / "skills"
ALLOWED = {"name", "description", "license", "allowed-tools", "metadata",
           "compatibility"}

results: list[tuple[str, bool, str]] = []


def frontmatter(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """Top-level keys, and the `metadata` sub-keys."""
    lines = text.split("\n")
    end = lines.index("---", 1)
    top: dict[str, str] = {}
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        key, _, value = line.strip().partition(":")
        target = meta if line.startswith("  ") else top
        target[key] = value.strip().strip("'\"")
    return top, meta


def check_skill(skill_md: Path) -> None:
    top, meta = frontmatter(skill_md.read_text())
    name, desc = top.get("name", ""), top.get("description", "")
    who = skill_md.parent.name
    extra = sorted(set(top) - ALLOWED)
    results.append((f"{who}: only spec fields at top level", not extra,
                    f"extra={extra}"))
    results.append((
        f"{who}: name is lowercase, hyphenated and matches its directory",
        0 < len(name) <= 64 and name == name.lower() == who
        and "--" not in name and not name.startswith("-")
        and not name.endswith("-") and all(c.isalnum() or c == "-" for c in name),
        f"name={name!r}",
    ))
    results.append((f"{who}: description is 1-1024 chars", 0 < len(desc) <= 1024,
                    f"len={len(desc)}"))
    results.append((f"{who}: metadata values are strings",
                    all(isinstance(v, str) and v for v in meta.values()),
                    f"metadata={sorted(meta)}"))
    body = skill_md.read_text().split("\n")
    results.append((f"{who}: SKILL.md stays under 500 lines", len(body) < 500,
                    f"lines={len(body)}"))


def main() -> int:
    skills = sorted(SKILLS.glob("*/SKILL.md"))
    results.append(("skills were found", bool(skills), str(SKILLS)))
    for skill_md in skills:
        check_skill(skill_md)
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            print(f"      {detail}")
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"\n=== {len(results) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
