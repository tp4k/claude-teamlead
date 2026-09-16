#!/usr/bin/env python3
"""Reproducible before/after corpus check for review_package.py's plan
classifier:  python3 scripts/corpus_ab.py --before <old> --after <new>
--manifest <manifest>

F8 found that the round-6 corpus calibration was recorded as a number with no
manifest, which made the 174-vs-178 discrepancy unresolvable and the whole
figure worthless as evidence. This script takes the manifest as an argument
instead of recalling a count: it hashes every entry, refuses if one no longer
matches (the corpus moved underneath the measurement), and reports which
plans, by path, flip between "structured" and "not structured" when
`missing_plan_sections`'s caller (`plan_is_structured`) is evaluated by the
`--before` and `--after` revisions of review_package.py in turn.

The plans referenced by a manifest live under `$TEAMLEAD_HOME/runs`, which
`prune_runs.py` deletes by age policy — so a manifest entry vanishing between
being written and being re-run is expected, not a fault. A vanished entry is
refused by default, same as a changed one, but `--allow-missing` re-runs over
the survivors and labels the result a partial re-run instead of silently
measuring a smaller corpus with no record that anything was dropped.

No pytest dependency — the skill's scripts run with bare python3.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

# Arbitrary streaming read size for sha256 — large enough that a run of a few
# hundred small plan.md files does not do one read() per file, small enough
# that hashing never has to hold a whole file in memory at once.
READ_CHUNK_BYTES = 1 << 16
MANIFEST_FIELD_SEP = "  "


class CorpusRefused(Exception):
    """The corpus cannot be measured as recorded; the message says why."""


def load_module(name: str, path: Path) -> ModuleType:
    """Load `path` as a module named `name`, without touching `sys.path`.

    The same in-process mechanism `test_run_codex_review.py:40-44` uses: a
    plain `import` here would have to follow a `sys.path` edit, which is the
    E402 the house linter refuses to have silenced.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(READ_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_manifest(path: Path) -> list[tuple[str, Path]]:
    """One `(sha256, path)` pair per non-blank manifest line.

    A manifest that cannot be read — absent, unreadable, or containing
    bytes that are not valid text — raises `CorpusRefused` rather than
    letting the underlying error propagate out of `main` as a traceback.
    """
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError) as exc:
        raise CorpusRefused(f"cannot read manifest {path}: {exc}") from exc
    entries: list[tuple[str, Path]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        digest, _, rest = line.partition(MANIFEST_FIELD_SEP)
        entries.append((digest, Path(rest)))
    return entries


def resolve_corpus(
    manifest: list[tuple[str, Path]], allow_missing: bool
) -> tuple[list[Path], int]:
    """The plan files to measure, and how many manifest entries have vanished.

    A sha256 mismatch is always a hard refusal — the corpus moved underneath
    the measurement, and continuing would silently measure a different corpus
    than the one the manifest describes. A vanished file is refused by
    default too, and only `--allow-missing` continues over the survivors,
    because refusing outright on any absence would make the harness
    unrunnable within weeks of being written (the corpus lives under a
    directory pruned by age).

    A corpus with nothing left to measure is refused too, by one of two
    distinct messages: an empty manifest never had entries, while an
    `--allow-missing` re-run whose every entry vanished did — "0 entries"
    and "N entries, all missing" are different facts a reader can act on
    differently, so neither is allowed to read as a silent zero-drift pass.
    """
    if not manifest:
        raise CorpusRefused(
            "manifest lists no entries to measure; refusing an empty corpus "
            "rather than reporting a vacuous zero-drift pass"
        )
    present: list[Path] = []
    missing = 0
    for digest, file_path in manifest:
        if not file_path.is_file():
            missing += 1
            continue
        actual = sha256_of(file_path)
        if actual != digest:
            raise CorpusRefused(
                f"manifest entry changed on disk, refusing: {file_path} "
                f"(expected sha256 {digest}, got {actual})"
            )
        present.append(file_path)
    if missing and not allow_missing:
        noun = "entry is" if missing == 1 else "entries are"
        raise CorpusRefused(
            f"{missing} manifest {noun} missing on disk; pass --allow-missing "
            "to measure the survivors as a partial re-run"
        )
    if not present:
        noun = "entry" if missing == 1 else "entries"
        raise CorpusRefused(
            f"all {missing} manifest {noun} missing on disk; no survivors "
            "left to measure after --allow-missing"
        )
    return present, missing


def drift(
    before: ModuleType, after: ModuleType, plans: list[Path]
) -> tuple[list[Path], list[Path]]:
    """Plans whose `plan_is_structured` verdict changed between modules."""
    newly_rejected: list[Path] = []
    newly_accepted: list[Path] = []
    for plan_path in plans:
        text = plan_path.read_text(errors="replace")
        was = before.plan_is_structured(text)
        now = after.plan_is_structured(text)
        if was and not now:
            newly_rejected.append(plan_path)
        elif not was and now:
            newly_accepted.append(plan_path)
    return newly_rejected, newly_accepted


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare two revisions of review_package.py's plan classifier "
            "over a recorded, reproducible corpus of plan.md files."
        )
    )
    parser.add_argument(
        "--before", required=True, type=Path, help="the baseline review_package.py"
    )
    parser.add_argument(
        "--after", required=True, type=Path, help="the candidate review_package.py"
    )
    parser.add_argument(
        "--manifest",
        required=True,
        type=Path,
        help="a `<sha256><two spaces><absolute path>` per line list of plan.md files",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="measure the survivors when manifest entries have vanished, "
        "instead of refusing outright",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = read_manifest(args.manifest)
        plans, missing = resolve_corpus(manifest, args.allow_missing)
    except CorpusRefused as exc:
        print(str(exc), file=sys.stderr)
        return 1

    before = load_module("review_package_before", args.before)
    after = load_module("review_package_after", args.after)
    newly_rejected, newly_accepted = drift(before, after, plans)

    if missing:
        noun = "entry is" if missing == 1 else "entries are"
        print(
            f"partial re-run: {missing} manifest {noun} missing; "
            f"measuring the {len(plans)} survivors"
        )
    print(f"corpus size: {len(plans)}")
    print(f"newly rejected: {len(newly_rejected)}")
    for path in newly_rejected:
        print(f"  {path}")
    print(f"newly accepted: {len(newly_accepted)}")
    for path in newly_accepted:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
