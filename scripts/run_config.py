"""Resolve one run's options from flags, config tiers and the user's card answers.

Three things decide how a `/teamlead:delegate` run behaves: what the user typed,
what their config says, and what they picked on the options cards. Before this
script the first lived only in the coordinator's reading of the task text and
the third lived only in the transcript, which meant a resumed or compacted run
could not tell you what it had been asked to do. Here the three are resolved by
one rule, printed as one table, and persisted to `$RUN/config.json` — so the
answer survives the session that produced it.

Precedence, highest first:

    card answer  ->  flag  ->  <repo>/.teamlead.json
      ->  $TEAMLEAD_HOME/config.json  ->  default

The card wins over the flag on purpose: the card is shown *after* the flag was
typed, so it is the user's later word on the same question.

A bad value is handled differently depending on where it came from, and the
asymmetry is deliberate. A config typo is skipped and the next tier answers
(`paths.setting`), because a config is edited once and read for months and a
stopping rule there breaks runs that have nothing to do with the typo. A flag
typo is fatal, because it was typed seconds ago by someone watching the output,
and silently ignoring it would run the whole loop in a mode they did not ask for.
"""
from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

import paths

OPTION_KEYS: tuple[str, ...] = (
    "codexPlanReview",
    "opusPlanReview",
    "humanReadablePlan",
    "securityReview",
    "perfReview",
    "codexCodeReview",
    "adr",
)

# The flag spelling of each option. `--no-security-review` and `--no-perf-review`
# are kept as aliases for `=off` rather than retired: they are what `cycle`
# forwards, what the old argument-hint advertised, and what a year of muscle
# memory types. An alias costs one line here; breaking them costs a silent
# behaviour change in runs that look like they asked for something.
VALUE_FLAGS: dict[str, str] = {
    "--codex-plan-review": "codexPlanReview",
    "--opus-plan-review": "opusPlanReview",
    "--with-human-readable-plan": "humanReadablePlan",
    "--security-review": "securityReview",
    "--perf-review": "perfReview",
    "--codex-code-review": "codexCodeReview",
    # `--adr` is listed here as well as in BARE_FLAGS, exactly as
    # `--codex-code-review` is. Both spellings are real: `off` and `on` are the
    # values the option admits, so `--adr=off` has to mean off rather than
    # falling through to whatever a config file says — a flag typed to turn
    # something off that instead leaves it on is the worst shape this parser
    # has. The bare form still means `on`, via BARE_FLAGS below.
    "--adr": "adr",
}
BARE_FLAGS: dict[str, tuple[str, str]] = {
    "--adr": ("adr", "on"),
    "--codex-code-review": ("codexCodeReview", "on"),
    "--no-security-review": ("securityReview", "off"),
    "--no-perf-review": ("perfReview", "off"),
}
MODE_FLAGS: tuple[str, ...] = ("--use-config-options", "--autopilot")

SEED_NOTE = (
    "Seeded by teamlead on its first run. Every option defaults to off in code "
    "(scripts/paths.py), so these two lines are what keep the security and "
    "performance reviews running the way they did before options existed. Edit "
    "or delete them freely; see the plugin's config.example.json for every key."
)


class Fail(Exception):
    pass


def takes_no_value(name: str) -> Fail:
    """The error for a bare flag written with an inline value.

    Rejecting is the only safe answer, and `--autopilot=false` is why. Reading
    the name and discarding the value turns a flag typed to KEEP the run's
    approval stops into the flag that skips every one of them — the user's
    intent inverted, silently, at the one gate that protects the rest. Parsing
    `=false` instead would invent a boolean syntax no flag here documents, and
    leave `--autopilot=no` and `--autopilot=0` as the next two versions of this
    bug. So the flag stops the run and names its real spelling, which is what a
    bad flag value does everywhere else in this parser.
    """
    return Fail(f"{name} takes no value: write it bare as {name}, or omit it.")


