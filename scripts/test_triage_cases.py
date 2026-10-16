#!/usr/bin/env python3
"""Regression suite for triage_cases.py:  python3 scripts/test_triage_cases.py

The grader exists to tell a promoted finding from a demoted one. Both put the
finding's words in the triage file, so every case here pairs the same text
under `## Rows` and under `## Demoted to Notes` and asserts the two grade
differently. Replay runs against a stub CLI, so the suite never calls a model.

No pytest dependency — the skill's scripts run with bare python3.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

# A plain import: `python3 scripts/<suite>.py` puts scripts/ first on sys.path.
import triage_cases as tc

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def triage(verdict: str, rows: str, demoted: str = "none") -> str:
    return (
        f"# Triage — round 2\n\nVerdict: {verdict}\n\n## Rows\n"
        "| Sev | Location | Req/Concern (reviewers) | Problem → Fix |\n"
        "|---|---|---|---|\n"
        f"{rows}\n\n## Demoted to Notes\n{demoted}\n\n## Notes for the user\nnone\n\n"
        "## Re-review set\nall\n\n## Rework count\n1\n"
    )


CASE = {
    "id": "synthetic",
    "round": 2,
    "workstream": "ws1",
    "verdict": ["NEEDS_REWORK"],
    "in_rows": [r"[Dd]ecod"],
    "not_in_rows": [r"\|\s*\**HIGH\**\s*\|", "SIGHUP"],
    "recorded": "miss",
    "note": "",
    "input": "reviews",
}
DECODE_ROW = "| MEDIUM | red_freeze.py:197 | cleanup | decode error skips kill → test |"


def failed(checks: list[tuple[str, bool]]) -> list[str]:
    return [name for name, ok in checks if not ok]


def case_a_promoted_finding_passes_in_rows() -> None:
    got = failed(tc.grade(CASE, triage("NEEDS_REWORK", DECODE_ROW)))
    check("promoted finding passes in_rows", got == [], f"failed: {got}")


def case_the_same_finding_demoted_fails_in_rows() -> None:
    out = triage("NEEDS_REWORK", "", demoted="- decode error path, deferred")
    got = failed(tc.grade(CASE, out))
    ok = got == [r"in Rows: [Dd]ecod"]
    check("demoted finding fails in_rows (only that check)", ok, f"failed: {got}")


def case_a_demotion_upheld_passes_not_in_rows() -> None:
    out = triage("NEEDS_REWORK", DECODE_ROW, demoted="- Defer SIGHUP too")
    got = failed(tc.grade(CASE, out))
    check("SIGHUP under Demoted passes not_in_rows", got == [], f"failed: {got}")


def case_a_promoted_demotion_fails_not_in_rows() -> None:
    rows = DECODE_ROW + "\n| LOW | red_freeze.py:90 | signals | defer SIGHUP |"
    got = failed(tc.grade(CASE, triage("NEEDS_REWORK", rows)))
    check("SIGHUP in Rows fails not_in_rows", got == ["not in Rows: SIGHUP"], str(got))


def case_a_high_row_fails_calibration() -> None:
    row = DECODE_ROW.replace("MEDIUM", "**HIGH**")
    got = failed(tc.grade(CASE, triage("NEEDS_REWORK", row)))
    ok = len(got) == 1 and got[0].startswith("not in Rows: \\|")
    check("bold HIGH row fails the no-HIGH check", ok, f"failed: {got}")


def case_the_wrong_verdict_fails_and_names_what_it_got() -> None:
    got = failed(tc.grade(CASE, triage("APPROVED_WITH_NOTES", DECODE_ROW)))
    ok = got == ["verdict in ['NEEDS_REWORK'] (got APPROVED_WITH_NOTES)"]
    check("APPROVED_WITH_NOTES fails a NEEDS_REWORK case", ok, f"failed: {got}")


def case_a_missing_rows_section_fails_instead_of_passing_not_in_rows() -> None:
    out = "# Triage\n\nVerdict: NEEDS_REWORK\n\nSIGHUP, decode\n"
    got = failed(tc.grade(CASE, out))
    ok = "## Rows section present" in got
    check("missing ## Rows is its own failure", ok, f"failed: {got}")


def case_every_shipped_case_is_well_formed() -> None:
    cases = tc.load_cases(tc.CASES_DIR)
    bad = []
    for c in cases:
        for p in c["in_rows"] + c["not_in_rows"]:
            try:
                re.compile(p)
            except re.error as e:
                bad.append(f"{c['id']}: {p}: {e}")
        if c["recorded"] not in ("pass", "miss") or not c["verdict"]:
            bad.append(f"{c['id']}: recorded/verdict")
        if not c["input"].strip():
            bad.append(f"{c['id']}: empty input.md")
    misses = [c["id"] for c in cases if c["recorded"] == "miss"]
    check("shipped cases are well formed", bad == [], "; ".join(bad))
    check("shipped cases include a recorded miss", bool(misses), "no overturn case")


STUB = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["STUB_ARGV_LOG"], "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
prompt = sys.stdin.read()
if os.environ.get("STUB_FAIL"):
    sys.stderr.write("boom")
    sys.exit(3)
row = "| MEDIUM | x.py:1 | c | decode → fix |" if "round 2" in prompt else ""
head = "# Triage\\n\\nVerdict: NEEDS_REWORK\\n\\n## Rows\\n"
print(head + row + "\\n\\n## Demoted to Notes\\n")
"""


def write_case(root: Path, name: str, rnd: int) -> None:
    d = root / name
    d.mkdir(parents=True)
    spec = {k: CASE[k] for k in ("verdict", "in_rows", "not_in_rows", "recorded")}
    spec.update(round=rnd, workstream=None, note="")
    (d / "case.json").write_text(json.dumps(spec))
    (d / "input.md").write_text("reviews\n")


