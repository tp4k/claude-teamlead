#!/usr/bin/env python3
"""Run a generated teamlead review package through a fresh sandboxed Codex session."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import zlib
from pathlib import Path
from typing import NamedTuple


REPO_RE = re.compile(r"^- Repo / worktree: `(.+)`$", re.MULTILINE)
SHARED_REF_WARNING = "WARNING: a worktree-shared ref moved during the review"
SHARED_CONFIG_WARNING = "WARNING: worktree-shared repository config changed"
SHARED_REFLOG_WARNING = "WARNING: a worktree-shared reflog changed"
SHARED_HOOK_WARNING = "WARNING: a worktree-shared repository hook changed"
SHARED_OBJECT_WARNING = "WARNING: worktree-shared object storage changed"
SHARED_STATE_WARNING = "WARNING: worktree-shared repository state changed"
# Every warning about state the repository shares with its linked worktrees, as
# opposed to an escape from the disposable checkout's filesystem. Both places
# that need to tell those apart read this one tuple, so a surface added to the
# list above cannot be classified as an escape by being forgotten in one of them.
SHARED_WARNINGS = (
    SHARED_REF_WARNING,
    SHARED_CONFIG_WARNING,
    SHARED_REFLOG_WARNING,
    SHARED_HOOK_WARNING,
    SHARED_OBJECT_WARNING,
    SHARED_STATE_WARNING,
)


class Fail(Exception):
    pass


class TreeState(NamedTuple):
    """One snapshot of everything a review could disturb without being seen.

    `head`, `entries` and `staged` are the original checkout's own state:
    `staged` is the logical content `git ls-files --stage` reports (mode and
    blob OID per path), not the raw index file, so a `git checkout` that only
    rewrites the on-disk stat cache leaves it unchanged. `shared` is the
    *repository* — the git common directory, which every linked worktree
    shares, so changing any of it needs no escape from the disposable checkout
    at all. `object_ids` is the set of object IDs this repository's own object
    store serves — local loose objects plus local pack indexes, not a store
    reached through `objects/info/alternates` — which is what changes when
    history is genuinely lost from that store; a semantics-preserving repack
    moves objects between loose and packed storage without shrinking this set.

    `shared` is the detector and is byte-exact, except for `objects/`: storage
    layout a repack rewrites is excluded entirely, and a loose object is
    excluded too as long as its bytes still hash to its own name — content
    addressing already vouches for it, and `object_ids` is what notices when it
    stops existing. `config` is not a second detector: it is the decoded
    `--local` config kept only so a warning can name the key that moved,
    because `core.hooksPath` and the `alias.*` entries decide what later
    commands in this repository execute and "something changed" is not enough
    to act on. Decoding cannot be injective — git accepts values that are not
    UTF-8, and two distinct byte strings can decode to the same replacement
    character — which is exactly why it renders and never decides.
    """

    head: str
    entries: dict[str, str]
    shared: dict[str, str]
    config: dict[str, list[str]]
    object_ids: frozenset[str]
    staged: dict[str, str]


def resolve_codex() -> str:
    configured = os.environ.get("CODEX_BIN", "").strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_file() or not os.access(path, os.X_OK):
            raise Fail(f"CODEX_BIN is not executable: {path}")
        return str(path.resolve())
    discovered = shutil.which("codex")
    if not discovered:
        raise Fail("Codex CLI not found. Install it, then run `codex login`.")
    return discovered


def require_login(codex: str) -> None:
    status = subprocess.run(
        [codex, "login", "status"],
        capture_output=True,
        text=True,
    )
    if status.returncode == 0:
        return
    detail = (status.stderr or status.stdout).strip()
    if detail:
        print(detail, file=sys.stderr)
    raise Fail(
        "Codex authentication is unavailable. Run `codex login` for ChatGPT "
        "access, then retry. An API key is not required."
    )


def repo_from_prompt(prompt: str) -> Path:
    match = REPO_RE.search(prompt)
    if not match:
        raise Fail("PROMPT.md does not contain a `Repo / worktree` entry.")
    repo = Path(match.group(1)).expanduser().resolve()
    if not repo.is_dir():
        raise Fail(f"review repository does not exist: {repo}")
    check = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if check.returncode != 0:
        raise Fail(f"review repository is not a git worktree: {repo}")
    return repo


def next_artifacts(directory: Path, stem: str = "codex-review") -> tuple[Path, Path]:
    """The next free `<stem>-rN.md` / `.jsonl` pair in `directory`.

    The stem is a parameter because a run can now send Codex two different
    things: the plan, before anything is built, and the diff, after. Both land
    beside their own prompt, and sharing one stem would make the plan review of
    round 1 and the code review of round 1 the same filename — with the second
    silently becoming `r2` and every later reader mis-attributing it.
    """
    round_number = 1
    while True:
        review = directory / f"{stem}-r{round_number}.md"
        events = directory / f"{stem}-r{round_number}.jsonl"
        if not review.exists() and not events.exists():
            return review, events
        round_number += 1


def summarize_event(line: str) -> str | None:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    event_type = event.get("type")
    if event_type == "thread.started":
        thread_id = event.get("thread_id")
        return f"Codex thread: {thread_id}" if thread_id else "Codex thread started."
    if event_type == "turn.started":
        return "Codex review started."
    if event_type in {"turn.failed", "error"}:
        message = event.get("message") or event.get("error") or "unknown error"
        return f"Codex reported {event_type}: {message}"
    return None


# Permission bits `stat.S_IMODE()` would return, kept as a mask because the
# common-directory walk below already binds the name `stat` to `path.stat()`.
MODE_BITS_MASK = 0o7777

# Storage layout a semantics-preserving `git repack -ad` rewrites without
# changing which objects the repository can serve. Never digested: digesting
# it would fail every repack with a false "deleted" alarm for content that
# only moved.
DERIVED_OBJECT_PREFIXES = ("objects/pack/", "objects/info/commit-graphs/")
DERIVED_OBJECT_FILES = ("objects/info/packs", "objects/info/commit-graph")
# A loose object's path is its own hash split after two hex characters. sha1
# names are 40 hex characters total, sha256 names are 64.
LOOSE_OBJECT_RE = re.compile(r"^objects/([0-9a-f]{2})/([0-9a-f]{38}|[0-9a-f]{62})$")
# `git repack` (without `-n`) always runs `update-server-info` and writes this
# cache of the current refs for the dumb-HTTP transport, whether or not any
# ref moved. `refs/` and `packed-refs` are the authoritative signal for a ref
# move; a plain repack regenerating this mirror of them is the same false
# "deleted"/"created" alarm F1 is about, one directory up from `objects/`.
DERIVED_STATE_FILES = ("info/refs",)
# Read size for both streaming decompression of a loose object and hashing any
# common-directory file — the shape `corpus_ab.py:READ_CHUNK_BYTES` already
# sets, so neither one holds a whole file in memory at once.
LOOSE_READ_CHUNK_BYTES = 1 << 16
# Bounds the inflated size `is_valid_loose_object` will hold in memory.
# Deflate's maximum expansion ratio is 1032:1, so an unbounded inflate of a
# crafted ~10 MB compressed stream written under `.git/objects/` -- a path
# the sandboxed reviewer can create, which is the entire reason this detector
# exists -- would allocate roughly 10 GB in one shot. Exceeding this cap
# returns `False` from `is_valid_loose_object`, which is fail-closed and
# raises no false alarm: the path then falls through to the digest branch
# beside that check, which only warns when the two snapshots' bytes differ.
LOOSE_OBJECT_MAX_BYTES = 1 << 30


def is_derived_object_layout(name: str) -> bool:
    """A path under `objects/` that records layout, not object identity."""
    return name.startswith(DERIVED_OBJECT_PREFIXES) or name in DERIVED_OBJECT_FILES


def loose_object_oid(name: str) -> str | None:
    """The object ID a loose-object path claims to be, or `None` if it is not one."""
    match = LOOSE_OBJECT_RE.match(name)
    return None if match is None else match.group(1) + match.group(2)


def is_valid_loose_object(path: Path, oid: str) -> bool:
    """A loose object is content-addressed only while its bytes hash to `oid`.

    `objects/info/alternates` and a bit-flipped loose object are both paths
    under `objects/` that are not content-addressed, so they need this check
    rather than the size-only shortcut valid loose objects get.

    Streamed through a bounded `zlib.decompressobj()` rather than
    `zlib.decompress(path.read_bytes())`: reading the whole compressed file
    and materialising the whole inflated object at once made peak memory
    proportional to a value the sandboxed reviewer controls. Each call bounds
    its own output to `LOOSE_READ_CHUNK_BYTES` via `max_length`, feeding any
    leftover `unconsumed_tail` back in before more of the file is read, and
    the running inflated-byte count is checked against `LOOSE_OBJECT_MAX_BYTES`
    after every chunk.
    """
    algorithm = hashlib.sha1 if len(oid) == 40 else hashlib.sha256
    digest = algorithm()
    decompressor = zlib.decompressobj()
    inflated_total = 0
    try:
        with path.open("rb") as handle:
            pending = b""
            while True:
                data = pending or handle.read(LOOSE_READ_CHUNK_BYTES)
                if not data:
                    break
                inflated = decompressor.decompress(data, LOOSE_READ_CHUNK_BYTES)
                inflated_total += len(inflated)
                if inflated_total > LOOSE_OBJECT_MAX_BYTES:
                    return False
                digest.update(inflated)
                pending = decompressor.unconsumed_tail
            tail = decompressor.flush()
            inflated_total += len(tail)
            if inflated_total > LOOSE_OBJECT_MAX_BYTES:
                return False
            digest.update(tail)
            if not decompressor.eof:
                return False
            # Bytes appended after the zlib stream land in `unused_data`, not
            # `unconsumed_tail`, so they never reach `digest.update()` above —
            # a loose object with trailing garbage still hashed correct.
            if decompressor.unused_data:
                return False
    except (OSError, zlib.error):
        return False
    return digest.hexdigest() == oid


def pack_index_oids(repo: Path, common: Path) -> set[str]:
    """Object IDs packed into `common`'s own local packs, read via `git show-index`.

    Only `common / "objects" / "pack"` is walked — never a path reached through
    `objects/info/alternates` — so a pack that lives only in a borrowed
    alternate store contributes nothing here. `git show-index` takes a pack
    `.idx` on stdin, one local pack at a time (`git show-index -h`); there is
    no flag to point it at several packs, or at an alternate store, at once.
    """
    oids: set[str] = set()
    pack_dir = common / "objects" / "pack"
    if not pack_dir.is_dir():
        return oids
    for index_path in sorted(pack_dir.glob("*.idx")):
        # is_file() specifically: open() on a FIFO blocks in the kernel and
        # never raises, so except OSError below cannot catch that input, and
        # no test here can exercise it without hanging this synchronous suite.
        if not index_path.is_file():
            continue
        if not index_path.with_suffix(".pack").is_file():
            continue
        try:
            with index_path.open("rb") as handle:
                listed = subprocess.run(
                    ["git", "-C", str(repo), "show-index"],
                    stdin=handle,
                    capture_output=True,
                    text=True,
                )
        except OSError:
            continue
        for line in listed.stdout.splitlines():
            fields = line.split()
            if len(fields) >= 2:
                oids.add(fields[1])
    return oids


def sha256_of(path: Path) -> str:
    """Hash `path` in fixed-size chunks rather than holding it whole in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(LOOSE_READ_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_status_paths(raw: bytes) -> dict[str, str]:
    """Decode `git status --porcelain -z -uall` bytes into path -> status code.

    Decoded with `os.fsdecode` (surrogateescape) rather than `errors="replace"`:
    replace maps every undecodable byte onto the same U+FFFD, so two distinct
    non-UTF-8 filenames compare equal and the digest keyed on one of them is
    never computed for the other. Surrogateescape is injective on POSIX.
    """
    paths: dict[str, str] = {}
    fields = raw.split(b"\0")
    index = 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        if len(entry) < 4:
            continue
        code = entry[:2].decode("ascii")
        path = os.fsdecode(entry[3:])
        if code[0] in "RC":
            # `-z` splits a rename or copy across two fields, destination
            # first, origin second — and the origin no longer exists on disk.
            index += 1
        paths[path] = code
    return paths


def tree_state(repo: Path) -> TreeState:
    """HEAD, dirty content, and the repository state a review could disturb.

    The status line alone is not the state. A file that was already `` M`` before
    the review is still `` M`` after the review rewrites it, so comparing status
    lines reports nothing — which is exactly the case that matters, because the
    file a teamlead run leaves uncommitted is the one deliverable with no other
    copy. Hashing each dirty path is what makes an overwrite visible.

    The status is read with `-z` because the default output *quotes* any path
    holding a space or a non-ASCII byte, octal-escaping the latter, and a quoted
    path does not exist on disk — so it read as `-` on both sides and
    the overwrite it was meant to catch was invisible. `-z` emits the real bytes,
    which also removes the `old -> new` spelling that made renames a special case.

    The repository shared by every linked worktree is snapshotted as the bytes of
    the files in its common directory, rather than as an inventory of the
    surfaces somebody thought to name. Four successive reviews of this function
    each found one more surface the previous one had missed — remote-tracking
    refs, then all of `refs/`, then `--local` config, then reflogs — and the one
    after that found hooks and the object database. Enumeration was the defect:
    every surface not on the list was invisible, so the list could only ever be
    as complete as the last person's imagination. Reading the directory inverts
    that. A surface nobody has thought of yet is reported by default, and what
    stays quiet is what genuinely did not change.

    Two consequences worth keeping in mind:

    - It is byte-exact, so it does not care whether a value decodes. `git config`
      accepts values that are not UTF-8, and the previous snapshot decoded with
      `errors="replace"`, which mapped the distinct values `0x80` and `0x81` onto
      the same replacement character and compared equal.
    - `objects/` is split by what it means rather than by path: a valid loose
      object's path *is* the hash of its content, so it is skipped and left to
      `object_ids`; storage layout a repack rewrites (`objects/pack/`,
      `objects/info/packs`, `objects/info/commit-graph*`) is skipped too,
      because none of it changes which objects the repository can serve.
      Everything else under `objects/` — `objects/info/alternates`, a loose
      object whose bytes no longer hash to its own name, anything not yet
      anticipated — is digested like any other file, because it is mutable
      metadata or corruption, not content-addressed storage.
    - `staged` is read separately as the logical content `git ls-files --stage`
      reports (mode and blob OID per path) rather than excluded: that is what
      `head` and `entries` do not capture, because they see the worktree, and a
      pure rewrite of the on-disk index file touches neither.
    - `info/refs`, the dumb-HTTP mirror `update-server-info` rewrites on every
      plain `git repack`, is skipped the same way: `refs/` and `packed-refs`
      already are the authoritative signal for a moved ref.
    - Every remaining file also records the mode bits `chmod` can flip, because
      `hooks/pre-commit` executing is a filesystem property a byte digest alone
      cannot see.
    """
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain", "-z", "-uall"],
        capture_output=True,
    ).stdout
    entries: dict[str, str] = {}
    for path, code in parse_status_paths(status).items():
        target = repo / path
        try:
            digest = hashlib.sha256(target.read_bytes()).hexdigest()[:12]
        except OSError:
            digest = "-"
        entries[path] = f"{code} {digest}"
    index_output = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "--stage", "-z"],
        capture_output=True,
    ).stdout
    staged: dict[str, str] = {}
    for record in index_output.split(b"\0"):
        if not record:
            continue
        # `mode oid stage\tpath` — the mode and OID are the logical content a
        # pure rewrite of the on-disk index (a `git checkout` stat-cache
        # refresh) does not touch, which is the property this projection needs.
        # Decoded as bytes, like `parse_status_paths` above: a tracked path can
        # be non-UTF-8, and `text=True` raised `UnicodeDecodeError` on one.
        #
        # A path is not a unique index key on its own: an unresolved conflict
        # carries stages 1-3 at once, and `git ls-files --stage` already emits
        # them in ascending stage order for one path. Every stage's record is
        # kept, joined by a newline no fixed-shape `mode oid stage` record can
        # contain, so the join stays injective and a change to any one stage
        # is visible.
        meta, separator, path = record.partition(b"\t")
        if separator:
            key = os.fsdecode(path)
            entry = meta.decode("ascii")
            previous = staged.get(key)
            staged[key] = entry if previous is None else f"{previous}\n{entry}"
    common_output = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    # `--git-common-dir` is the point of the whole exercise: from a linked
    # worktree it names the ORIGINAL repository rather than that worktree's
    # private directory, which is precisely why changing it needs no escape. It
    # is answered relative to the repository when it is inside it (`.git`).
    common = Path(common_output) if common_output else repo / ".git"
    if not common.is_absolute():
        common = repo / common
    shared: dict[str, str] = {}
    # Every loose object's OID, gathered from this same walk rather than a
    # second directory pass — regardless of `is_valid_loose_object` below,
    # because the set this feeds is "what a path under `objects/` claims to
    # be", the same thing `cat-file --batch-all-objects` would have listed.
    loose_oids: set[str] = set()
    for path in sorted(common.rglob("*")):
        name = str(path.relative_to(common))
        if name == "index":
            # Read separately above as `staged`, a logical projection rather
            # than these raw bytes: the stat cache that lives in this file
            # changes on a plain `git checkout` with no staged or worktree
            # content moving, which is exactly the duplicate warning that
            # projection exists to avoid.
            continue
        if name in DERIVED_STATE_FILES:
            continue
        if path.is_symlink():
            # Recorded without following it: the interesting change is where the
            # link points, and following one out of the repository would hash
            # something this snapshot does not own.
            shared[name] = f"symlink {os.readlink(path)}"
            continue
        try:
            if not path.is_file():
                continue
            if name.startswith("objects/"):
                if is_derived_object_layout(name):
                    continue
                oid = loose_object_oid(name)
                if oid is not None:
                    loose_oids.add(oid)
                    if is_valid_loose_object(path, oid):
                        # Content-addressed and valid: `object_ids` is what
                        # notices if it later stops existing.
                        continue
            stat = path.stat()
            mode = f"{stat.st_mode & MODE_BITS_MASK:04o}"
            # Chunked, not `path.read_bytes()`: an over-cap or invalid object
            # falls through from the branch above and must not be
            # materialised whole here either, on top of the failed attempt
            # `is_valid_loose_object` already streamed through.
            digest = sha256_of(path)[:12]
            shared[name] = f"{mode} {stat.st_size} {digest}"
        except OSError:
            # A file that vanishes mid-walk, or that this process may not read,
            # is recorded as unreadable rather than skipped: skipping it would
            # make it identical to absent, and "the review made this unreadable"
            # is a difference worth a warning.
            shared[name] = "unreadable"
    # Local-only: loose OIDs come from this repository's own `objects/??/`
    # directories, gathered above, and packed OIDs from this repository's own
    # `objects/pack/*.idx` files, read below. Neither source follows
    # `objects/info/alternates`, so a change inside a borrowed alternate store
    # never reaches this set — only a change to the pointer file itself does,
    # and that is still caught by the byte-digest branch above.
    object_ids = frozenset(loose_oids | pack_index_oids(repo, common))
    config_output = subprocess.run(
        ["git", "-C", str(repo), "config", "--list", "--local", "-z"],
        capture_output=True,
        text=True,
        errors="replace",
    ).stdout
    config: dict[str, list[str]] = {}
    for record in config_output.split("\0"):
        if not record:
            continue
        # `-z` spells one entry `key\nvalue`, and a value may itself hold
        # newlines, so the split is on the FIRST one only. A key can legitimately
        # repeat — `remote.origin.fetch` usually does — so repeats accumulate
        # into a list rather than overwriting, which keeps two records from
        # rendering as one value that happens to contain a newline.
        #
        # This is the rendering, not the detection: see `TreeState`. The file's
        # own bytes are already in `shared`, so a change this decoding cannot
        # represent is still caught — it simply gets a less specific message.
        key, separator, value = record.partition("\n")
        if separator:
            config.setdefault(key, []).append(value)
    return TreeState(head, entries, shared, config, object_ids, staged)


