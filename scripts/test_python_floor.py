#!/usr/bin/env python3
"""Check shipped scripts against the supported Python grammar floor.

Parse every shipped Python file, including scripts that other suites never
import. The CI matrix runs behavioral tests on each supported interpreter;
this check catches newer syntax even when run on a newer developer interpreter.
Python 3.10 supports PEP 604 unions without postponed annotations, so they are
no longer a compatibility error.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

FLOOR = (3, 10)
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



def case_accepts_python_310_syntax_and_union_annotations() -> None:
    source = """def classify(value: int | None) -> str:
    match value:
        case None:
            return "missing"
        case _:
            return "present"
"""
    tree = ast.parse(source, feature_version=FLOOR)
    namespace: dict = {}
    exec(compile(tree, "<python-floor>", "exec", dont_inherit=True), namespace)
    classify = namespace["classify"]
    check("Python 3.10 match syntax and runtime unions are accepted",
          classify(None) == "missing" and classify(1) == "present",
          "Python 3.10 constructs must remain usable")


def case_rejects_syntax_newer_than_the_floor() -> None:
    source = "try:\n    pass\nexcept* ValueError:\n    pass\n"
    try:
        ast.parse(source, feature_version=FLOOR)
    except SyntaxError:
        rejected = True
    else:
        rejected = False
    check("Python 3.11 exception groups are rejected at the floor", rejected,
          "except* must not parse as Python 3.10")


CASES = [
    case_every_shipped_module_parses_at_the_floor,
    case_accepts_python_310_syntax_and_union_annotations,
    case_rejects_syntax_newer_than_the_floor,
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
