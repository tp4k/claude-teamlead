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

import paths
import run_config

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
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


def flat(text: str) -> str:
    return " ".join(text.split())


def table_rows(text: str) -> list[dict[str, str]]:
    """The first Markdown table in `text` as header-keyed rows of raw cells."""
    rows: list[dict[str, str]] = []
    header: list[str] = []
    for line in text.splitlines():
        if not line.startswith("|"):
            if rows:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not header:
            header = cells
        elif not set(line) <= set("|-: "):
            rows.append(dict(zip(header, cells)))
    return rows


def check_delegate_names_next_py_and_gate() -> None:
    """The loop routes through next.py and ends in the in-loop Codex gate.

    Reads the loop block only: the same words in a reference table further down
    would mask a loop that stopped saying them.
    """
    delegate = SKILLS / "delegate" / "SKILL.md"
    loop = flat(section(delegate, "## The coordination loop",
                        "## Pointer briefs"))
    for needle in ("scripts/next.py $RUN", "mutation gate", "baseline",
                   "triage-gate-r", "teamlead:code-reviewer", "reworkCap",
                   "NEEDS_DECISION", "docs-fix:", "coordinator-fix:",
                   "decisions-log.md", "ledger.py apply"):
        results.append((f"delegate loop names {needle!r}", needle in loop,
                        needle))
    order = ("4a. ", "6. Relay", "scripts/next.py $RUN", "baseline", "8a. ",
             "9. Reviewers", "10. TRIAGE", "10a. CODEX GATE", "ledger.py apply")
    at, cursor, in_order = [], 0, True
    for needle in order:
        found = loop.find(needle, cursor)
        in_order = in_order and found >= 0
        at.append(found)
        cursor = found + 1 if found >= 0 else cursor
    results.append(("delegate loop runs 4a, relay, next.py, baseline, 8a, 9, 10, "
                    "10a, ledger in that order", in_order, str(at)))
    results.append(("delegate loop states verify, review, triage, gate, close order",
                    "Then verify (8a), review (9), triage (10), the Codex gate "
                    "(10a), and close (11)." in loop, "order sentence"))


def check_delegate_asks_one_batch() -> None:
    """Every plan question, the scope card included, goes out in the step-6 relay."""
    delegate = SKILLS / "delegate" / "SKILL.md"
    validator = flat(section(delegate, "4a. ", "5.  PLAN TRIAGE"))
    relay = flat(section(delegate, "6.  Relay", "6a."))
    hold = flat(section(delegate, "6d. HOLD GATE", "7.  "))
    results.append(("delegate 4a dispatches the validator beside the design review",
                    "teamlead:plan-validator" in validator, "4a"))
    results.append(("delegate step 6 asks the scope card in the one batch",
                    "Smaller:" in relay and "Scope card" in relay, "6"))
    results.append(("delegate step 6d no longer asks the scope card after the relay",
                    "Scope card" not in hold and "A/B/C" not in hold, "6d"))


def check_followups_only_for_out_of_scope_rows() -> None:
    """The in-loop gate replaces the post-run Codex review; only picked rows follow."""
    delegate = SKILLS / "delegate" / "SKILL.md"
    step11 = flat(section(delegate, "11. Any demoted row", "```"))
    cycle = flat(section(SKILLS / "cycle" / "SKILL.md", "## 10. Review", "## 11."))
    review = flat(section(SKILLS / "codex-review" / "SKILL.md", "# Review a teamlead",
                          "## 1."))
    results.append(("delegate step 11 offers a follow-up for out-of-scope rows only",
                    "out-of-scope" in step11 and "every demoted" not in step11,
                    "step 11"))
    results.append(("delegate step 11 prints no codex-review one-liner for the gate",
                    "without running it" not in step11, "step 11"))
    results.append(("cycle step 10 runs no separate Codex review after the gate",
                    "in-loop" in cycle and "codexCodeReview=off" in cycle
                    and "After a clean finish" not in cycle
                    and "Do not start a separate `/teamlead:codex-review` after it"
                    in cycle, "cycle step 10"))
    results.append(("codex-review says the loop already gates the diff in-loop",
                    "in-loop" in review, "codex-review intro"))