def config_values(values: list[str] | None) -> str:
    """Render one config key's values so two records never read as one.

    The whole point of keeping repeats as a list is that `first\\nsecond` and
    `first` + `second` are different states; printing them with the same join
    they are no longer stored with would hide that difference again at the last
    step, in the one line a human actually reads.
    """
    if values is None:
        return "absent"
    return ", ".join(repr(value) for value in values)


def shared_label(path: str) -> tuple[str, str]:
    """Which warning a changed common-directory path deserves, and what to call it.

    The path is mostly self-describing — `refs/heads/main` and `hooks/pre-commit`
    each name the thing that moved — so only `config`, which is one opaque file
    holding every key, needs a separate rendering. The catch-all at the bottom is
    the part that makes this bounded: a file nobody anticipated still produces a
    warning naming it, instead of nothing.
    """
    if path == "config":
        return SHARED_CONFIG_WARNING, path
    if path.startswith("hooks/"):
        return SHARED_HOOK_WARNING, path
    if path.startswith("logs/"):
        return SHARED_REFLOG_WARNING, path[len("logs/"):] or path
    if path.startswith("refs/") or path == "packed-refs":
        return SHARED_REF_WARNING, path
    if path.startswith("objects/"):
        return SHARED_OBJECT_WARNING, path
    return SHARED_STATE_WARNING, path


