"""Conservative, opt-in routing for the small-task pilot."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import paths

RISKS = ("uncertain", "storage", "protocol", "security", "concurrency", "migration")
EVIDENCE = ("consumer", "callers", "boundary", "library", "verification")


def fingerprint(run: Path) -> str:
    """Bind the assessment to the plan and its concrete instructions."""
    files = [run / name for name in ("plan.md", "questions.md", "plan-validation.md")]
    files += sorted((run / "briefs").glob("impl-ws*-r1.md"))
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes() if path.exists() else b"missing")
        digest.update(b"\0")
    return digest.hexdigest()


def selection(run: Path) -> tuple[str, str]:
    config = paths.read_json(run / "config.json")
    opts = config.get("options", {})
    if not isinstance(opts, dict) or opts.get("workflowProfile") != "adaptive":
        return "standard", "default workflow"
    if config.get("scopeFence") is not True:
        return "standard", "scope fence is not enabled"
    if opts.get("codexCodeReview", "on") != "on":
        return "standard", "independent final review is disabled"
    if any(opts.get(key) == "on" for key in ("securityReview", "perfReview")):
        return "standard", "explicit full specialist review requested"
    assessment = paths.read_json(run / "workflow-assessment.json")
    if assessment.get("fingerprint") != fingerprint(run):
        return "standard", "assessment missing or stale"
    if assessment.get("bounded") is not True:
        return "standard", "task is not explicitly bounded"
    risks = assessment.get("risks", {})
    if not isinstance(risks, dict) or any(risks.get(key) is not False for key in RISKS):
        return "standard", "risk or uncertainty requires the existing stages"
    evidence = assessment.get("evidence", {})
    if not isinstance(evidence, dict) or any(
            not isinstance(evidence.get(key), str) or not evidence[key].strip()
            for key in EVIDENCE):
        return "standard", "assessment lacks consumer or verification evidence"
    plan = (run / "plan.md").read_text()
    streams = re.findall(r"^##\s+WS-(\d+)\b", plan, re.M)
    if len(streams) != 1:
        return "standard", "pilot requires one consolidated workstream"
    ws = streams[0]
    questions = (run / "questions.md").read_text()
    routes = re.findall(rf"^WS-{ws}\s*\|.*$", questions, re.M)
    if len(routes) != 1 or not re.search(r"\|\s*S\s*\|", routes[0]):
        return "standard", "workstream size is not explicitly small"
    if any(not re.search(rf"\b{tag}:\s*no\b", routes[0])
           for tag in ("input", "hot", "public")):
        return "standard", "review axis requires the existing stages"
    validation = (run / "plan-validation.md").read_text()
    upgrades = run / "tag-upgrades.md"
    if upgrades.exists():
        validation += upgrades.read_text()
    if re.search(r"requires\s+(input|hot|public):\s*yes", validation):
        return "standard", "validator upgraded a review axis"
    briefs = list((run / "briefs").glob("impl-ws*-r*.md"))
    if len(briefs) != 1:
        return "standard", "rework retains the existing stages"
    brief = briefs[0].read_text()
    fence = re.search(r"^```scope\s*\n(.+?)^```", brief, re.M | re.S)
    if not fence or not fence.group(1).strip():
        return "standard", "no bounded file scope"
    for line in fence.group(1).strip().splitlines():
        path = Path(line.strip())
        repo = Path((run / "repo.txt").read_text().strip())
        if (path.is_absolute() or ".." in path.parts or str(path) == "."
                or any(c in line for c in "*?[") or line.rstrip().endswith("/")
                or (repo / path).is_dir()):
            return "standard", "pilot requires explicit file paths"
    return "adaptive", "bounded low-risk task; verification and cumulative final review"


if __name__ == "__main__":
    import sys

    run = Path(sys.argv[1])
    if "--fingerprint" in sys.argv[2:]:
        print(fingerprint(run))
    else:
        profile, reason = selection(run)
        print(json.dumps({"profile": profile, "reason": reason}))
