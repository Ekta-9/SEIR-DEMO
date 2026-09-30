"""The shared evidence -> features conversion must behave identically for the
dataset builder (EvidenceItem objects) and the live predictor (JSON dicts)."""

import json
import math
from datetime import datetime, timezone

import pytest

from app.collectors.config_files import ComponentResolver, build_config_evidence, scan_revision
from app.collectors.git_history import GitHistoryIndex, build_git_evidence
from app.collectors.git_log import read_history
from app.config import Settings
from app.inventory import list_components
from app.schema import EVIDENCE_TYPES, EvidenceItem, Source
from seir_features import (
    ACTION_FEATURE,
    FEATURE_COLUMNS,
    MULTI_VALUED_EVIDENCE_TYPES,
    FeatureError,
    column_name,
    evidence_to_features,
    to_vector,
)
from app.schema.evidence import MULTI_VALUED_EVIDENCE_TYPES as SCHEMA_MULTI_VALUED
from tests.git_repo_builder import GitRepoBuilder, java

BASE = dict(repo_id="acme/shop", snapshot="a" * 40, component_id="com.shop.Pay",
            as_of="2024-01-01T00:00:00Z", extraction_method="t@0")


def item(**fields) -> EvidenceItem:
    return EvidenceItem(**{**BASE, **fields})


def test_columns_match_the_evidence_registry():
    """seir_features is dependency-free, so its column list is written out; this
    test keeps it in sync with the schema's evidence-type registry."""
    expected = [column_name(source.value, t) for source in (Source.GIT, Source.CONFIG)
                for t in sorted(EVIDENCE_TYPES[source]) if t not in SCHEMA_MULTI_VALUED]
    assert list(FEATURE_COLUMNS) == [ACTION_FEATURE, *expected]
    assert MULTI_VALUED_EVIDENCE_TYPES == SCHEMA_MULTI_VALUED


def test_unknown_and_missing_are_nan_multi_valued_skipped():
    row = evidence_to_features([
        item(source="CONFIG", evidence_type="config_reference", value="RUNTIME", availability="AVAILABLE",
             provenance={"files": [{"path": "a.xml", "line": 1}]}),
        item(source="CONFIG", evidence_type="config_reference_count", value=1, availability="AVAILABLE",
             provenance={"note": "n"}),
        item(source="GIT", evidence_type="churn_ratio", availability="UNKNOWN"),
    ], action="MODIFY")
    assert set(row) == set(FEATURE_COLUMNS)  # every column always present
    assert row["config_config_reference_count"] == 1.0
    assert math.isnan(row["git_churn_ratio"])  # unknown is not zero
    assert math.isnan(row["git_recent_commit_count"])  # no evidence at all -> unknown


@pytest.mark.parametrize(("action", "expected"), [("DELETE", 1.0), ("MODIFY", 0.0), ("DEPRECATE", 0.0)])
def test_action(action, expected):
    assert evidence_to_features([], action)[ACTION_FEATURE] == expected


def test_rejects_mixed_components_and_conflicts():
    a = item(source="GIT", evidence_type="recent_commit_count", value=1, availability="AVAILABLE",
             provenance={"note": "n"})
    other = EvidenceItem(**{**BASE, "component_id": "com.shop.Other"}, source="GIT",
                         evidence_type="recent_commit_count", value=1, availability="AVAILABLE",
                         provenance={"note": "n"})
    with pytest.raises(FeatureError, match="mixes components"):
        evidence_to_features([a, other], "MODIFY")
    conflicting = item(source="GIT", evidence_type="recent_commit_count", value=5, availability="AVAILABLE",
                       as_of="2024-02-01T00:00:00Z", provenance={"note": "n"})
    with pytest.raises(FeatureError, match="conflicting"):
        evidence_to_features([a, conflicting], "MODIFY")


def test_to_vector_order():
    row = {c: float(i) for i, c in enumerate(FEATURE_COLUMNS)}
    assert to_vector(row) == [float(i) for i in range(len(FEATURE_COLUMNS))]


def test_json_route_equals_object_route_on_a_real_repository(tmp_path):
    """Training builds features from EvidenceItem objects; the live predictor gets
    JSON from the Evidence Service. Both must give byte-identical vectors."""
    repo = GitRepoBuilder(tmp_path / "repo")
    repo.write("src/main/java/com/acme/Handler.java", java("com.acme", "Handler"))
    repo.write("src/main/resources/app.xml", '<beans><bean class="com.acme.Handler"/></beans>\n')
    repo.commit("add", datetime(2024, 1, 1, tzinfo=timezone.utc))
    repo.write("src/main/java/com/acme/Handler.java", java("com.acme", "Handler", "  int x;\n"))
    snapshot = repo.commit("edit", datetime(2024, 3, 1, tzinfo=timezone.utc))

    settings = Settings()
    components = list_components(repo.path, "acme/shop", snapshot)
    index = GitHistoryIndex.build(read_history(repo.path, snapshot),
                                  {c.file_path: c.component_id for c in components}, settings)
    as_of = datetime(2024, 4, 1, tzinfo=timezone.utc)
    evidence = build_git_evidence(index, ["com.acme.Handler"], "acme/shop", snapshot, as_of, settings)
    evidence += build_config_evidence(scan_revision(repo.path, snapshot, ComponentResolver(["com.acme.Handler"])),
                                      ["com.acme.Handler"], "acme/shop", snapshot, as_of)

    from_objects = to_vector(evidence_to_features(evidence, "DELETE"))
    as_json = json.loads(json.dumps([e.model_dump(mode="json") for e in evidence]))  # what the API sends
    from_json = to_vector(evidence_to_features(as_json, "DELETE"))
    assert from_json == from_objects
    assert from_objects[FEATURE_COLUMNS.index("git_historical_commit_count")] == 2.0
    assert from_objects[FEATURE_COLUMNS.index("config_config_reference_count")] == 1.0
