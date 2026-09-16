#!/usr/bin/env python3
"""Regression suite for corpus_ab.py:  python3 scripts/test_corpus_ab.py

F8 found that the round-6 corpus calibration was recorded as a bare number
with no manifest, so a 174-vs-178 discrepancy could not be resolved from the
record. These cases never touch the real corpus — the fixtures are synthetic
plans and two synthetic `review_package`-shaped modules in a
`tempfile.TemporaryDirectory()` — because the point is that the harness
itself is reproducible, not any particular measurement of real plans.

No pytest dependency — the skill's scripts run with bare python3.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

# Loaded by path rather than imported: a plain `import` here has to follow a
# `sys.path` edit, which is the E402 the house linter refuses to have
# silenced.
_SPEC = importlib.util.spec_from_file_location(
    "corpus_ab", Path(__file__).resolve().parent / "corpus_ab.py"
)
ab = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ab)

MANIFEST_FIELD_SEP = "  "

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


# Two synthetic `review_package`-shaped modules. Each defines only the one
# function corpus_ab.py calls, because the harness is what is under test, not
# the real classifier — that suite already lives in test_review_package.py.
BASE_MODULE_SRC = 'def plan_is_structured(text):\n    return "## Real" in text\n'
STRICTER_MODULE_SRC = (
    'def plan_is_structured(text):\n'
    '    return "## Real" in text and "## Extra" in text\n'
)

STABLE_PLAN = "## Real\n## Extra\nboth sections present\n"
DROPPED_PLAN = "## Real\nonly the one section a stricter reading now rejects\n"


def write_manifest(tmp: Path, plans: list[Path]) -> Path:
    manifest = tmp / "corpus-manifest.txt"
    lines = [
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}{MANIFEST_FIELD_SEP}{p}"
        for p in plans
    ]
    manifest.write_text("\n".join(lines) + "\n")
    return manifest


def run_ab(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = ab.main(argv)
    return rc, out.getvalue(), err.getvalue()


def case_the_ab_reports_zero_drift_on_an_unchanged_module(tmp: Path) -> None:
    module = tmp / "review_package_same.py"
    module.write_text(BASE_MODULE_SRC)
    plan = tmp / "plan.md"
    plan.write_text(STABLE_PLAN)
    manifest = write_manifest(tmp, [plan])
    rc, out, err = run_ab(
        ["--before", str(module), "--after", str(module), "--manifest", str(manifest)]
    )
    check(
        "the same module before and after reports zero drift",
        rc == 0 and "newly rejected: 0" in out and "newly accepted: 0" in out,
        f"rc={rc} out={out!r} err={err!r}",
    )


def case_a_newly_rejected_plan_is_counted_and_named(tmp: Path) -> None:
    before = tmp / "review_package_before.py"
    before.write_text(BASE_MODULE_SRC)
    after = tmp / "review_package_after.py"
    after.write_text(STRICTER_MODULE_SRC)
    stable = tmp / "stable.md"
    stable.write_text(STABLE_PLAN)
    dropped = tmp / "dropped.md"
    dropped.write_text(DROPPED_PLAN)
    manifest = write_manifest(tmp, [stable, dropped])
    rc, out, err = run_ab(
        ["--before", str(before), "--after", str(after), "--manifest", str(manifest)]
    )
    check(
        "the plan whose sections a stricter reading drops is named by path",
        rc == 0
        and "newly rejected: 1" in out
        and str(dropped) in out
        and "newly accepted: 0" in out,
        f"rc={rc} out={out!r} err={err!r}",
    )


def case_a_manifest_entry_whose_file_changed_is_refused(tmp: Path) -> None:
    module = tmp / "review_package_same.py"
    module.write_text(BASE_MODULE_SRC)
    plan = tmp / "plan.md"
    plan.write_text(STABLE_PLAN)
    manifest = write_manifest(tmp, [plan])
    plan.write_text(STABLE_PLAN + "edited underneath the manifest\n")
    rc, out, err = run_ab(
        ["--before", str(module), "--after", str(module), "--manifest", str(manifest)]
    )
    check(
        "a corpus file that changed on disk makes the run refuse, not measure silently",
        rc != 0 and "corpus size" not in out and "changed on disk" in err,
        f"rc={rc} out={out!r} err={err!r}",
    )


def case_a_vanished_manifest_entry_is_reported_as_missing(tmp: Path) -> None:
    module = tmp / "review_package_same.py"
    module.write_text(BASE_MODULE_SRC)
    kept = tmp / "kept.md"
    kept.write_text(STABLE_PLAN)
    gone = tmp / "gone.md"
    gone.write_text(STABLE_PLAN)
    manifest = write_manifest(tmp, [kept, gone])
    gone.unlink()

    rc_default, out_default, err_default = run_ab(
        ["--before", str(module), "--after", str(module), "--manifest", str(manifest)]
    )
    rc_allow, out_allow, err_allow = run_ab(
        [
            "--before",
            str(module),
            "--after",
            str(module),
            "--manifest",
            str(manifest),
            "--allow-missing",
        ]
    )
    check(
        "a vanished entry refuses by default, and --allow-missing measures the "
        "survivors while naming the count that vanished",
        rc_default != 0
        and "corpus size" not in out_default
        and "missing" in err_default
        and rc_allow == 0
        and "corpus size: 1" in out_allow
        and "1 manifest entry is missing" in out_allow,
        f"default rc={rc_default} out={out_default!r} err={err_default!r} "
        f"allow rc={rc_allow} out={out_allow!r} err={err_allow!r}",
    )


def case_an_empty_manifest_is_refused_not_a_zero_drift_pass(tmp: Path) -> None:
    """A zero-entry manifest is a refusal, not a vacuous zero-drift pass."""
    module = tmp / "review_package_same.py"
    module.write_text(BASE_MODULE_SRC)
    manifest = write_manifest(tmp, [])
    rc, out, err = run_ab(
        ["--before", str(module), "--after", str(module), "--manifest", str(manifest)]
    )
    check(
        "an empty manifest refuses instead of reporting zero drift",
        rc != 0
        and "corpus size" not in out
        and "newly rejected" not in out
        and "newly accepted" not in out
        and "no entries to measure" in err,
        f"rc={rc} out={out!r} err={err!r}",
    )


def case_an_unreadable_manifest_refuses_instead_of_raising(tmp: Path) -> None:
    """A manifest path that cannot be read refuses through CorpusRefused,
    not an OSError or UnicodeDecodeError propagating out of main."""
    module = tmp / "review_package_same.py"
    module.write_text(BASE_MODULE_SRC)
    absent = tmp / "does-not-exist.txt"
    rc, out, err = run_ab(
        ["--before", str(module), "--after", str(module), "--manifest", str(absent)]
    )
    check(
        "an unreadable manifest refuses cleanly instead of raising",
        rc != 0 and "corpus size" not in out and "cannot read manifest" in err,
        f"rc={rc} out={out!r} err={err!r}",
    )
    non_utf8 = tmp / "non-utf8-manifest.txt"
    non_utf8.write_bytes(b"abc  /tmp/\xff.md\n")
    rc, out, err = run_ab(
        ["--before", str(module), "--after", str(module), "--manifest", str(non_utf8)]
    )
    check(
        "a non-UTF-8 manifest refuses cleanly instead of raising UnicodeDecodeError",
        rc != 0
        and "cannot read manifest" in err
        and "Traceback" not in out
        and "Traceback" not in err,
        f"rc={rc} out={out!r} err={err!r}",
    )


def case_allow_missing_with_no_survivors_is_still_refused(tmp: Path) -> None:
    """--allow-missing over a manifest whose every entry vanished is still a
    refusal, by a message distinct from the empty-manifest one."""
    module = tmp / "review_package_same.py"
    module.write_text(BASE_MODULE_SRC)
    gone_one = tmp / "gone_one.md"
    gone_one.write_text(STABLE_PLAN)
    gone_two = tmp / "gone_two.md"
    gone_two.write_text(STABLE_PLAN)
    manifest = write_manifest(tmp, [gone_one, gone_two])
    gone_one.unlink()
    gone_two.unlink()
    rc, out, err = run_ab(
        [
            "--before",
            str(module),
            "--after",
            str(module),
            "--manifest",
            str(manifest),
            "--allow-missing",
        ]
    )
    check(
        "--allow-missing over an all-vanished manifest still refuses, "
        "distinctly from an empty manifest",
        rc != 0
        and "corpus size" not in out
        and "no survivors left to measure" in err
        and "no entries to measure" not in err,
        f"rc={rc} out={out!r} err={err!r}",
    )


CASES = [
    case_the_ab_reports_zero_drift_on_an_unchanged_module,
    case_a_newly_rejected_plan_is_counted_and_named,
    case_a_manifest_entry_whose_file_changed_is_refused,
    case_a_vanished_manifest_entry_is_reported_as_missing,
    case_an_empty_manifest_is_refused_not_a_zero_drift_pass,
    case_an_unreadable_manifest_refuses_instead_of_raising,
    case_allow_missing_with_no_survivors_is_still_refused,
]


def main() -> int:
    for case in CASES:
        with tempfile.TemporaryDirectory() as d:
            case(Path(d))
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            print(f"      {detail}")
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"\n=== {len(results) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