def config_detail(before: TreeState, after: TreeState) -> list[str]:
    """Name the config keys that moved, or say plainly that none can be named.

    The empty case is not a non-event. It means the file's bytes changed while
    every decoded value stayed equal, which is what a value git accepts but UTF-8
    cannot represent looks like from here — so it is reported as exactly that,
    rather than as a silence that would read as a false alarm.
    """
    details = []
    for key in sorted(set(before.config) | set(after.config)):
        old_values = before.config.get(key)
        new_values = after.config.get(key)
        if old_values != new_values:
            details.append(
                f"{key}: {config_values(old_values)} -> {config_values(new_values)}"
            )
    if not details:
        details.append(
            "the file changed but every decoded value is unchanged — compare "
            "`git config --list --local` against a copy, the difference is in "
            "bytes this listing cannot show"
        )
    return details


def tree_warnings(
    before: TreeState,
    after: TreeState,
    isolated: bool = False,
) -> list[str]:
    """Expose filesystem escapes and movement in worktree-shared repository state.

    Dirty content is compared by DIFFERENCE, never by emptiness, because a run's
    own deliverables are legitimately dirty before review. Shared state needs its
    own warnings: a linked worktree shares the whole git common directory, so
    refs, config, reflogs, hooks and the object database can all change without
    any escape from the disposable checkout's filesystem — real changes to the
    source repository, but not isolation failures, and saying "isolation escaped"
    about them would teach the reader to discount the message that means it.
    """
    warnings = []
    escape = "review isolation escaped — " if isolated else ""
    if before.head and after.head and before.head != after.head:
        warnings.append(
            f"WARNING: {escape}HEAD moved during the review: "
            f"{before.head[:12]} -> {after.head[:12]}"
        )
    for path in sorted(set(after.entries) - set(before.entries)):
        warnings.append(
            f"WARNING: {escape}the review created or changed: {path}"
        )
    for path in sorted(set(before.entries) - set(after.entries)):
        warnings.append(
            f"WARNING: {escape}a change present before the review is gone: {path}"
        )
    for path in sorted(set(before.entries) & set(after.entries)):
        if before.entries[path] != after.entries[path]:
            warnings.append(
                f"WARNING: {escape}the review rewrote an already-uncommitted "
                f"file: {path}"
            )
    for path in sorted(set(before.staged) | set(after.staged)):
        # `before.staged`/`after.staged` hold mode and blob OID, not the raw
        # index file, so a `git checkout` that only refreshes the stat cache
        # leaves this loop silent — the duplicate warning that exclusion used
        # to prevent is now prevented by comparing the right thing instead.
        if before.staged.get(path) != after.staged.get(path):
            warnings.append(
                f"WARNING: {escape}a staged-only change moved independently "
                f"of the worktree: {path}"
            )
    for path in sorted(set(before.shared) | set(after.shared)):
        # The runner's own disposable checkout is created after the first
        # snapshot and removed before the second, so its `worktrees/<name>/`
        # administration files are in neither and need no filtering. One that
        # does appear belongs to a worktree somebody else is using, which is
        # worth saying rather than hiding.
        old = before.shared.get(path)
        new = after.shared.get(path)
        if old == new:
            continue
        label, name = shared_label(path)
        if path == "config":
            details = config_detail(before, after)
            warnings += [f"{label}: {detail}" for detail in details]
        elif old is None:
            warnings.append(f"{label}: {name}: created during the review")
        elif new is None:
            warnings.append(f"{label}: {name}: deleted during the review")
        else:
            warnings.append(f"{label}: {name}: {old} -> {new}")
    for oid in sorted(before.object_ids - after.object_ids):
        # Storage layout (loose vs. packed) is deliberately not part of this
        # comparison, so a semantics-preserving repack that keeps every object
        # ID reports nothing here. A name lost from this set is an object this
        # repository's own store held before and does not hold now, however it
        # was stored.
        warnings.append(
            f"{SHARED_OBJECT_WARNING}: objects/{oid[:2]}/{oid[2:]}: "
            "deleted during the review"
        )
    for oid in sorted(after.object_ids - before.object_ids):
        # The mirror image of the loop above: valid loose objects are skipped
        # from `shared` entirely (see `TreeState`), so an object genuinely
        # added to the store during the review would otherwise produce no
        # warning of any kind.
        warnings.append(
            f"{SHARED_OBJECT_WARNING}: objects/{oid[:2]}/{oid[2:]}: "
            "created during the review"
        )
    return warnings


