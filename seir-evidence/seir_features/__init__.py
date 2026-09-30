"""The ONE shared conversion from SEIR evidence to risk-model inputs.

Used by both sides of the model, so training and live prediction can never
compute features differently ("training/serving skew"):

  * the dataset builder (Member 5) -> training rows
  * the risk predictor (Member 3)  -> live feature vectors

Dependency-free on purpose: it accepts evidence as plain JSON dicts (as
returned by the Evidence Service) or as `EvidenceItem` objects, and needs
nothing but the Python standard library.

    from seir_features import FEATURE_COLUMNS, evidence_to_features, to_vector

    row = evidence_to_features(evidence_json_list, action="DELETE")
    x = to_vector(row)             # floats in FEATURE_COLUMNS order, NaN = unknown

Changing a column (adding STATIC/RUNTIME features, renaming...) bumps
FEATURE_SPEC_VERSION; datasets and trained models record the version they use.
"""

import math
from collections.abc import Iterable, Mapping
from typing import Any

FEATURE_SPEC_VERSION = "features@1.0"

ACTION_FEATURE = "action_is_delete"
# Evidence types that occur several times per component (e.g. one per config
# line). They are details for explanations, not model inputs.
MULTI_VALUED_EVIDENCE_TYPES = frozenset({"config_reference"})

# Ordered model inputs. Evidence columns follow the rule <source>_<evidence_type>.
FEATURE_COLUMNS: tuple[str, ...] = (
    ACTION_FEATURE,
    "git_churn_ratio",
    "git_co_change_count",
    "git_days_since_last_change",
    "git_historical_commit_count",
    "git_lines_added",
    "git_lines_deleted",
    "git_recent_commit_count",
    "git_total_churn",
    "git_unique_contributors",
    "config_config_reference_count",
)

# DEPRECATE has no training examples (history has no reliable deprecation
# signal); it is treated like MODIFY, i.e. the class is kept.
DELETE_ACTIONS = frozenset({"DELETE"})


class FeatureError(ValueError):
    """Evidence cannot be turned into one consistent feature row."""


def column_name(source: str, evidence_type: str) -> str:
    return f"{str(source).lower()}_{evidence_type}"


def _as_dict(item: Any) -> Mapping:
    if isinstance(item, Mapping):
        return item
    if hasattr(item, "model_dump"):  # pydantic EvidenceItem
        return item.model_dump(mode="json")
    raise FeatureError(f"unsupported evidence item type: {type(item).__name__}")


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def evidence_to_features(evidence: Iterable[Any], action: Any) -> dict[str, float]:
    """Evidence for ONE component + the proposed action -> {column: float}.

    Every column in FEATURE_COLUMNS is present. A column with no evidence, or
    evidence that is UNAVAILABLE/UNKNOWN, is NaN — never 0 ("unknown is not zero").
    Evidence types that are not model inputs (yet) are ignored.
    """
    row = {column: math.nan for column in FEATURE_COLUMNS}
    row[ACTION_FEATURE] = 1.0 if _enum_value(action) in DELETE_ACTIONS else 0.0

    component = None
    for raw in evidence:
        item = _as_dict(raw)
        if component is None:
            component = item["component_id"]
        elif item["component_id"] != component:
            raise FeatureError(f"evidence mixes components: {component} and {item['component_id']}")
        if item["evidence_type"] in MULTI_VALUED_EVIDENCE_TYPES:
            continue
        column = column_name(_enum_value(item["source"]), item["evidence_type"])
        if column not in row:
            continue
        value = math.nan if _enum_value(item["availability"]) != "AVAILABLE" else float(item["value"])
        previous = row[column]
        if not math.isnan(previous) and previous != value:
            raise FeatureError(f"conflicting values for {column}: {previous} vs {value}")
        row[column] = value
    return row


def to_vector(row: Mapping[str, float]) -> list[float]:
    """Feature row -> list in FEATURE_COLUMNS order (what the model is fed)."""
    missing = [c for c in FEATURE_COLUMNS if c not in row]
    if missing:
        raise FeatureError(f"row is missing columns: {missing}")
    return [float(row[c]) for c in FEATURE_COLUMNS]
