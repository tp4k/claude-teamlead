#!/usr/bin/env python3
"""Regression suite for the declared Python floor:  python3 scripts/test_python_floor.py

`plugin.json` and the CI matrix both say 3.9, but nothing enforced it. The other
suites each import one module, and the scripts nothing imports — `prune_runs.py`
is one — were never loaded on any version at all. A floor that only CI's oldest
job could disprove, on files that job never touches, is not a floor.

Two different failures are checked, because they fail at different moments:

  * syntax newer than the floor, which `ast.parse(feature_version=...)` rejects
    the way an old interpreter would;
  * PEP 604 (`X | Y`) in an annotation, which is *valid syntax* on 3.9 and
    raises `TypeError` at def time instead — unless the module carries
    `from __future__ import annotations`, which keeps annotations as strings.

The second one is why this file exists: `prune_runs.py` shipped a
`-> datetime | None` return annotation with no future import, so the module
could not be imported on 3.9 or 3.10 and every test suite stayed green.

No pytest dependency — the skill's scripts run with bare python3, and a suite
that needs an install is a suite nobody runs.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

FLOOR = (3, 9)
ROOT = Path(__file__).resolve().parent.parent

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def sources() -> list[Path]:
    """Every Python file the plugin ships, in a stable order.

    `.git` and the disposable review checkouts are skipped: a review tree is a
    copy of this same source that happens to be lying around during a run, and
    failing on it would make the suite's result depend on whether one is open.
    """
    skip = {".git", "review-tree", "pre-review-tree", "__pycache__"}
    return sorted(
        path
        for path in ROOT.rglob("*.py")
        if not skip & set(path.relative_to(ROOT).parts)
    )


def annotations_of(tree: ast.AST) -> list[ast.expr]:
    """Just the expressions written in an annotation position.

    Deliberately not "every node under a function": `a | b` in a body is
    ordinary bitwise arithmetic on any version, and flagging it would push the
    next person toward silencing the check rather than fixing a real break.
    """
    found: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.returns is not None:
                found.append(node.returns)
        elif isinstance(node, ast.arg) and node.annotation is not None:
            found.append(node.annotation)
        elif isinstance(node, ast.AnnAssign):
            found.append(node.annotation)
    return found


def has_future_annotations(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == "__future__"
        and any(alias.name == "annotations" for alias in node.names)
        for node in ast.walk(tree)
    )


def runtime_union_lines(source: str) -> list[int]:
    """Lines whose annotation would raise `TypeError` on the floor, if any.

    An empty list for a module that postpones evaluation is the whole point:
    with the future import the annotation is never evaluated, so `X | Y` there
    is free, and demanding `Optional[X]` everywhere would be a style rule
    wearing a compatibility rule's clothes.
    """
    tree = ast.parse(source)
    if has_future_annotations(tree):
        return []
    return sorted(
        node.lineno
        for annotation in annotations_of(tree)
        for node in ast.walk(annotation)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr)
    )


GOOD_POSTPONED = (
    "from __future__ import annotations\n"
    "from pathlib import Path\n"
    "def f(a: int | None) -> Path | None: ...\n"
)
GOOD_NO_UNION = (
    "from typing import Optional\n"
    "def f(a: Optional[int]) -> Optional[int]: ...\n"
)
BAD_RETURN = "from pathlib import Path\ndef f(a: int) -> Path | None: ...\n"
BAD_ARG = "def f(a: int | None) -> int: ...\n"
BAD_FIELD = "class C:\n    x: int | None = None\n"
BITWISE_BODY = "def f(a: int, b: int) -> int:\n    return a | b\n"


def case_the_detector_finds_a_runtime_union() -> None:
    """A guard that cannot fail proves nothing, so it is aimed at known-bad input
    first. Each shape is a separate annotation position — return, argument and
    class field — because they are separate branches of the walk."""
    hits = {
        "return": runtime_union_lines(BAD_RETURN),
        "argument": runtime_union_lines(BAD_ARG),
        "class field": runtime_union_lines(BAD_FIELD),
    }
    check(
        "an unpostponed PEP 604 union is found in every annotation position",
        all(hits.values()),
        f"hits={hits}",
    )


def case_the_detector_accepts_what_the_floor_accepts() -> None:
    """The discriminating half. A check that flagged these would be satisfied by
    deleting the future import and rewriting every annotation, which is not the
    defect and would make the suite an obstacle rather than a floor."""
    clean = {
        "postponed": runtime_union_lines(GOOD_POSTPONED),
        "no union": runtime_union_lines(GOOD_NO_UNION),
        "bitwise in a body": runtime_union_lines(BITWISE_BODY),
    }
    check(
        "postponed unions and ordinary bitwise maths are not reported",
        not any(clean.values()),
        f"hits={clean}",
    )


def case_every_shipped_module_parses_at_the_floor() -> None:
    bad: list[str] = []
    for path in sources():
        try:
            ast.parse(path.read_text(), feature_version=FLOOR)
        except SyntaxError as exc:
            bad.append(f"{path.relative_to(ROOT)}:{exc.lineno}: {exc.msg}")
    check(
        f"every shipped .py parses as Python {FLOOR[0]}.{FLOOR[1]}",
        not bad,
        "\n      ".join(bad),
    )


def case_no_module_evaluates_a_union_annotation() -> None:
    """The one that would have caught `prune_runs.py`. It runs on every version,
    so the 3.9 job is no longer the only thing standing between the declaration
    and a module that cannot be imported under it."""
    bad = [
        f"{path.relative_to(ROOT)}:{line}"
        for path in sources()
        for line in runtime_union_lines(path.read_text())
    ]
    check(
        "no module evaluates a PEP 604 union at def time",
        not bad,
        "add `from __future__ import annotations` to:\n      "
        + "\n      ".join(bad),
    )


CASES = [
    case_the_detector_finds_a_runtime_union,
    case_the_detector_accepts_what_the_floor_accepts,
    case_every_shipped_module_parses_at_the_floor,
    case_no_module_evaluates_a_union_annotation,
]


def main() -> int:
    for case in CASES:
        case()
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            print(f"      {detail}")
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"\n=== {len(results) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