BACKUP_MAX_FILES = 500
BACKUP_MAX_BYTES = 50 * 1024 * 1024


def backup_worktree(repo: Path, dest: Path) -> tuple[Path | None, list[str]]:
    """Preserve uncommitted work before granting a reviewer write-plus-network.

    The snapshot both populates the disposable checkout and protects the source
    if isolation setup fails or is escaped. Detecting a write afterwards is no
    consolation for a file with no other copy, so tracked changes become a patch
    and untracked files are copied whole. Committed history needs no backup: it
    is already in git, and `tree_warnings` reports a moved HEAD separately.
    """
    notes: list[str] = []
    diff = subprocess.run(
        ["git", "-C", str(repo), "diff", "HEAD", "--binary"],
        capture_output=True,
        text=True,
    )
    if diff.returncode != 0:
        detail = (diff.stderr or diff.stdout).strip()
        raise Fail(
            "could not snapshot tracked changes: "
            f"{detail or f'git exited {diff.returncode}'}"
        )
    others = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "--others", "--exclude-standard", "-z"],
        capture_output=True,
        text=True,
    )
    if others.returncode != 0:
        detail = (others.stderr or others.stdout).strip()
        raise Fail(
            "could not list untracked files: "
            f"{detail or f'git exited {others.returncode}'}"
        )
    untracked = [name for name in others.stdout.split("\0") if name]
    if not diff.stdout and not untracked:
        # A clean tree still has to clear `dest`. Leaving the previous review's
        # backup standing let `main()` adopt it — it decides by `is_dir()`, so a
        # stale directory reads as "this run's backup" and would be offered as
        # recovery for work it does not contain.
        if dest.is_dir():
            shutil.rmtree(dest)
        return None, notes
    if dest.is_dir():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    if diff.stdout:
        (dest / "pre-review.patch").write_text(diff.stdout, encoding="utf-8")
    copied = 0
    total = 0
    for name in untracked:
        src = repo / name
        if not src.is_file() or src.is_symlink():
            # A symlink is not followed and a socket or fifo cannot be copied,
            # but silence here contradicted the promise that untracked work is
            # preserved. Say which path went uncopied so the omission is visible
            # while the tree can still be saved by hand.
            notes.append(
                f"WARNING: pre-review backup skipped `{name}` — it is a symlink "
                "or not a regular file, and was not copied"
            )
            continue
        size = src.stat().st_size
        if copied >= BACKUP_MAX_FILES or total + size > BACKUP_MAX_BYTES:
            notes.append(
                f"WARNING: pre-review backup is incomplete — stopped after "
                f"{copied} untracked file(s); `{name}` and any after it were not "
                f"copied"
            )
            break
        target = dest / "untracked" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
        copied += 1
        total += size
    return dest, notes


