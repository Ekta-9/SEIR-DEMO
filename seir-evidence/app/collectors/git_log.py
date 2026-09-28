"""Read a repository's history in one `git log` pass and attribute every file
change to a component — following renames so history is not lost when a
class is moved or renamed (report RQ-D1).
"""

from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from app.git_cli import run_git
from app.ids import path_to_component_id

RECORD_SEPARATOR = "\x1e"
FIELD_SEPARATOR = "\x1f"
# %H full sha, %ct committer time (when the change landed on the branch),
# %aE author email (mailmap-aware), %P parent shas, %s subject line (last: may contain anything)
LOG_FORMAT = FIELD_SEPARATOR.join(("%H", "%ct", "%aE", "%P", "%s"))
LOG_FORMAT = f"{RECORD_SEPARATOR}{LOG_FORMAT}"
JAVA_PATHSPEC = "*.java"


@dataclass(frozen=True)
class FileChange:
    path: str  # path after the commit
    old_path: str | None  # set only for renames
    added: int  # 0 for binary files, where git reports "-"
    deleted: int
    is_file_deletion: bool = False  # the commit removed this file


@dataclass(frozen=True)
class CommitRecord:
    sha: str
    timestamp: datetime
    author: str
    files: tuple[FileChange, ...]
    parent: str | None = None  # first parent; None for a root commit
    subject: str = ""


def _to_int(value: str) -> int:
    return 0 if value == "-" else int(value)


def parse_log(raw: str) -> list[CommitRecord]:
    """Parse `git log --numstat -z` output produced with LOG_FORMAT.

    With -z, each numstat entry is "added\\tdeleted\\tpath\\0"; for a rename the
    path is empty and the old and new paths follow as two extra \\0 tokens.
    """
    commits = []
    for chunk in raw.split(RECORD_SEPARATOR):
        if not chunk.strip():
            continue
        header, _, body = chunk.partition("\0")
        sha, timestamp, author, parents, subject = header.split(FIELD_SEPARATOR, 4)
        tokens = iter(body.split("\0"))
        files = []
        for token in tokens:
            token = token.lstrip("\n")
            if not token:
                continue
            added, deleted, path = token.split("\t", 2)
            old_path = None
            if not path:  # rename: old and new paths are the next two tokens
                old_path, path = next(tokens), next(tokens)
            files.append(FileChange(path, old_path, _to_int(added), _to_int(deleted)))
        commits.append(
            CommitRecord(
                sha=sha,
                timestamp=datetime.fromtimestamp(int(timestamp), tz=timezone.utc),
                author=author.strip().lower(),
                files=tuple(files),
                parent=parents.split()[0] if parents.strip() else None,
                subject=subject.strip(),
            )
        )
    return commits


def parse_deletions(raw: str) -> dict[str, frozenset[str]]:
    """Parse `git log --diff-filter=D --name-only -z --format=%x1e%H` output."""
    deletions = {}
    for chunk in raw.split(RECORD_SEPARATOR):
        if not chunk.strip():
            continue
        sha, _, body = chunk.partition("\0")
        deletions[sha] = frozenset(p.lstrip("\n") for p in body.split("\0") if p.strip())
    return deletions


def read_history(repo_dir: Path, snapshot: str, timeout: int = 600) -> list[CommitRecord]:
    """All non-merge commits reachable from `snapshot` that touch Java files, newest first.

    Merge commits are skipped: their changes already appear in the merged
    commits, so counting them would double-count activity. Numstat does not
    say whether a file was deleted, so a second (cheap) pass lists deletions.

    `--full-history` is essential: with a pathspec, git otherwise prunes side
    branches at merges ("history simplification") and silently drops real
    commits from the log.
    """
    common = (snapshot, "--full-history", "--no-merges", "-M", "-z")
    raw = run_git(repo_dir, "log", *common, "--numstat", f"--format={LOG_FORMAT}", "--", JAVA_PATHSPEC,
                  timeout=timeout)
    raw_deletions = run_git(repo_dir, "log", *common, "--diff-filter=D", "--name-only",
                            f"--format={RECORD_SEPARATOR}%H", "--", JAVA_PATHSPEC, timeout=timeout)
    deletions = parse_deletions(raw_deletions)
    commits = parse_log(raw)
    return [_mark_deletions(c, deletions[c.sha]) if c.sha in deletions else c for c in commits]


def _mark_deletions(commit: CommitRecord, deleted_paths: frozenset[str]) -> CommitRecord:
    files = tuple(
        replace(f, is_file_deletion=f.old_path is None and f.path in deleted_paths) for f in commit.files
    )
    return replace(commit, files=files)


def _rename_targets(commits: list[CommitRecord]) -> dict[str, str]:
    """old_path -> new_path for every rename; the most recent rename wins."""
    targets: dict[str, str] = {}
    for commit in commits:  # newest first
        for change in commit.files:
            if change.old_path:
                targets.setdefault(change.old_path, change.path)
    return targets


def _follow_renames(path: str, targets: dict[str, str], live_paths: set[str]) -> str:
    seen = {path}
    while path in targets and path not in live_paths:
        path = targets[path]
        if path in seen:  # A -> B -> A rename cycle
            break
        seen.add(path)
    return path


def attribute_changes(
    commits: list[CommitRecord], path_to_component: dict[str, str]
) -> Iterator[tuple[CommitRecord, FileChange, str]]:
    """Yield (commit, change, component_id) for every Java file change.

    Walks history newest -> oldest. `lineage` maps a path as it existed at an
    older point in time to the path it eventually became, so a class renamed
    from A.java to B.java has all of A's history attributed to B's component.

    History is a DAG, not a line: a commit on a parallel branch can edit the
    old path *after* (by date) the rename happened on another branch. Such
    edits are not in `lineage` yet, so paths that no longer exist at the
    snapshot are additionally resolved through every rename ever recorded.
    Paths that still exist keep date-ordered resolution, because a path can
    be reused by an unrelated new file.

    Paths absent from `path_to_component` (deleted classes) fall back to a
    FQCN derived from the path.
    """
    targets = _rename_targets(commits)
    live_paths = set(path_to_component)
    lineage: dict[str, str] = {}
    for commit in commits:  # newest first
        for change in commit.files:
            if change.path in lineage:
                final_path = lineage[change.path]
            elif change.path in live_paths:
                final_path = change.path
            else:
                final_path = _follow_renames(change.path, targets, live_paths)
            if change.old_path:
                # Before this commit the file lived at old_path. Any *older*
                # history recorded under change.path belongs to a different file.
                lineage.pop(change.path, None)
                lineage[change.old_path] = final_path
            component_id = path_to_component.get(final_path) or path_to_component_id(final_path)
            if component_id:
                yield commit, change, component_id
