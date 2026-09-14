"""Create the run directory for one teamlead invocation and print its path.

Usage: python3 new_run.py <repo-path> <slug> [--task-file <path>]

Creates $TEAMLEAD_HOME/runs/<repo-name>/<YYYY-MM-DD-HHMM>-<slug>/ (default
~/.teamlead/runs/, suffixing -2, -3 on collision), prunes old runs first (see
prune_runs.py), writes task.md when given, and prints the absolute run directory
as the only stdout line that starts with RUN_DIR=.
The slug is lower-cased and reduced to [a-z0-9-], max 40 chars.

It also asks for the session to be renamed to the slug — see session_title.py. The
rename lands at the next prompt; SESSION_TITLE=<slug> here is how the coordinator
knows it is handled and never prints a relaunch instruction. Kickoff is the right
place for it because the slug is born here, and a name that has to be requested by
hand is a name that gets forgotten.

It also prints PLUGIN_ROOT=<abs>. The plugin's own agents reach their role files
through ${CLAUDE_PLUGIN_ROOT}, but the reviewer briefs go to subagent types the
plugin does not own (`code-review`, `performance-engineer`), and a subagent prompt
is not a shell — a `${...}` in one arrives literally. So the coordinator gets the
resolved path here, in the call it already makes, rather than guessing at one.
"""
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import paths
import session_title
from prune_runs import prune


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:40].rstrip("-")) or "task"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    repo = Path(argv[0]).resolve()
    if not repo.is_dir():
        print(f"not a directory: {repo}")
        return 2
    slug = slugify(argv[1])
    task_file = None
    if "--task-file" in argv:
        task_file = Path(argv[argv.index("--task-file") + 1])
    for p in prune(dry_run=False):
        print(f"pruned {p.relative_to(paths.runs_dir())}")
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    repo_dir = paths.runs_dir() / repo.name
    run_dir = repo_dir / f"{stamp}-{slug}"
    n = 2
    while run_dir.exists():
        run_dir = repo_dir / f"{stamp}-{slug}-{n}"
        n += 1
    run_dir.mkdir(parents=True)
    (run_dir / "repo.txt").write_text(f"{repo}\n")
    if task_file is not None:
        shutil.copyfile(task_file, run_dir / "task.md")
    print(f"RUN_DIR={run_dir}")
    print(f"PLUGIN_ROOT={paths.plugin_root()}")
    requested = session_title.request(
        os.environ.get("CLAUDE_CODE_SESSION_ID", ""), slug
    )
    if requested is not None:
        print(f"SESSION_TITLE={slug}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
