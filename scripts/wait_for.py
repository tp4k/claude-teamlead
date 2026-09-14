#!/usr/bin/env python3
"""Wait until every named $RUN file is on disk and stable, then print its routing line.

    python3 $SKILL/scripts/wait_for.py --timeout 480 FILE [FILE ...]

One call = one coordinator turn per phase, instead of a `sleep` per poll. A file
counts as ready when it exists, is non-empty and its size has not changed between
two consecutive polls (a Write in progress grows; a finished one does not).

`--rewritten FILE` (repeatable) is required for any phase that overwrites a file
that already exists — the planner's Fix mode rewriting `plan.md` is the one in
this skill. Without it such a file is already present and already size-stable, so
it is declared ready on the second poll and the coordinator routes on the PREVIOUS
round's verdict, seconds after dispatching an agent that has written nothing yet.
A `--rewritten` file must additionally show an mtime newer than the moment waiting
began. Pass it per call rather than making it the default: for a file the phase
does not touch, demanding a fresh mtime turns a finished artifact into a certain
timeout.

`--expect FILE TOKEN` (repeatable) holds a file unready until its routing line
actually says TOKEN, and it is what a rewrite needs on top of `--rewritten`. Fresh
mtime plus size stability is not enough on its own: an agent that rewrites a file
through several `Edit` calls leaves it fresh-mtime AND the same size across two
consecutive polls in the gap *between* two edits, so the file is declared ready
half-rewritten and the coordinator routes on a document the agent is still
editing. Observed twice in iteration 15 — eval-9 treatment and eval-6 baseline,
both logging `exit 0 on a partially rewritten file` with no `PLAN_FIXED` in it
yet, both papered over by a hand-rolled grep loop in the coordinator. The marker
the phase writes last is the only honest "I am done" signal, so wait for it:
`--rewritten $RUN/plan.md --expect $RUN/plan.md PLAN_FIXED`. A token that never
arrives times out, which is the correct failure — a timeout asks you to look,
whereas a premature exit 0 routes the whole run on stale content.

The routing line is searched from the END of the file — see `routing_line`.

Exit codes, so the coordinator routes on the exit code plus the printed lines and
never `cat`s the file:
  0  every file ready; one line per file: `<name>: <routing line>` — a line
     starting with `OUTCOME:`, `Verdict:`, `VERDICT:` or `status:` (the colon
     must follow the keyword directly), or with one of the bare tokens
     PLAN_WRITTEN / PLAN_FIXED / PLAN_VALID / PLAN_NEEDS_FIX; else the first
     non-heading line
  1  early exit: a ready file's routing line says `status: blocked|partial` or
     `OUTCOME: CANNOT_RUN` — read that file now, do not wait for the slow siblings
  2  timeout: the files not yet ready are listed, and one already present but
     unchanged is marked as still the pre-dispatch copy; wait one more chunk,
     then check the child's task output
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

# The keyword must be IMMEDIATELY followed by its colon. A `Verdict on scope:` line
# closing the plan-validator's Smaller/none section is not the plan verdict, and
# because the search runs from the END of the file it would otherwise outrank the
# real `Verdict: PLAN_VALID` eleven lines above it.
# The PLAN_* tokens carry their own meaning, so they still match bare.
ROUTING = re.compile(r"^\s*(?:\*\*)?(?:(OUTCOME|VERDICT|status)(?:\*\*)?[ \t]*:"
                     r"|(PLAN_WRITTEN|PLAN_FIXED|PLAN_VALID|PLAN_NEEDS_FIX)\b)", re.I)
EARLY = re.compile(r"status:\s*(blocked|partial)|OUTCOME:\s*CANNOT_RUN", re.I)


def routing_line(path: Path) -> str:
    """The phase's routing line, searched from the END of the file.

    Every role here ends its output with the routing block, and some outputs quote
    spec text verbatim — a `plan.md` whose spec excerpt describes a `status:` field
    would otherwise route on the quotation instead of the planner's own verdict.
    Searching backwards lets the file's last word win, which is what "end the file
    with the block" already promises.
    """
    raw = path.read_text(errors="replace").splitlines()
    lines = [s for s in (ln.strip() for ln in raw) if s]
    for s in reversed(lines):
        if ROUTING.match(s):
            return s.strip("* ")
    return next((s for s in lines if not s.startswith("#")), "")[:160]


def token_present(path: Path, token: str) -> bool:
    """True when the file's ROUTING LINE carries `token`.

    Deliberately not a whole-file search. A brief or plan that *mentions* the
    marker in prose — "the Fix-mode planner ends with PLAN_FIXED" — would satisfy
    a substring scan while the phase has still written nothing, which is the very
    failure this flag exists to stop. The routing line is the phase speaking for
    itself, which is the same reason every other decision here reads it.
    """
    return re.search(rf"\b{re.escape(token)}\b", routing_line(path), re.I) is not None


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--timeout", type=int, default=480,
                    help="seconds to block before exit 2 (default 480)")
    ap.add_argument("--poll", type=int, default=5,
                    help="seconds between polls (default 5)")
    ap.add_argument("--rewritten", action="append", metavar="FILE", default=[],
                    help="file this phase overwrites; ready needs a fresh mtime too")
    ap.add_argument("--expect", action="append", nargs=2, default=[],
                    metavar=("FILE", "TOKEN"),
                    help="hold FILE unready until its routing line says TOKEN; "
                         "pair it with --rewritten so a mid-edit file cannot "
                         "look ready between two Edit calls")
    ap.add_argument("files", nargs="+")
    a = ap.parse_args()

    files = [Path(f) for f in a.files]
    last_size: dict[Path, int] = {}
    ready: set[Path] = set()
    # Only files that ALREADY exist need the mtime bump. A `--rewritten` file missing
    # at launch is being created for the first time, and existence plus size
    # stability already prove that.
    rewritten = {Path(f) for f in a.rewritten}
    start_mtime_ns = {f: f.stat().st_mtime_ns for f in rewritten if f.exists()}
    for f in rewritten:
        if f not in set(files):
            print(f"--rewritten {f.name} is not in the wait list; nothing waits on it")
            return 2
    expect: dict[Path, str] = {Path(f): token for f, token in a.expect}
    for f in expect:
        if f not in set(files):
            print(f"--expect {f.name} is not in the wait list; nothing waits on it")
            return 2
    deadline = time.monotonic() + a.timeout

    while True:
        for f in files:
            if f in ready or not f.exists():
                continue
            st = f.stat()
            size = st.st_size
            stale = f in start_mtime_ns and st.st_mtime_ns <= start_mtime_ns[f]
            # A half-rewritten file is fresh-mtime and size-stable in the gap
            # between two Edit calls, so size stability alone cannot tell
            # "finished" from "paused". The awaited token can.
            unmarked = f in expect and not token_present(f, expect[f])
            if size > 0 and not stale and not unmarked and last_size.get(f) == size:
                ready.add(f)
                # Match the routing line only, not the whole file: a spec
                # excerpt quoting `status: blocked` is not this phase
                # reporting itself blocked.
                line = routing_line(f)
                if EARLY.search(line):
                    print(f"EARLY_EXIT {f.name}: {line}")
                    return 1
            last_size[f] = size
        if len(ready) == len(files):
            for f in files:
                print(f"{f.name}: {routing_line(f)}")
            return 0
        if time.monotonic() >= deadline:
            # "not rewritten yet" and "not there at all" need different
            # follow-ups, so name which one it is.
            def why(f: Path) -> str:
                if f.exists() and f in expect and not token_present(f, expect[f]):
                    return f"{f.name} (exists, no {expect[f]} in its routing line yet)"
                if f in start_mtime_ns:
                    return f"{f.name} (still the pre-dispatch copy)"
                return f.name

            pending = [why(f) for f in files if f not in ready]
            print(f"TIMEOUT after {a.timeout}s; missing: {', '.join(pending)}")
            return 2
        time.sleep(a.poll)


if __name__ == "__main__":
    sys.exit(main())