def replay(tmp: Path, out: str, samples: int = 1) -> tuple[int, str]:
    stub = tmp / "claude-stub"
    stub.write_text(STUB)
    stub.chmod(0o755)
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = tc.main([
            "replay", "--out", str(tmp / out), "--cases", str(tmp / "cases"),
            "--role", str(tc.ROLE_FILE), "--claude", str(stub),
            "--samples", str(samples),
        ])
    return code, buf.getvalue()


def case_replay_grades_samples_without_tools_or_sessions(tmp: Path) -> None:
    write_case(tmp / "cases", "hit", 2)
    write_case(tmp / "cases", "miss", 1)
    os.environ["STUB_ARGV_LOG"] = str(tmp / "argv.log")
    code, out = replay(tmp, "run", samples=2)
    res = json.loads((tmp / "run" / "results.json").read_text())
    hit = res["cases"]["hit"]["passes"]
    miss = res["cases"]["miss"]["passes"]
    ok = code == 0 and set(hit.values()) == {2} and miss["in Rows: [Dd]ecod"] == 0
    check("replay counts passes per check across samples", ok, f"{res} / {out}")
    argvs = [json.loads(line) for line in (tmp / "argv.log").read_text().splitlines()]
    flags_ok = len(argvs) == 4 and all(
        "--no-session-persistence" in a and a[a.index("--tools") + 1] == ""
        for a in argvs
    )
    check("replay disables tools and session persistence", flags_ok, str(argvs[:1]))
    kept = sorted(p.name for p in (tmp / "run").glob("*.md"))
    check("replay keeps each sample's output", len(kept) == 4, str(kept))


def case_a_failing_cli_raises_instead_of_grading_empty_output(tmp: Path) -> None:
    write_case(tmp / "cases", "hit", 2)
    os.environ["STUB_ARGV_LOG"] = str(tmp / "argv.log")
    os.environ["STUB_FAIL"] = "1"
    try:
        replay(tmp, "run")
        check("CLI failure raises", False, "no exception")
    except RuntimeError as e:
        check("CLI failure raises", "exited 3" in str(e) and "boom" in str(e), str(e))
    finally:
        del os.environ["STUB_FAIL"]


def results_file(tmp: Path, name: str, samples: int, passes: dict) -> str:
    p = tmp / f"{name}.json"
    cases = {cid: {"recorded": "pass", "passes": v} for cid, v in passes.items()}
    p.write_text(json.dumps({"samples": samples, "cases": cases}))
    return str(p)


def compare(before: str, after: str) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = tc.main(["compare", before, after])
    return code, buf.getvalue()


def case_compare_fails_on_a_drop_and_normalises_sample_counts(tmp: Path) -> None:
    before = results_file(tmp, "b", 1, {"a": {"v": 1, "r": 0}})
    gain = results_file(tmp, "g", 3, {"a": {"v": 3, "r": 2}})
    drop = results_file(tmp, "d", 3, {"a": {"v": 2, "r": 1}})
    code_g, out_g = compare(before, gain)
    check("a gain alone exits 0", code_g == 0 and "GAIN  a  r" in out_g, out_g)
    code_d, out_d = compare(before, drop)
    ok = code_d == 1 and "DROP  a  v  1.00 -> 0.67" in out_d
    check("a 1/1 -> 2/3 drop exits 1", ok, out_d)


def case_compare_catches_a_lost_rows_section(tmp: Path) -> None:
    # No in_rows checks, so only the Rows-presence check can see the loss.
    case = dict(CASE, in_rows=[])
    sides = {}
    outputs = (("b", triage("NEEDS_REWORK", "")), ("a", "Verdict: NEEDS_REWORK\n"))
    for name, out in outputs:
        passes = {k.split(" (got ")[0]: int(ok) for k, ok in tc.grade(case, out)}
        sides[name] = results_file(tmp, name, 1, {"c": passes})
    code, out = compare(sides["b"], sides["a"])
    ok = code == 1 and "DROP  c  ## Rows section present" in out
    check("compare fails when ## Rows disappears", ok, out)


def case_compare_skips_a_case_present_on_one_side(tmp: Path) -> None:
    before = results_file(tmp, "b", 1, {"a": {"v": 1}, "old": {"v": 1}})
    after = results_file(tmp, "a", 1, {"a": {"v": 1}})
    code, out = compare(before, after)
    ok = code == 0 and "SKIP  old" in out
    check("a removed case is skipped, not a drop", ok, out)


CASES = [
    case_a_promoted_finding_passes_in_rows,
    case_the_same_finding_demoted_fails_in_rows,
    case_a_demotion_upheld_passes_not_in_rows,
    case_a_promoted_demotion_fails_not_in_rows,
    case_a_high_row_fails_calibration,
    case_the_wrong_verdict_fails_and_names_what_it_got,
    case_a_missing_rows_section_fails_instead_of_passing_not_in_rows,
    case_every_shipped_case_is_well_formed,
]
TMP_CASES = [
    case_replay_grades_samples_without_tools_or_sessions,
    case_a_failing_cli_raises_instead_of_grading_empty_output,
    case_compare_fails_on_a_drop_and_normalises_sample_counts,
    case_compare_catches_a_lost_rows_section,
    case_compare_skips_a_case_present_on_one_side,
]


def main() -> int:
    for case in CASES:
        case()
    for tmp_case in TMP_CASES:
        with tempfile.TemporaryDirectory() as d:
            tmp_case(Path(d))
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            print(f"      {detail}")
    failed_n = sum(1 for _, ok, _ in results if not ok)
    print(f"\n=== {len(results) - failed_n} passed, {failed_n} failed")
    return 1 if failed_n else 0


if __name__ == "__main__":
    sys.exit(main())