def check_readme_defaults_match_paths() -> None:
    """README states the defaults paths.DEFAULTS holds, and no stale opt-in prose."""
    readme = ROOT / "README.md"
    options = section(readme, "## Run options", "## What gets installed")
    config = section(readme, "## Configuration", "## Troubleshooting")
    rows = {r["Option"].strip("`"): r for r in table_rows(options)}
    results.append(("README run options table lists every option",
                    set(rows) == set(run_config.OPTION_KEYS), str(sorted(rows))))
    for key, row in rows.items():
        stated = row.get("Default", "").strip("`")
        results.append((f"README default of {key} is {paths.DEFAULTS.get(key)!r}",
                        stated == str(paths.DEFAULTS.get(key)),
                        f"README says {stated!r}"))
    for row in table_rows(config):
        key = row.get("Key", "").strip("`")
        want = paths.DEFAULTS.get(key)
        if isinstance(want, (int, str)):
            stated = row.get("Default", "").strip("`")
            results.append((f"README Configuration default of {key}",
                            stated == str(want).lower(), f"README says {stated!r}"))
    axes = next((r for r in table_rows(config)
                 if r.get("Key") == "`codexPlanReviewAxes`"), {})
    results.append(("README Configuration lists every plan-review axis",
                    all(a in axes.get("Meaning", "") for a in paths.PLAN_REVIEW_AXES),
                    str(paths.PLAN_REVIEW_AXES)))
    results.append(("README Configuration no longer says every option defaults off",
                    "default to `off`" not in config and "default to off" not in config,
                    "All run options default to off"))
    results.append(("README does not describe the Codex final gate as opt-in",
                    "opt-in" not in flat(options).lower()
                    and "`off` skips the gate" in flat(options), "opt-in"))


def check_readme_fences() -> None:
    """README fences alternate open/close: a stray bare fence turns prose to code."""
    lines = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()
    heading = "### `/teamlead:cycle` \u2014 the same run, plus the tree it runs in"
    inside, closed_at, stray, heading_inside = False, -1, [], None
    for number, line in enumerate(lines, 1):
        if line == heading:
            heading_inside = inside
        if not line.startswith("```"):
            continue
        if not inside and number == closed_at + 1 and line == "```":
            stray.append(number)
        if inside:
            closed_at = number
        inside = not inside
    results.append(("README has no bare fence right after a closing fence",
                    not stray, f"stray fence at lines {stray}"))
    results.append(("README cycle heading sits outside a code fence",
                    heading_inside is False, f"inside fence: {heading_inside}"))
    results.append(("README closes every code fence", not inside, "unclosed fence"))


def check_delegate_run_options_match_paths() -> None:
    """Defaults the delegate Run options prose states equal paths.DEFAULTS."""
    options = flat(section(SKILLS / "delegate" / "SKILL.md", "## Run options",
                           "## The coordination loop"))
    pairs = re.findall(r"`(\w+)=([\w-]+)`", options)
    checked = [(k, v) for k, v in pairs if k in run_config.OPTION_KEYS]
    results.append(("delegate Run options states at least one default",
                    bool(options) and bool(checked), str(pairs)))
    for key, value in checked:
        results.append((f"delegate Run options default of {key} is "
                        f"{paths.DEFAULTS[key]!r}",
                        value == str(paths.DEFAULTS[key]), f"says {value!r}"))


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
    check_delegate_names_next_py_and_gate()
    check_delegate_asks_one_batch()
    check_followups_only_for_out_of_scope_rows()
    check_readme_defaults_match_paths()
    check_readme_fences()
    check_delegate_run_options_match_paths()
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