def remove_review_tree(repo: Path, dest: Path) -> list[str]:
    """Drop the disposable checkout so contained writes and git locks die together.

    A forced worktree removal intentionally discards anything the reviewer wrote.
    Pruning afterwards clears administrative debris, while a failure is returned
    with the path because silently leaking a linked checkout blocks the next run.
    """
    notes: list[str] = []
    try:
        removed = subprocess.run(
            ["git", "-C", str(repo), "worktree", "remove", "--force", str(dest)],
            capture_output=True,
            text=True,
        )
        if removed.returncode != 0:
            detail = (removed.stderr or removed.stdout).strip()
            notes.append(
                f"WARNING: could not remove review worktree at {dest}: "
                f"{detail or f'git exited {removed.returncode}'}"
            )
    except OSError as exc:
        notes.append(f"WARNING: could not remove review worktree at {dest}: {exc}")
    try:
        pruned = subprocess.run(
            ["git", "-C", str(repo), "worktree", "prune"],
            capture_output=True,
            text=True,
        )
        if pruned.returncode != 0:
            detail = (pruned.stderr or pruned.stdout).strip()
            notes.append(
                f"WARNING: could not prune review worktrees after removing {dest}: "
                f"{detail or f'git exited {pruned.returncode}'}"
            )
    except OSError as exc:
        notes.append(
            f"WARNING: could not prune review worktrees after removing {dest}: {exc}"
        )
    return notes


