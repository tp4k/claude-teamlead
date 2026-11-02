"""Collect recovery evidence in a disposable clone; never launch agent trials."""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[3]
TEST_COMMAND = [sys.executable, "-B", "-m", "unittest", "-v", "test_labels"]


def command(cwd: Path, *args: str) -> dict:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                            timeout=120)
    return {"argv": list(args), "exit": result.returncode,
            "output": result.stdout + result.stderr}


def git(repo: Path, *args: str) -> str:
    result = command(repo, "git", *args)
    if result["exit"]:
        raise ValueError(result["output"])
    return result["output"].strip()


def snapshot(repo: Path, expected: str) -> dict:
    head = git(repo, "rev-parse", "HEAD")
    status = git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    return {"head": head, "porcelain": status,
            "tree": "CLEAN" if head == expected and not status else "CHANGED"}


def observe_probes(repo: Path, probes: list[dict]) -> list[dict]:
    """Keep the actual failing test output that the gate's summary omits."""
    results = []
    target = repo / "labels.py"
    for probe in probes:
        original = target.read_text()
        if original.count(probe["old"]) != 1:
            raise ValueError("Probe must identify one exact site")
        changed = original.replace(probe["old"], probe["new"], 1)
        compile(changed, "labels.py", "exec")
        try:
            target.write_text(changed)
            results.append({"probe": probe["probe"],
                            "test_result": command(repo, *TEST_COMMAND)})
        finally:
            target.write_text(original)
    return results


def collect(source: Path, out: Path, head: str, base: str, red: str,
            probes: list[dict]) -> dict:
    """Verify an already applied recovery, preserving its original evidence."""
    source = source.resolve()
    out = out.resolve()
    if source == out or source in out.parents:
        raise ValueError("Evidence output must be outside the source repository")
    if snapshot(source, head)["tree"] != "CLEAN":
        raise ValueError("Source must be clean at the recorded recovery HEAD")
    if not probes:
        raise ValueError("Missing probe patches: cannot establish mutation evidence")
    if any(p.get("file") != "labels.py" for p in probes):
        raise ValueError("Recovery probes must stay in labels.py")
    out.mkdir(parents=True, exist_ok=False)
    repo = out / "checkout"
    cloned = command(out, "git", "clone", "--quiet", "--no-hardlinks",
                     "--", str(source), str(repo))
    if cloned["exit"]:
        raise ValueError(cloned["output"])
    expected = git(repo, "rev-parse", "HEAD")
    if expected != head:
        raise ValueError("Clone HEAD differs from the recorded recovery HEAD")
    snapshots = [snapshot(repo, head)]
    evidence = {"head": head, "base": base, "red": red,
                "commit": git(repo, "show", "-s", "--format=fuller", head),
                "attribution": "Original harness applied the agent's proposed file; "
                "this collector only verifies that existing commit in a clone.",
                "snapshots": snapshots}
    probe_path = out / "probes-ws1-r2.json"
    probe_path.write_text(json.dumps(probes, indent=2) + "\n")
    commands = {
        "tests": TEST_COMMAND,
        "freeze": [sys.executable, str(PLUGIN / "scripts/red_freeze.py"),
                   "--repo", str(repo), red],
        "mutation": [sys.executable, str(PLUGIN / "scripts/mutate.py"),
                     "--repo", str(repo), "--base", base, "--commits", head,
                     "--cmd", shlex.join(TEST_COMMAND), "--probes", str(probe_path),
                     "--max-generic", "0", "--out", str(out / "mutation-ws1-r2.md")],
    }
    for name, args in commands.items():
        if any(s["tree"] != "CLEAN" for s in snapshots):
            break
        if name == "mutation" and evidence["tests"]["exit"]:
            break
        evidence[name] = command(repo, *args)
        snapshots.append(snapshot(repo, head))
    mutation = evidence.get("mutation", {})
    if (mutation.get("exit") == 0
            and all(s["tree"] == "CLEAN" for s in snapshots)):
        evidence["probe_runs"] = observe_probes(repo, probes)
        snapshots.append(snapshot(repo, head))
    outcome = "CANNOT_RUN"
    if all(s["tree"] == "CLEAN" for s in snapshots):
        tests = evidence.get("tests", {})
        freeze = evidence.get("freeze", {})
        mutation = evidence.get("mutation", {})
        frozen = freeze.get("output", "").startswith(("RED_FROZEN", "RED_CHANGED"))
        if (tests.get("exit") == 0 and freeze.get("exit") in (0, 1) and frozen
                and mutation.get("exit") == 0
                and "MUTATION: PASS" in mutation.get("output", "")
                and len(evidence.get("probe_runs", [])) == len(probes)
                and all(p["test_result"]["exit"] == 1
                        for p in evidence.get("probe_runs", []))):
            outcome = "PASS"
        elif tests.get("exit") == 1 or mutation.get("exit") == 1:
            outcome = "FAIL"
    evidence["outcome"] = outcome
    evidence["tree"] = "CLEAN" if all(
        s["tree"] == "CLEAN" for s in snapshots) else "CHANGED"
    (out / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    report = ["# Verifier — recovery evidence supplement", "",
              f"OUTCOME: {outcome}", "", "## Snapshot", "",
              f"head: {head}", f"tree: {evidence['tree']}", "",
              "## Commit attribution", "", evidence["attribution"], "",
              evidence["commit"], "", "## RED run", "",
              "none — round 2 has no new RED commit", ""]
    for name in commands:
        report += [f"## {name.title()}", ""]
        if name in evidence:
            result = evidence[name]
            report += [f"{shlex.join(result['argv'])} → exit {result['exit']}"]
            report += ["> " + line for line in result["output"].splitlines()]
        else:
            report += ["not run — earlier execution or snapshot failed"]
        report += [""]
    report += ["## Observed probe failures", ""]
    for probe in evidence.get("probe_runs", []):
        report += [probe["probe"]]
        report += ["> " + line for line in probe["test_result"]["output"].splitlines()]
        report += [""]
    report += ["The reviewer must match any RED_CHANGED lines to the prior finding.",
               "This supplement does not change the original agent verdicts.", "",
               f"OUTCOME: {outcome}", ""]
    (out / "verifier-r2.md").write_text("\n".join(report))
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "out", "head", "base", "red", "probes"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    result = collect(Path(args.source), Path(args.out).resolve(), args.head,
                     args.base, args.red, json.loads(Path(args.probes).read_text()))
    print(f"OUTCOME: {result['outcome']}; evidence: {args.out}")
    return 0 if result["outcome"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
