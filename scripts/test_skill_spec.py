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

import re
import sys
from pathlib import Path

SKILLS = Path(__file__).resolve().parent.parent / "skills"
ALLOWED = {"name", "description", "license", "allowed-tools", "metadata",
           "compatibility"}

results: list[tuple[str, bool, str]] = []


NON_STRING_WORDS = {"true", "false", "yes", "no", "on", "off", "null", "~"}
NUMBER = re.compile(r"[-+]?(\d[\d_]*(\.\d*)?|\.\d+)([eE][-+]?\d+)?|0x[0-9a-fA-F]+"
                    r"|[-+]?\.(inf|Inf|INF)|\.(nan|NaN|NAN)")


def frontmatter(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """Top-level keys, and the `metadata` sub-keys, as the raw YAML text.

    Raw, not unquoted: whether a value is a string is decided by how it is
    written (`"1"` is a string, `1` is not), so quotes must survive to
    `is_yaml_string`.
    """
    lines = text.split("\n")
    end = lines.index("---", 1)
    top: dict[str, str] = {}
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        key, _, value = line.strip().partition(":")
        target = meta if line.startswith("  ") else top
        target[key] = value.strip()
    return top, meta


def unquoted(raw: str) -> str:
    return raw[1:-1] if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"" else raw


def is_yaml_string(raw: str) -> bool:
    """Would YAML load this plain scalar as a non-empty string?

    Quoted is always a string. Unquoted, YAML 1.1 (what PyYAML, and so most
    validators, speak) turns empty into null, `true`/`yes`/`on` and friends into
    booleans, digits into numbers, and `[`/`{` into collections.
    """
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        return len(raw) > 2
    return (
        bool(raw)
        and raw.lower() not in NON_STRING_WORDS
        and not NUMBER.fullmatch(raw)
        and raw[0] not in "[{&*!|>"
    )


def check_skill(skill_md: Path) -> None:
    top, meta = frontmatter(skill_md.read_text())
    name = unquoted(top.get("name", ""))
    desc = unquoted(top.get("description", ""))
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
    bad = sorted(k for k, v in meta.items() if not is_yaml_string(v))
    results.append((f"{who}: metadata values are strings", not bad,
                    f"non-string metadata={bad}"))
    body = skill_md.read_text().split("\n")
    results.append((f"{who}: SKILL.md stays under 500 lines", len(body) < 500,
                    f"lines={len(body)}"))


def check_the_string_check() -> None:
    """`is_yaml_string` must be able to fail, or the metadata row proves nothing."""
    for raw in ('"a b"', "'1'", "<issue> [--flag]", "plain words"):
        results.append((f"string check accepts {raw!r}", is_yaml_string(raw), raw))
    for raw in ("", '""', "1", "3.5", "true", "Yes", "null", "~", "[a]", "{a: 1}"):
        results.append((f"string check rejects {raw!r}", not is_yaml_string(raw),
                        raw))


def main() -> int:
    check_the_string_check()
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
