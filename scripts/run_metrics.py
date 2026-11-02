"""Private run measurements. Missing values are null, never inferred as zero.

next.py records dispatch-to-observation duration, including coordinator delay.
For planning or measured provider usage: start RUN PHASE; finish RUN PHASE;
usage RUN PHASE --cached N --uncached N --output N --source EVIDENCE.
Record attributed rework and subsequently confirmed findings with `event`.
Compare matched historical and pilot runs with `compare BASELINE CANDIDATE ...`.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path


def read(run: Path) -> dict:
    path = run / "metrics.json"
    if not path.exists():
        return {"schema": 1, "phases": {}, "events": []}
    data = json.loads(path.read_text())
    if data.get("schema") != 1:
        raise ValueError("unsupported metrics schema")
    return data


def save(run: Path, data: dict) -> None:
    target = run / "metrics.json"
    temporary = run / "metrics.json.tmp"
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.replace(target)


def start(run: Path, phase: str, now: float | None = None) -> None:
    data = read(run)
    data["phases"].setdefault(phase, {
        "started": time.time() if now is None else now,
        "finished": None, "durationSeconds": None,
        "durationBasis": "dispatch to observation; includes coordinator delay",
        "tokens": {"cached": None, "uncached": None, "output": None},
        "tokenSource": "unavailable: provider usage not supplied",
    })
    save(run, data)


def finish(run: Path, phase: str, now: float | None = None) -> None:
    data = read(run)
    row = data["phases"].get(phase)
    if row is None:
        raise ValueError(f"phase was not started: {phase}")
    if row["finished"] is None:
        row["finished"] = time.time() if now is None else now
        row["durationSeconds"] = max(0, row["finished"] - row["started"])
    save(run, data)


def usage(run: Path, phase: str, tokens: dict, source: str) -> None:
    data = read(run)
    if phase not in data["phases"]:
        raise ValueError(f"phase was not started: {phase}")
    if not source.strip() or any(
            v is not None and (not isinstance(v, int) or isinstance(v, bool) or v < 0)
            for v in tokens.values()):
        raise ValueError("usage requires nonnegative counts and a source")
    data["phases"][phase]["tokens"] = tokens
    data["phases"][phase]["tokenSource"] = source
    save(run, data)


def codex_usage(run: Path, phase: str, files: list[Path]) -> None:
    """Read available Codex exec turn usage, whose input total includes cache."""
    rows = []
    for file in files:
        if not file.exists():
            return  # An unobserved attempt makes the phase total unavailable.
        events = []
        for line in file.read_text().splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and event.get("type") == "turn.completed":
                events.append(event.get("usage", {}))
        if not events:
            return
        rows.extend(events)
    if not rows:
        return

    def total(key: str) -> int | None:
        values = [row.get(key) if isinstance(row, dict) else None for row in rows]
        if all(isinstance(v, int) and not isinstance(v, bool) and v >= 0
               for v in values):
            return sum(values)
        return None

    cached, inputs, output = (total(key) for key in
                              ("cached_input_tokens", "input_tokens", "output_tokens"))
    uncached = (inputs - cached if inputs is not None and cached is not None
                and inputs >= cached else None)
    usage(run, phase, {"cached": cached, "uncached": uncached, "output": output},
          "; ".join(str(file) for file in files))


def event(run: Path, kind: str, ident: str, cause: str, evidence: str) -> None:
    if kind not in ("rework", "confirmed-pr-finding") or not all(
            value.strip() for value in (ident, cause, evidence)):
        raise ValueError("event needs kind, stable id, cause and evidence")
    data = read(run)
    row = {"kind": kind, "id": ident, "cause": cause, "evidence": evidence}
    existing = next((e for e in data["events"]
                     if (e["kind"], e["id"]) == (kind, ident)), None)
    if existing is not None and existing != row:
        raise ValueError("event id already exists with different evidence")
    if existing is None:
        data["events"].append(row)
    save(run, data)


def totals(run: Path) -> dict:
    if not (run / "metrics.json").exists():
        return {key: None for key in ("seconds", "cached", "uncached", "output",
                                     "rework", "confirmedFindings")}
    data = read(run)
    phases = list(data["phases"].values())

    def total(values: list) -> int | float | None:
        return sum(values) if values and all(v is not None for v in values) else None

    out = {"seconds": total([p["durationSeconds"] for p in phases])}
    out.update({key: total([p["tokens"][key] for p in phases])
                for key in ("cached", "uncached", "output")})
    # A missing follow-up is not a clean PR. Explicit observation is required.
    observed = data.get("outcomeObservation")
    out["confirmedFindings"] = (sum(e["kind"] == "confirmed-pr-finding"
                                   for e in data["events"]) if observed else None)
    out["rework"] = sum(e["kind"] == "rework" for e in data["events"])
    return out


def compare(pairs: list[tuple[Path, Path]]) -> dict:
    values = [(totals(base), totals(candidate)) for base, candidate in pairs]
    metrics = {}
    for key in ("seconds", "cached", "uncached", "output", "rework",
                "confirmedFindings"):
        available = [(b[key], c[key]) for b, c in values
                     if b[key] is not None and c[key] is not None]
        metrics[key] = {
            "availablePairs": len(available),
            "unavailablePairs": len(pairs) - len(available),
            "medianBaseline": statistics.median([b for b, _ in available])
            if available else None,
            "medianCandidate": statistics.median([c for _, c in available])
            if available else None,
            "medianPairedDelta": statistics.median([c - b for b, c in available])
            if available else None,
        }
    return {"pairs": len(pairs), "metrics": metrics,
            "limitation": "Small, selected sample; matched tasks are not randomized. "
                          "No quality claim from internal approval or test counts."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("start", "finish", "usage", "event",
                                           "observe", "compare"))
    parser.add_argument("paths", nargs="+")
    for key in ("cached", "uncached", "output"):
        parser.add_argument(f"--{key}", type=int)
    parser.add_argument("--source")
    parser.add_argument("--kind")
    parser.add_argument("--cause")
    args = parser.parse_args()
    if args.command == "compare":
        if len(args.paths) % 2:
            parser.error("compare needs baseline/candidate pairs")
        print(json.dumps(compare([(Path(args.paths[i]), Path(args.paths[i + 1]))
                                  for i in range(0, len(args.paths), 2)]), indent=2))
        return
    run = Path(args.paths[0])
    if args.command == "observe":
        if not args.source:
            parser.error("observe needs --source with review date and evidence")
        data = read(run)
        data["outcomeObservation"] = args.source
        save(run, data)
        return
    if len(args.paths) != 2:
        parser.error("command needs RUN and PHASE or EVENT_ID")
    ident = args.paths[1]
    if args.command == "start":
        start(run, ident)
    elif args.command == "finish":
        finish(run, ident)
    elif args.command == "usage":
        if not args.source:
            parser.error("usage needs --source")
        usage(run, ident, {key: getattr(args, key) for key in
                           ("cached", "uncached", "output")}, args.source)
    elif args.command == "event":
        event(run, args.kind or "", ident, args.cause or "", args.source or "")


if __name__ == "__main__":
    main()
