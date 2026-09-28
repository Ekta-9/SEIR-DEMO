"""Pre-change feature rows for change cases.

Features are produced by `build_git_evidence` — the *same* function the live
service uses — and then flattened into columns. Computing training features
with different code than serving features ("training/serving skew") is a
classic silent ML bug; sharing one code path rules it out.
"""

import math

from app.collectors.git_history import GitHistoryIndex, build_git_evidence
from app.config import Settings
from app.dataset.cases import CandidateCase
from app.schema import Availability, ChangeAction

GIT_FEATURES = (
    "recent_commit_count",
    "historical_commit_count",
    "days_since_last_change",
    "unique_contributors",
    "lines_added",
    "lines_deleted",
    "total_churn",
    "churn_ratio",
    "co_change_count",
)
FEATURE_PREFIX = "git_"
ACTION_FEATURE = "action_is_delete"


class LeakageError(AssertionError):
    """A feature was computed from information at or after the change."""


def git_feature_row(index: GitHistoryIndex, case: CandidateCase, settings: Settings) -> dict:
    # Guard: the change commit itself must be invisible to its own features.
    visible = index.features(case.target_component_id, case.as_of).touches
    if any(t.sha == case.commit_sha or t.timestamp >= case.as_of for t in visible):
        raise LeakageError(f"{case.case_id}: features can see the change or later commits")

    items = build_git_evidence(index, [case.target_component_id], case.repo_id, case.parent_sha,
                               case.as_of, settings)
    row: dict = {ACTION_FEATURE: int(case.action is ChangeAction.DELETE)}
    for item in items:
        # Unknown stays unknown: NaN (which tree models handle), never 0.
        value = item.value if item.availability is Availability.AVAILABLE else math.nan
        row[f"{FEATURE_PREFIX}{item.evidence_type}"] = float(value)
    return row


def feature_columns() -> list[str]:
    return [ACTION_FEATURE, *(f"{FEATURE_PREFIX}{name}" for name in GIT_FEATURES)]