def parse_flags(raw: str) -> tuple[dict[str, str], set[str]]:
    """(option overrides, mode flags) from the run's flag text.

    Unrecognised tokens are ignored rather than rejected, because this is handed
    the same string the task text was stripped from and a stray word is not a
    mistake worth stopping a run over. A *recognised* flag carrying a value the
    option does not admit is the opposite case, and raises.
    """
    values: dict[str, str] = {}
    modes: set[str] = set()
    try:
        tokens = shlex.split(raw)
    except ValueError:
        # An apostrophe in the task text ("don't drop the cache") is an unbalanced
        # quote to shlex, and refusing to resolve a run's options over English
        # punctuation would be absurd. Whitespace splitting finds every flag this
        # function can act on; quoting only ever mattered for the prose around them.
        tokens = raw.split()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        name, _, inline = token.partition("=")

        if name in MODE_FLAGS:
            if inline:
                raise takes_no_value(name)
            modes.add(name)
            continue

        if name in VALUE_FLAGS:
            key = VALUE_FLAGS[name]
            if inline:
                value = inline
            elif index < len(tokens) and tokens[index] in paths.CHOICES[key]:
                # The space form (`--codex-plan-review always`) is accepted only
                # when the next token is actually one of this option's values.
                # Anything else is a bare flag followed by the task text, and
                # swallowing a word of the task would be worse than ignoring it.
                value = tokens[index]
                index += 1
            elif name in BARE_FLAGS:
                value = BARE_FLAGS[name][1]
            else:
                raise Fail(
                    f"{name} needs a value: one of {', '.join(paths.CHOICES[key])}"
                )
            if value not in paths.CHOICES[key]:
                raise Fail(
                    f"{name}={value} is not a value it takes: "
                    f"{', '.join(paths.CHOICES[key])}"
                )
            values[key] = value
            continue

        if name in BARE_FLAGS:
            # Only the `--no-*` aliases reach here now: every bare flag that is
            # also a real option is in VALUE_FLAGS and was handled above. An
            # alias for `=off` has no value of its own to carry, so an inline
            # one is the same mistake as on a mode flag and gets the same answer
            # rather than being dropped on the floor.
            if inline:
                raise takes_no_value(name)
            key, value = BARE_FLAGS[name]
            values[key] = value
    return values, modes


def parse_choices(raw: list[str]) -> dict[str, str]:
    """`key=value` pairs from the options cards, validated against the vocabulary."""
    chosen: dict[str, str] = {}
    for item in raw:
        key, _, value = item.partition("=")
        if key not in paths.CHOICES:
            raise Fail(f"--choice {item}: {key} is not a run option")
        if value not in paths.CHOICES[key]:
            raise Fail(
                f"--choice {item}: {key} takes {', '.join(paths.CHOICES[key])}"
            )
        chosen[key] = value
    return chosen


def seed_global_config() -> Path | None:
    """Write the global config if there is none, and say so. Otherwise leave it.

    Only ever called when the file is absent, and it never rewrites one that
    exists — a config the user has edited is theirs, and a script that "restores"
    a key they deliberately removed is worse than no seeding at all.
    """
    target = paths.config_path()
    if target.exists():
        return None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {"_comment": SEED_NOTE, "securityReview": "on", "perfReview": "on"},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError:
        # A home that cannot be written is a machine where every run works
        # anyway, just with everything off. Reporting that beats failing here.
        return None
    return target


def tier_of(key: str, repo: Path) -> str:
    """Which config file supplied `key`, or "default" — for the table's `from`."""
    validator = paths.one_of(key) if key in paths.CHOICES else None
    for label, src in (
        (f"{repo}/.teamlead.json", repo / ".teamlead.json"),
        (str(paths.config_path()), paths.config_path()),
    ):
        data = paths.read_json(src)
        if key in data and (validator is None or validator(data[key])):
            return label
    return "default"