def prepare_review_tree(repo: Path, dest: Path) -> tuple[Path | None, list[str]]:
    """Give a networked reviewer equivalent content without exposing real work.

    The recovery backup is deliberately the source for tracked and untracked
    changes: one snapshot both preserves the user's only copy and populates the
    detached checkout. A partially registered worktree is removed.

    Returning `None` means the review must not run as a networked one — the
    caller refuses rather than falling back to the live tree. That used to be the
    other way round, on the reasoning that some review beats no review; it is the
    wrong trade when the fallback is a networked agent with write access to the
    repository being reviewed, and `--no-network` already covers the case.
    """
    notes: list[str] = []
    added = False
    try:
        repo = repo.resolve()
        resolved_dest = dest.resolve()
        if resolved_dest == repo or repo in resolved_dest.parents:
            return None, [
                "WARNING: review worktree must be outside the source repository: "
                f"{dest}"
            ]
        backup, backup_notes = backup_worktree(
            repo, dest.parent / "pre-review-tree"
        )
        notes += backup_notes
        created = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "worktree",
                "add",
                "--detach",
                str(dest),
                "HEAD",
            ],
            capture_output=True,
            text=True,
        )
        if created.returncode != 0:
            detail = (created.stderr or created.stdout).strip()
            notes.append(
                f"WARNING: could not prepare isolated review worktree at {dest}: "
                f"{detail or f'git exited {created.returncode}'}"
            )
            return None, notes
        added = True

        if backup is not None:
            patch = backup / "pre-review.patch"
            if patch.is_file():
                applied = subprocess.run(
                    ["git", "-C", str(dest), "apply", str(patch)],
                    capture_output=True,
                    text=True,
                )
                if applied.returncode != 0:
                    detail = (applied.stderr or applied.stdout).strip()
                    raise Fail(
                        "could not apply the pre-review patch: "
                        f"{detail or f'git exited {applied.returncode}'}"
                    )
            untracked = backup / "untracked"
            if untracked.is_dir():
                for source in sorted(untracked.rglob("*")):
                    if not source.is_file():
                        continue
                    target = dest / source.relative_to(untracked)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
        return dest, notes
    except (Fail, OSError) as exc:
        notes.append(
            f"WARNING: could not prepare isolated review worktree at {dest}: {exc}"
        )
        if added:
            notes += remove_review_tree(repo, dest)
        return None, notes


