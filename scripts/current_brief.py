"""Build compact current instructions and preserve explicit review decisions."""
from __future__ import annotations

import json
import re
from pathlib import Path

DECISIONS = re.compile(r"^```decision-records\s*\n(.*?)^```", re.M | re.S)
INHERITED = ("Repo", "Scope", "Spec", "Observable acceptance", "Test plan",
             "Reuse and scope", "Do not touch", "Project forbiddens",
             "Verification commands")


def sections(text: str) -> list[tuple[str, str]]:
    """Top-level sections, preserving fenced spec excerpts verbatim."""
    found: list[tuple[str, str]] = []
    name = ""
    body: list[str] = []
    fence = ""
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            if (marker and marker.group(1)[0] == fence[0]
                    and len(marker.group(1)) >= len(fence)
                    and not marker.group(2).strip()):
                fence = ""
        elif marker:
            fence = marker.group(1)
        else:
            heading = re.match(r"^##[ \t]+(.+?)\s*$", line)
            if heading:
                if name:
                    found.append((name, "".join(body)))
                name, body = heading.group(1), []
                continue
        body.append(line)
    if name:
        found.append((name, "".join(body)))
    return found


def has_constraint(name: str, body: str) -> bool:
    """Match the scope hook and verifier's inheritance rules."""
    if name == "Scope":
        return bool(re.search(r"^```scope\s*\n.*?^```", body, re.M | re.S))
    if name == "Verification commands":
        return bool(re.search(r"^\s*[-*]\s+`([^`]+)`\s*$", body, re.M))
    return bool(body.strip())


def decisions(run: Path) -> list[dict]:
    """Newest explicit revision per id; absent rows never erase a decision."""
    versions: dict[tuple[str, int], dict] = {}
    sources = [run / "plan.md", run / "questions.md"] + sorted(run.glob("triage-*.md"))
    sources += sorted((run / "report-history").rglob("triage-*.md"))
    for source in sources:
        if not source.exists():
            continue
        for block in DECISIONS.findall(source.read_text()):
            rows = json.loads(block)
            if not isinstance(rows, list):
                raise ValueError(f"{source.name}: decision-records must be a list")
            for row in rows:
                if not isinstance(row, dict) or any(
                        not isinstance(row.get(k), str) or not row[k].strip()
                        for k in ("id", "action", "reason", "evidence")):
                    raise ValueError(f"{source.name}: incomplete decision record")
                if row["action"] not in ("fix", "decline", "defer"):
                    raise ValueError(f"{source.name}: invalid decision action")
                revision = row.get("revision")
                if (not isinstance(revision, int) or isinstance(revision, bool)
                        or revision < 1):
                    raise ValueError(f"{source.name}: invalid decision revision")
                key = (row["id"], revision)
                if key in versions and versions[key]["record"] != row:
                    raise ValueError(f"conflicting decision revision: {key}")
                versions.setdefault(key, {"record": row, "sources": []})
                versions[key]["sources"].append(source.relative_to(run).as_posix())
    latest: dict[str, dict] = {}
    for (ident, revision), item in sorted(versions.items()):
        latest[ident] = {**item["record"], "sources": item["sources"]}
    return list(latest.values())


def decision_text(run: Path) -> str:
    rows = decisions(run)
    if not rows:
        return "No structured decisions recorded; consult plan and prior triage.\n"
    return "\n".join(
        f"- {row['id']} r{row['revision']}: {row['action']} — {row['reason']} "
        f"Evidence: {row['evidence']}. Source: {', '.join(row['sources'])}."
        for row in rows) + "\n"


def write_decisions(run: Path) -> Path:
    target = run / "current-decisions.md"
    target.write_text("# Current decisions\n\n" + decision_text(run))
    return target


def write(run: Path, ws: int, rnd: int) -> Path:
    """Inherit only current sections, retaining source paths for audit."""
    current = run / "briefs" / f"impl-ws{ws}-r{rnd}.md"
    text = current.read_text()
    present = {name for name, body in sections(text) if has_constraint(name, body)}
    inherited: dict[str, tuple[str, str]] = {}
    for number in range(rnd - 1, 0, -1):
        earlier = run / "briefs" / f"impl-ws{ws}-r{number}.md"
        if not earlier.exists():
            continue
        for name, body in sections(earlier.read_text()):
            if (name in INHERITED and name not in present and name not in inherited
                    and has_constraint(name, body)):
                inherited[name] = (body, earlier.name)
    for name in INHERITED:
        if name in inherited:
            body, source = inherited[name]
            text += f"\n## {name}\n\nInherited from {source}.\n\n{body.rstrip()}\n"
    text += "\n## Current review decisions\n\n" + decision_text(run)
    target = run / "briefs" / f"current-ws{ws}-r{rnd}.md"
    target.write_text(text)
    return target