def resolve(
    repo: Path, flags: dict[str, str], choices: dict[str, str]
) -> tuple[dict[str, str], dict[str, str]]:
    """(value per option, where each came from)."""
    values: dict[str, str] = {}
    sources: dict[str, str] = {}
    for key in OPTION_KEYS:
        if key in choices:
            values[key] = choices[key]
            sources[key] = "options card"
        elif key in flags:
            values[key] = flags[key]
            sources[key] = "flag"
        else:
            values[key] = str(paths.setting(key, repo, paths.one_of(key)))
            sources[key] = tier_of(key, repo)

    if not scope_fence(repo):
        # `when-needed` rests entirely on the planner's per-workstream `input:` /
        # `hot:` tags, and those are only binding on the code because a PreToolUse
        # hook refuses a write outside the brief's fenced scope. With the fence
        # off, an implementer may touch anything, so a tag that said "no
        # attacker-controlled input reaches this stream" describes a boundary
        # nothing enforces. Silently reviewing less on the strength of a promise
        # that has been switched off is the one failure this resolver can prevent
        # for free, so `when-needed` becomes `on` and the table says why.
        for key in ("securityReview", "perfReview"):
            if values[key] == "when-needed":
                values[key] = "on"
                sources[key] = f"{sources[key]} → on (scopeFence off)"
    return values, sources


def scope_fence(repo: Path) -> bool:
    """Whether the run's writes are held to the briefs' declared file scopes."""
    return bool(
        paths.setting("scopeFence", repo, lambda value: isinstance(value, bool))
    )


def render(
    values: dict[str, str],
    sources: dict[str, str],
    modes: set[str],
    seeded: Path | None,
) -> str:
    lines: list[str] = []
    if seeded is not None:
        lines.append(f"seeded {seeded} — security and perf reviews stay on")
        lines.append("")
    lines.append("option                 value        set by")
    lines.append("---------------------- ------------ " + "-" * 34)
    for key in OPTION_KEYS:
        lines.append(f"{key:<22} {values[key]:<12} {sources[key]}")
    lines.append("")
    if "--autopilot" in modes:
        lines.append(
            "options card: skipped (--autopilot)"
            " · every skippable stop: skipped"
        )
    elif "--use-config-options" in modes:
        lines.append("options card: skipped (--use-config-options)")
    else:
        lines.append("options card: show it — the values above are the current ones")
    return "\n".join(lines)


def lift_flags(argv: list[str]) -> tuple[str, list[str]]:
    """Pull `--flags <text>` out of `argv`, returning the text and what remains.

    argparse cannot take this argument, and the failure is the nasty kind: a
    value that begins with a dash is read as another option, so
    `--flags "--adr"` dies with "expected one argument" while
    `--flags "--adr fix the bug"` works, because argparse lets a value through
    once it contains a space. The caller is passing a whole flag string, and
    whether that string happens to be one token is not something they should
    have to think about. So take the token after `--flags` verbatim, whatever
    it looks like, and let argparse have the rest.
    """
    rest: list[str] = []
    text = ""
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--flags":
            if index + 1 >= len(argv):
                raise Fail("--flags needs a value (quote the whole flag string)")
            text = argv[index + 1]
            index += 2
            continue
        if token.startswith("--flags="):
            text = token[len("--flags=") :]
            index += 1
            continue
        rest.append(token)
        index += 1
    return text, rest


def main(argv: list[str]) -> int:
    flag_text, argv = lift_flags(argv)
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "repo", nargs="?", default=None, help="repo or worktree (default: cwd)"
    )
    ap.add_argument(
        "--choice",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="an options-card answer; repeatable, and it beats the flag",
    )
    ap.add_argument(
        "--out",
        help="also write the resolved config here (usually $RUN/config.json)",
    )
    ap.add_argument(
        "--flags",
        default="",
        help=(
            "the run's flag text, quoted as one string "
            "(read before argparse; see lift_flags)"
        ),
    )
    args = ap.parse_args(argv)

    repo = Path(args.repo).expanduser().resolve() if args.repo else Path.cwd()
    if not repo.is_dir():
        raise Fail(f"repo path does not exist: {repo}")

    seeded = seed_global_config()
    flags, modes = parse_flags(flag_text)
    choices = parse_choices(args.choice)
    values, sources = resolve(repo, flags, choices)

    if args.out:
        out = Path(args.out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "options": values,
                    "sources": sources,
                    "autopilot": "--autopilot" in modes,
                    "optionsCard": "skipped" if modes else "shown",
                    "planValidatorPasses": paths.setting(
                        "planValidatorPasses", repo, paths.positive_int
                    ),
                    "codexPlanReviewAxes": paths.review_axes(repo),
                    "scopeFence": scope_fence(repo),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    print(render(values, sources, modes, seeded))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Fail as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