def prompt_for_review_tree(prompt: str, repo: Path) -> str:
    """Keep the reviewer from silently following the readable live-repo path.

    Only the repository declaration changes; all task context remains byte-for-byte
    identical so isolation cannot accidentally alter what the reviewer is grading.
    """
    return REPO_RE.sub(
        lambda match: f"- Repo / worktree: `{repo}`", prompt, count=1
    )


def codex_command(codex: str, repo: Path, review: Path, network: bool) -> list[str]:
    """The `codex exec` argv, kept separate so it can be asserted without a model call.

    `read-only` is the only mode with no network, and `workspace-write` is the
    only one with any: measured on codex-cli 0.154.0, `network_access=true`
    under `read-only` changes nothing, and `sandbox_read_only` is not a config
    table at all. So the reviewer gets `gh` or it gets an unwritable tree; it
    cannot have both, and the pairing below is not a preference to be split.
    """
    command = [codex, "exec", "-C", str(repo)]
    if network:
        command += [
            "--sandbox",
            "workspace-write",
            "-c",
            "sandbox_workspace_write.network_access=true",
        ]
    else:
        command += ["--sandbox", "read-only"]
    return command + ["--json", "--output-last-message", str(review), "-"]


def run_review(
    codex: str,
    repo: Path,
    prompt: str,
    review: Path,
    events: Path,
    timeout_minutes: float,
    network: bool,
) -> int:
    command = codex_command(codex, repo, review, network)
    with events.open("w", encoding="utf-8") as event_file:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        assert process.stdin is not None
        assert process.stdout is not None
        timed_out = threading.Event()

        def kill_on_deadline() -> None:
            timed_out.set()
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        watchdog = threading.Timer(timeout_minutes * 60, kill_on_deadline)
        watchdog.daemon = True
        watchdog.start()
        try:
            process.stdin.write(prompt)
            process.stdin.close()
            for line in process.stdout:
                event_file.write(line)
                event_file.flush()
                summary = summarize_event(line)
                if summary:
                    print(summary, file=sys.stderr, flush=True)
            status = process.wait()
        finally:
            watchdog.cancel()
        if timed_out.is_set():
            raise Fail(
                f"Codex review exceeded {timeout_minutes:g} minutes and was killed. "
                f"Events retained at {events}"
            )
        return status


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", help="absolute path to generated PROMPT.md")
    parser.add_argument(
        "--timeout-minutes",
        type=float,
        default=30,
        help="kill Codex and fail if the review runs longer than this (default: 30)",
    )
    parser.add_argument(
        "--artifact-stem",
        default="codex-review",
        help=(
            "basename for the review and event files, before `-rN` "
            "(default: codex-review; a plan review passes codex-plan-review)"
        ),
    )
    parser.add_argument(
        "--no-network",
        action="store_true",
        help=(
            "run under the hard read-only sandbox instead: nothing in the repo "
            "is writable, and `gh`, CI status and any other network check are "
            "unavailable to the reviewer"
        ),
    )
    args = parser.parse_args(argv)
    if args.timeout_minutes <= 0:
        raise Fail("--timeout-minutes must be positive")

    prompt_path = Path(args.prompt).expanduser().resolve()
    if not prompt_path.is_file():
        raise Fail(f"review prompt not found: {prompt_path}")
    prompt = prompt_path.read_text(encoding="utf-8", errors="replace")
    repo = repo_from_prompt(prompt)
    codex = resolve_codex()
    require_login(codex)
    stem = args.artifact_stem
    if not stem or "/" in stem or stem != stem.strip():
        raise Fail("--artifact-stem must be a bare filename stem")
    review_path, events_path = next_artifacts(prompt_path.parent, stem)

    network = not args.no_network
    before = tree_state(repo)
    backup: Path | None = None
    review_tree: Path | None = None
    warnings: list[str] = []
    try:
        review_repo = repo
        review_prompt = prompt
        if network:
            review_tree, notes = prepare_review_tree(
                repo, prompt_path.parent / "review-tree"
            )
            warnings += notes
            backup_path = prompt_path.parent / "pre-review-tree"
            backup = backup_path if backup_path.is_dir() else None
            if review_tree is None:
                # Refusing is the point of this path, not a regression from it.
                # A networked review runs `workspace-write` with the network on,
                # and the disposable checkout is the only thing between that and
                # the user's real tree. Continuing would hand a networked agent
                # write access to the repository under review while saying so in
                # one lowercase `warning:` line nobody reads — the exact outcome
                # the isolation exists to prevent. `--no-network` is the way to
                # review a tree that cannot be isolated.
                raise Fail(
                    "could not isolate the review, and refused to run a networked "
                    "review against the live repository. Re-run with --no-network "
                    "to review in the read-only sandbox instead."
                )
            review_repo = review_tree
            review_prompt = prompt_for_review_tree(prompt, review_tree)
        status = run_review(
            codex,
            review_repo,
            review_prompt,
            review_path,
            events_path,
            args.timeout_minutes,
            network,
        )
        if status != 0:
            raise Fail(
                f"Codex review failed with exit code {status}. Events retained at "
                f"{events_path}"
            )
        if not review_path.is_file() or not review_path.read_text(
            errors="replace"
        ).strip():
            raise Fail(
                "Codex exited successfully without a final review. Events retained "
                f"at {events_path}"
            )
    finally:
        if network:
            if review_tree is not None:
                warnings += remove_review_tree(repo, review_tree)
            try:
                changes = tree_warnings(
                    before, tree_state(repo), isolated=review_tree is not None
                )
            except (OSError, ValueError) as exc:
                # `ValueError` alongside `OSError`: a non-UTF-8 tracked or
                # status path used to raise `UnicodeDecodeError` here, which
                # is a `ValueError`, aborting this `finally` before any
                # already-accumulated warning below was ever printed.
                changes = [
                    "WARNING: could not compare the original worktree after the "
                    f"review: {exc}"
                ]
            warnings += changes
            worktree_changed = any(
                not warning.startswith(SHARED_WARNINGS)
                for warning in changes
            )
            if worktree_changed and backup is not None:
                warnings.append(
                    "WARNING: the worktree as it stood before the review is saved "
                    f"at {backup} — compare it before accepting any change above"
                )
            for warning in warnings:
                print(warning, file=sys.stderr)

    print(f"review  : {review_path}")
    print(f"events  : {events_path}")
    print(f"sandbox : {'workspace-write, network on' if network else 'read-only'}")
    if backup is not None:
        print(f"pre-tree: {backup}")
    # Warnings already went to stderr above, on both the success and the failure
    # path. Printing them again here would double every line the skill is told to
    # relay verbatim, which reads as twice as many tree modifications as occurred.
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Fail as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
