"""SZZ: find which past changes *caused* a later bug fix.

Algorithm (Sliwerski, Zimmermann & Zeller, 2005, with common refinements):
  1. A bug-fix commit F is identified from its subject (commit_filters).
  2. The lines F deleted or modified were the faulty lines.
  3. `git blame` on F's parent tells which commit last wrote each faulty line.
  4. That commit is "bug-inducing" for the component that owns the file.

Refinements: whitespace-only changes are ignored (`-w`), and blank lines,
comments and import statements are skipped — they cannot cause a bug.

Known limitation (standard for SZZ): fixes that only *add* lines leave no
faulty line to blame, so they cannot be traced to an inducing commit.
"""

import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.collectors.git_log import CommitRecord, attribute_changes
from app.config import Settings
from app.dataset.commit_filters import is_bug_fix
from app.git_cli import run_git
from app.ids import is_test_path

HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@")
BLAME_HEADER = re.compile(r"^([0-9a-f]{40}) \d+ \d+")
NON_CODE_PREFIXES = ("//", "/*", "*", "*/", "import ", "package ")

# (inducing commit sha, component id) -> fix commit shas
InducingMap = dict[tuple[str, str], set[str]]


def is_meaningful_line(content: str) -> bool:
    stripped = content.strip()
    return bool(stripped) and not stripped.startswith(NON_CODE_PREFIXES)


def faulty_lines(diff: str) -> list[int]:
    """Line numbers (in the parent version) that a -U0 diff deleted or modified."""
    lines: list[int] = []
    old_line = 0
    for row in diff.splitlines():
        header = HUNK_HEADER.match(row)
        if header:
            old_line = int(header.group(1))
            continue
        if row.startswith("-") and not row.startswith("---"):
            if is_meaningful_line(row[1:]):
                lines.append(old_line)
            old_line += 1
    return lines


def to_ranges(lines: list[int]) -> list[tuple[int, int]]:
    """[3,4,5,9] -> [(3,5),(9,9)] so blame runs once per contiguous block."""
    ranges: list[tuple[int, int]] = []
    for line in sorted(set(lines)):
        if ranges and line == ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], line)
        else:
            ranges.append((line, line))
    return ranges


def blame_commits(repo_dir: Path, revision: str, path: str, lines: list[int], timeout: int) -> set[str]:
    ranges = to_ranges(lines)
    if not ranges:
        return set()
    range_args = [arg for start, end in ranges for arg in ("-L", f"{start},{end}")]
    raw = run_git(repo_dir, "blame", "--porcelain", "-w", *range_args, revision, "--", path, timeout=timeout)
    return {m.group(1) for m in map(BLAME_HEADER.match, raw.splitlines()) if m}


def _trace_fix(repo_dir: Path, fix: CommitRecord, files: list[tuple[str, str, str]],
               timeout: int) -> list[tuple[str, str]]:
    """For one fix commit, return (inducing sha, component id) pairs."""
    found = []
    for parent_path, new_path, component_id in files:
        # Both paths in the pathspec: if the fix also renamed the file, git can
        # pair them as a rename instead of reporting "whole file deleted".
        diff = run_git(repo_dir, "diff", "-w", "-U0", "--no-color", "-M", fix.parent, fix.sha,
                       "--", *sorted({parent_path, new_path}), timeout=timeout)
        for inducing in blame_commits(repo_dir, fix.parent, parent_path, faulty_lines(diff), timeout):
            if inducing != fix.sha:
                found.append((inducing, component_id))
    return found


def find_bug_inducing(repo_dir: Path, commits: list[CommitRecord], path_to_component: dict[str, str],
                      settings: Settings) -> tuple[InducingMap, int]:
    """Return the inducing map and the number of bug-fix commits analysed."""
    files_per_fix: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    fixes = {
        c.sha: c for c in commits
        if c.parent and is_bug_fix(c.subject) and len(c.files) <= settings.bulk_commit_file_threshold
    }
    for commit, change, component_id in attribute_changes(commits, path_to_component):
        if commit.sha in fixes and not is_test_path(change.path):
            files_per_fix[commit.sha].append((change.old_path or change.path, change.path, component_id))

    inducing: InducingMap = defaultdict(set)
    with ThreadPoolExecutor(max_workers=settings.szz_workers) as pool:
        jobs = {
            sha: pool.submit(_trace_fix, repo_dir, fixes[sha], files, settings.git_timeout_seconds)
            for sha, files in files_per_fix.items()
        }
        for fix_sha, job in jobs.items():
            for key in job.result():
                inducing[key].add(fix_sha)
    return dict(inducing), len(files_per_fix)
