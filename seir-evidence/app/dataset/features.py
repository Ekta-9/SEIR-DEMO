"""Pre-change feature rows for change cases.

Evidence is produced by the *same* functions the live service uses
(`build_git_evidence`, `build_config_evidence`) and turned into columns by
`seir_features.evidence_to_features` — the one shared conversion that the
risk predictor (Member 3) also uses at prediction time. Computing training
features with different code than serving features ("training/serving skew")
is a classic silent ML bug; one code path rules it out.
"""

from app.collectors.git_history import GitHistoryIndex, build_git_evidence
from app.config import Settings
from app.dataset.cases import CandidateCase
from app.schema import EvidenceItem
from seir_features import FEATURE_COLUMNS, FEATURE_SPEC_VERSION, evidence_to_features

__all__ = ["FEATURE_SPEC_VERSION", "LeakageError", "feature_columns", "feature_row"]


class LeakageError(AssertionError):
    """A feature was computed from information at or after the change."""


def feature_row(index: GitHistoryIndex, case: CandidateCase, config_items: list[EvidenceItem],
                settings: Settings) -> dict[str, float]:
    # Guard: the change commit itself must be invisible to its own features.
    visible = index.features(case.target_component_id, case.as_of).touches
    if any(t.sha == case.commit_sha or t.timestamp >= case.as_of for t in visible):
        raise LeakageError(f"{case.case_id}: features can see the change or later commits")

    git_items = build_git_evidence(index, [case.target_component_id], case.repo_id, case.parent_sha,
                                   case.as_of, settings)
    return evidence_to_features(git_items + config_items, case.action)


def feature_columns() -> list[str]:
    return list(FEATURE_COLUMNS)
