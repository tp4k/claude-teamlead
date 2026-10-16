#!/usr/bin/env python3
"""Regression cases for the triage role:  python3 scripts/triage_cases.py <cmd>

  grade   <case-dir> <triage.md>          score one triage output against one case
  replay  --out <dir> [--role F] [--model M] [--samples N] [--cases D]
                                          run the role on every case via `claude -p`
  compare <before/results.json> <after/results.json>
                                          per-check pass-rate deltas; exit 1 on any drop

A case is `evals/triage/cases/<id>/` with `input.md` (the round's plan excerpt,
review and verifier reports, copied in because `prune_runs.py` deletes the run
they came from) and `case.json`:

  verdict       allowed `Verdict:` values
  in_rows       regexes that must match inside `## Rows` (a finding promoted)
  not_in_rows   regexes that must not (a demotion upheld, or no HIGH row)
  recorded      "pass" or "miss": how the triage that actually ran scored
  note          why the expectation is what it is

Checks look only inside `## Rows`, because a demoted finding still appears in
the file under `## Demoted to Notes`; a whole-file match cannot tell a
promotion from a demotion. Expectations come from what happened later: a
demotion Codex or a later round raised again is an overturn and becomes an
`in_rows` check; one that stayed in the ledger is an upheld `not_in_rows`.

Gate a role-file edit by replaying before and after, then `compare`. One
sample is noisy, so use --samples 3 or more before trusting a delta.

No pytest dependency — the skill's scripts run with bare python3.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = ROOT / "evals" / "triage" / "cases"
ROLE_FILE = ROOT / "references" / "roles" / "triage.md"
VERDICT_RE = re.compile(r"(?m)^\W*Verdict:\W*([A-Z_]+)")
ROWS_RE = re.compile(r"(?ms)^## Rows\b(.*?)(?=^## |\Z)")
SECTIONS = (
    "## Rows",
    "## Demoted to Notes",
    "## Notes for the user",
    "## Re-review set",
    "## Rework count",
)
# Each replay is a single prompt with no tools; a triage file comes back in
# well under a minute, so five minutes only catches a hung CLI.
REPLAY_TIMEOUT_S = 300


def load_case(case_dir: Path) -> dict:
    case = json.loads((case_dir / "case.json").read_text())
    case["id"] = case_dir.name
    case["input"] = (case_dir / "input.md").read_text()
    return case


def load_cases(cases_dir: Path) -> list[dict]:
    dirs = sorted(p for p in cases_dir.iterdir() if (p / "case.json").is_file())
    if not dirs:
        raise SystemExit(f"no cases under {cases_dir}")
    return [load_case(d) for d in dirs]


def grade(case: dict, output: str) -> list[tuple[str, bool]]:
    """One (check name, passed) pair per expectation in the case."""
    m = VERDICT_RE.search(output)
    got = m.group(1) if m else None
    checks = [(f"verdict in {case['verdict']} (got {got})", got in case["verdict"])]
    rows_m = ROWS_RE.search(output)
    # Emitted on every sample, not only on failure: compare keys on check names,
    # so a check that exists only when it fails can never register as a drop.
    checks.append(("## Rows section present", rows_m is not None))
    rows = rows_m.group(1) if rows_m else ""
    for p in case["in_rows"]:
        checks.append((f"in Rows: {p}", re.search(p, rows) is not None))
    for p in case["not_in_rows"]:
        checks.append((f"not in Rows: {p}", re.search(p, rows) is None))
    return checks


def prompt_for(case: dict) -> str:
    ws = case["workstream"] or "all"
    return (
        f"You are the teamlead triage step for round {case['round']} "
        f"(workstream {ws}). Consolidate the review and verifier reports below "
        "into the triage file. Output ONLY the triage file content: '# Triage', "
        "a 'Verdict:' line, then "
        + ", ".join(f"'{s}'" for s in SECTIONS)
        + ".\n\n"
        + case["input"]
    )


def run_claude(claude: str, model: str, role: str, prompt: str) -> str:
    # A temp cwd keeps project CLAUDE.md files out of the context, no tools keeps
    # it a single-prompt replay, and no persistence keeps ~/.claude/projects clean.
    with tempfile.TemporaryDirectory() as cwd:
        proc = subprocess.run(
            [
                claude, "-p", "--model", model, "--system-prompt", role,
                "--tools", "", "--disable-slash-commands",
                "--no-session-persistence", "--output-format", "text",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=REPLAY_TIMEOUT_S,
        )
    if proc.returncode != 0:
        tail = proc.stderr.strip()[-500:]
        raise RuntimeError(f"claude exited {proc.returncode}: {tail}")
    return proc.stdout


def cmd_grade(args: argparse.Namespace) -> int:
    checks = grade(load_case(Path(args.case)), Path(args.output).read_text())
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in checks) else 1


def cmd_replay(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    role = Path(args.role).read_text()
    results: dict = {
        "role": str(Path(args.role).resolve()),
        "model": args.model,
        "samples": args.samples,
        "cases": {},
    }
    for case in load_cases(Path(args.cases)):
        passes: dict[str, int] = {}
        for i in range(args.samples):
            text = run_claude(args.claude, args.model, role, prompt_for(case))
            (out / f"{case['id']}.{i}.md").write_text(text)
            for name, ok in grade(case, text):
                # The verdict check's name carries the observed verdict;
                # strip it so the key is the same across samples.
                key = name.split(" (got ")[0]
                passes[key] = passes.get(key, 0) + int(ok)
        results["cases"][case["id"]] = {"recorded": case["recorded"], "passes": passes}
        full = sum(passes.values()) == len(passes) * args.samples
        mark = "PASS" if full else "FAIL"
        print(f"{mark}  {case['id']}  (recorded: {case['recorded']})")
        for key, n in passes.items():
            if n < args.samples:
                print(f"      {n}/{args.samples}  {key}")
    (out / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    print(f"\nwrote {out / 'results.json'}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    before = json.loads(Path(args.before).read_text())
    after = json.loads(Path(args.after).read_text())
    dropped = 0
    for cid in sorted(set(before["cases"]) | set(after["cases"])):
        if cid not in before["cases"] or cid not in after["cases"]:
            print(f"SKIP  {cid}: present in only one result set")
            continue
        b, a = before["cases"][cid]["passes"], after["cases"][cid]["passes"]
        for key in sorted(set(b) | set(a)):
            rb = b.get(key, 0) / before["samples"]
            ra = a.get(key, 0) / after["samples"]
            if ra < rb:
                dropped += 1
                print(f"DROP  {cid}  {key}  {rb:.2f} -> {ra:.2f}")
            elif ra > rb:
                print(f"GAIN  {cid}  {key}  {rb:.2f} -> {ra:.2f}")
    print(f"\n{dropped} check(s) dropped")
    return 1 if dropped else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Regression cases for the triage role.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grade")
    g.add_argument("case")
    g.add_argument("output")
    r = sub.add_parser("replay")
    r.add_argument("--out", required=True)
    r.add_argument("--cases", default=str(CASES_DIR))
    r.add_argument("--role", default=str(ROLE_FILE))
    r.add_argument("--model", default="sonnet")
    r.add_argument("--samples", type=int, default=1)
    r.add_argument("--claude", default="claude", help="CLI to run (tests pass a stub)")
    c = sub.add_parser("compare")
    c.add_argument("before")
    c.add_argument("after")
    args = ap.parse_args(argv)
    commands = {"grade": cmd_grade, "replay": cmd_replay, "compare": cmd_compare}
    return commands[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
