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


# PyYAML 6.0.2's implicit resolvers (`yaml.resolver.Resolver`), copied verbatim
# in re.X form: a plain scalar matching any of these loads as that type, not as
# a string. Copied rather than approximated because the approximation missed
# timestamps (PR #5 review); `scripts/` runs on bare python3, so no import.
YAML_IMPLICIT = {
    "bool": r"""^(?:yes|Yes|YES|no|No|NO
                    |true|True|TRUE|false|False|FALSE
                    |on|On|ON|off|Off|OFF)$""",
    "null": r"""^(?: ~
                    |null|Null|NULL
                    | )$""",
    "float": r"""^(?:[-+]?(?:[0-9][0-9_]*)\.[0-9_]*(?:[eE][-+][0-9]+)?
                    |\.[0-9][0-9_]*(?:[eE][-+][0-9]+)?
                    |[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*
                    |[-+]?\.(?:inf|Inf|INF)
                    |\.(?:nan|NaN|NAN))$""",
    "int": r"""^(?:[-+]?0b[0-1_]+
                    |[-+]?0[0-7_]+
                    |[-+]?(?:0|[1-9][0-9_]*)
                    |[-+]?0x[0-9a-fA-F_]+
                    |[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+)$""",
    "timestamp": r"""^(?:[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]
                    |[0-9][0-9][0-9][0-9] -[0-9][0-9]? -[0-9][0-9]?
                     (?:[Tt]|[ \t]+)[0-9][0-9]?
                     :[0-9][0-9] :[0-9][0-9] (?:\.[0-9]*)?
                     (?:[ \t]*(?:Z|[-+][0-9][0-9]?(?::[0-9][0-9])?))?)$""",
    "merge": r"^(?:<<)$",
    "value": r"^(?:=)$",
    "yaml": r"^(?:!|&|\*)$",
}
NON_STRING = [re.compile(p, re.X) for p in YAML_IMPLICIT.values()]


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
    validators, speak) resolves it by `NON_STRING` — null, bool, int, float,
    timestamp and the rest — and a leading indicator makes it a collection,
    alias, tag or block scalar instead. A `: ` inside, a trailing `:`, or a
    leading `- `/`? ` is not a value at all: the frontmatter stops parsing.
    """
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        return len(raw) > 2
    return (
        bool(raw)
        and not any(rx.match(raw) for rx in NON_STRING)
        and raw[0] not in "[{&*!|>%@`"
        and ": " not in raw
        and not raw.endswith(":")
        and not raw.startswith(("- ", "? "))
    )


# Anthropic's skill-authoring guide: the description is injected into the system
# prompt, so it reads as third person ("Coordinates …"), not an order to the
# model ("Act as …") or a voice ("You can …", "I help …"). Only the opener is
# checked; trigger phrases quoted later ("act as teamlead") are the user's words.
# The opener must be a third-person verb: one ending in "s", but not "ss", which
# is an imperative ("Process …", "Address …"). A noun phrase ("One cycle …")
# fails too, so a description always says what the skill does.


def is_third_person(desc: str) -> bool:
    words = desc.split(maxsplit=1)
    if not words:
        return False
    opener = words[0].lower()
    return opener.endswith("s") and not opener.endswith("ss")


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
    results.append((f"{who}: description is in third person",
                    is_third_person(desc), f"opens with {desc[:30]!r}"))
    bad =sorted(k for k, v in meta.items() if not is_yaml_string(v))
    results.append((f"{who}: metadata values are strings", not bad,
                    f"non-string metadata={bad}"))
    body = skill_md.read_text().split("\n")
    results.append((f"{who}: SKILL.md stays under 500 lines", len(body) < 500,
                    f"lines={len(body)}"))


def check_the_string_check() -> None:
    """`is_yaml_string` must be able to fail, or the metadata row proves nothing."""
    for raw in ('"a b"', "'1'", "<issue> [--flag]", "plain words", '"2020-01-01"',
                "YeS", "0o17", "v1.2.3", "2020-01"):
        results.append((f"string check accepts {raw!r}", is_yaml_string(raw), raw))
    for raw in ("", '""', "1", "3.5", "true", "Yes", "null", "~", "[a]", "{a: 1}",
                "2020-01-01", "2001-12-14t21:59:43.10-05:00", "1:30", "0b101",
                "1_000", ".inf", "<<", "="):
        results.append((f"string check rejects {raw!r}", not is_yaml_string(raw),
                        raw))


def check_the_person_check() -> None:
    """`is_third_person` must be able to fail, or the description row proves nothing."""
    for desc in ("Coordinates a task", "Has Codex review", "Runs one cycle",
                 " runs one cycle"):
        results.append((f"person check accepts {desc!r}", is_third_person(desc),
                        desc))
    for desc in ("Act as a coordinator", "Have Codex review", "You can review",
                 "I help with", "Run a review", "act as a coordinator",
                 " Act as a coordinator", "Process the run", "One delivery cycle",
                 ""):
        results.append((f"person check rejects {desc!r}",
                        not is_third_person(desc), desc))


FOLLOWUP_MARKER = "<!-- teamlead:review-followup -->"


def check_followup_contract() -> None:
    """codex-review writes the follow-up header that delegate step 11 routes on.

    The two halves live in different skills and nothing else ties them
    together: rename the marker or a `Reviewer:` value on one side and the fix
    run silently ends with a one-liner instead of its re-review.

    Each check reads only the step that owns the token: the same key written in
    step 3 and read in step 11 would otherwise mask a rename on either side.
    """
    writer = section(SKILLS / "codex-review" / "SKILL.md",
                     "## 4. Route the accepted rows back", None)
    delegate = SKILLS / "delegate" / "SKILL.md"
    kickoff = section(delegate, "3.  KICKOFF:", "3a. RUN OPTIONS")
    step11 = section(delegate, "11. Any demoted row", "```")
    results.append(("codex-review step 4 writes the follow-up marker",
                    FOLLOWUP_MARKER in writer, FOLLOWUP_MARKER))
    results.append(("codex-review's header lists both reviewer values",
                    "Reviewer: Codex | Opus fallback" in writer,
                    "Reviewer: Codex | Opus fallback"))
    results.append(("codex-review's header records the head the packager starts at",
                    "Reviewed head: <" in writer, "Reviewed head: <"))
    results.append(("codex-review triages the follow-up's `## Earlier findings`",
                    "`## Earlier findings`" in section(
                        SKILLS / "codex-review" / "SKILL.md",
                        "## 3. Triage the Codex findings", "## 4."),
                    "`## Earlier findings`"))
    for needle in (FOLLOWUP_MARKER, "followup-of:", "followup-reviewer:"):
        results.append((f"delegate step 3 records {needle!r}",
                        needle in kickoff, needle))
    for needle in ("task.md has `followup-of:`", "`followup-reviewer:` is "
                   "`Opus fallback`", "--opus-code-review=fallback",
                   "invoke `/teamlead:codex-review <abs $RUN>` yourself (Skill "
                   "tool)"):
        results.append((f"delegate step 11 routes the re-review on {needle!r}",
                        needle in " ".join(step11.split()), needle))


def section(path: Path, start: str, end: str | None) -> str:
    """The text of `path` from `start` up to the next `end` (or EOF); '' if absent."""
    text = path.read_text(encoding="utf-8")
    begin = text.find(start)
    if begin < 0:
        return ""
    stop = text.find(end, begin + len(start)) if end else -1
    return text[begin:stop if stop >= 0 else len(text)]


def main() -> int:
    check_the_string_check()
    check_the_person_check()
    check_followup_contract()
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
