"""Mine candidate change cases from history.

A case = one *production* component that existed before a commit and was
modified or deleted by it. Every rejected candidate is counted under a named
exclusion reason so the dataset report can document what was dropped and why.
"""

import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.collectors.git_history import GitHistoryIndex
from app.collectors.git_log import CommitRecord, FileChange, attribute_changes
from app.config import Settings
from app.dataset.commit_filters import is_cosmetic
from app.git_cli import run_git_piped
from app.ids import is_test_path
from app.schema import ChangeAction

# Exclusion reasons (stable strings: they appear in the quality report).
ROOT_COMMIT = "root_commit"
DUPLICATE_COMMIT = "duplicate_commit"
BULK_COMMIT = "bulk_commit"
COSMETIC_COMMIT = "cosmetic_commit"
CENSORED = "censored_recent_change"
NEW_COMPONENT = "new_component"


@dataclass(frozen=True)
class CandidateCase:
    repo_id: str
    commit_sha: str
    parent_sha: str
    as_of: datetime  # the change's commit time; features use only data strictly before it
    target_component_id: str
    target_parent_path: str  # where the target lived *before* the change
    action: ChangeAction
    impacted: tuple[str, ...]  # other existing production components changed in the same commit
    impacted_test_count: int

    @property
    def case_id(self) -> str:
        return f"{self.repo_id}@{self.commit_sha[:12]}:{self.target_component_id}"


SAMPLED_OUT = "sampled_out_repo_cap"


def sample_by_commit(cases: list[CandidateCase], max_cases: int, seed: int) -> list[CandidateCase]:
    """Keep at most `max_cases`, choosing WHOLE commits at random across the entire
    history (so one large repository cannot dominate training, while the time
    spread — needed for chronological splits — is preserved). Deterministic."""
    if len(cases) <= max_cases:
        return cases
    by_commit: dict[str, int] = Counter(c.commit_sha for c in cases)
    commits = sorted(by_commit)  # stable order before shuffling -> reproducible
    random.Random(seed).shuffle(commits)
    kept, total = set(), 0
    for sha in commits:
        if total + by_commit[sha] <= max_cases:
            kept.add(sha)
            total += by_commit[sha]
    return [c for c in cases if c.commit_sha in kept]


def find_duplicate_commits(repo_dir: Path, snapshot: str, timeout: int) -> set[str]:
    """Cherry-picked copies of the same patch: keep the oldest, return the rest.

    `git patch-id` fingerprints a diff independent of line numbers and commit
    metadata, which is exactly how git itself recognizes cherry-picks.
    """
    raw = run_git_piped(
        repo_dir,
        ["log", snapshot, "--full-history", "--no-merges", "--reverse", "-p", "--", "*.java"],
        ["patch-id", "--stable"],
        timeout=timeout,
    )
    seen: set[str] = set()
    duplicates: set[str] = set()
    for line in raw.splitlines():  # oldest first because of --reverse
        patch_id, sha = line.split()
        if patch_id in seen:
            duplicates.add(sha)
        seen.add(patch_id)
    return duplicates


def _commit_exclusion(commit: CommitRecord, duplicates: set[str], censor_from: datetime,
                      settings: Settings) -> str | None:
    if commit.parent is None:
        return ROOT_COMMIT
    if commit.sha in duplicates:
        return DUPLICATE_COMMIT
    if len(commit.files) > settings.bulk_commit_file_threshold:
        return BULK_COMMIT
    if is_cosmetic(commit.subject):
        return COSMETIC_COMMIT
    if commit.timestamp >= censor_from:
        return CENSORED
    return None


def mine_cases(
    commits: list[CommitRecord],
    index: GitHistoryIndex,
    path_to_component: dict[str, str],
    repo_id: str,
    censor_from: datetime,
    duplicates: set[str],
    settings: Settings,
) -> tuple[list[CandidateCase], Counter]:
    changes_by_commit: dict[str, dict[str, list[FileChange]]] = defaultdict(lambda: defaultdict(list))
    for commit, change, component_id in attribute_changes(commits, path_to_component):
        changes_by_commit[commit.sha][component_id].append(change)

    cases: list[CandidateCase] = []
    excluded: Counter = Counter()
    for commit in commits:
        by_component = changes_by_commit.get(commit.sha)
        if not by_component:
            continue
        production = {c for c, chs in by_component.items() if not all(is_test_path(ch.path) for ch in chs)}
        existing = {c for c in production if index.is_alive(c, commit.timestamp)}
        excluded[NEW_COMPONENT] += len(production - existing)
        if not existing:
            continue

        reason = _commit_exclusion(commit, duplicates, censor_from, settings)
        if reason:
            excluded[reason] += len(existing)
            continue

        test_count = len(by_component) - len(production)
        for target in sorted(existing):
            target_changes = by_component[target]
            deleted = all(ch.is_file_deletion for ch in target_changes)
            first = target_changes[0]
            cases.append(CandidateCase(
                repo_id=repo_id,
                commit_sha=commit.sha,
                parent_sha=commit.parent,
                as_of=commit.timestamp,
                target_component_id=target,
                target_parent_path=first.old_path or first.path,
                action=ChangeAction.DELETE if deleted else ChangeAction.MODIFY,
                impacted=tuple(sorted(existing - {target})),
                impacted_test_count=test_count,
            ))
    return cases, excluded
