import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schema import EXPORTED_CONTRACTS, ChangeCase, Component, EvidenceItem, RiskAssessment

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "contracts" / "examples"
SHA = "a" * 40


def git_item(**overrides) -> dict:
    base = {
        "repo_id": "acme/shop",
        "snapshot": SHA,
        "component_id": "com.shop.payment.LegacyPaymentService",
        "source": "GIT",
        "evidence_type": "recent_commit_count",
        "value": 2,
        "availability": "AVAILABLE",
        "as_of": "2026-09-01T00:00:00Z",
        "provenance": {"commits": [SHA]},
        "extraction_method": "git_history@0.1.0",
    }
    return {**base, **overrides}


# ---- every example in /contracts/examples must stay valid -------------------

@pytest.mark.parametrize("name", EXPORTED_CONTRACTS)
def test_examples_validate(name):
    payload = json.loads((EXAMPLES_DIR / f"{name}.json").read_text(encoding="utf-8"))
    records = payload if isinstance(payload, list) else [payload]
    for record in records:
        EXPORTED_CONTRACTS[name].model_validate(record)


# ---- EvidenceItem rules ------------------------------------------------------

def test_evidence_id_is_filled_and_deterministic():
    first = EvidenceItem.model_validate(git_item())
    second = EvidenceItem.model_validate(git_item())
    assert first.evidence_id.startswith("ev_")
    assert first.evidence_id == second.evidence_id


def test_evidence_id_ignores_timestamp_format():
    as_string = EvidenceItem.model_validate(git_item(as_of="2026-09-01T00:00:00Z"))
    ist = timezone(timedelta(hours=5, minutes=30))
    as_datetime = EvidenceItem.model_validate(git_item(as_of=datetime(2026, 9, 1, 5, 30, tzinfo=ist)))
    assert as_string.evidence_id == as_datetime.evidence_id


def test_evidence_id_changes_with_cutoff():
    early = EvidenceItem.model_validate(git_item(as_of="2026-01-01T00:00:00Z"))
    late = EvidenceItem.model_validate(git_item(as_of="2026-09-01T00:00:00Z"))
    assert early.evidence_id != late.evidence_id


def test_unknown_is_not_zero():
    with pytest.raises(ValidationError, match="unknown is not zero"):
        EvidenceItem.model_validate(git_item(availability="UNKNOWN", value=0))


def test_available_requires_value():
    with pytest.raises(ValidationError, match="must carry a value"):
        EvidenceItem.model_validate(git_item(value=None))


def test_available_requires_provenance_or_window():
    with pytest.raises(ValidationError, match="provenance or an observation window"):
        EvidenceItem.model_validate(git_item(provenance={}))


def test_unregistered_evidence_type_rejected():
    with pytest.raises(ValidationError, match="not registered"):
        EvidenceItem.model_validate(git_item(evidence_type="commit_count"))


def test_naive_timestamp_rejected():
    with pytest.raises(ValidationError, match="timezone-aware"):
        EvidenceItem.model_validate(git_item(as_of="2026-09-01T00:00:00"))


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        EvidenceItem.model_validate(git_item(confidence=0.9))


# ---- other contracts ---------------------------------------------------------

def test_component_rejects_windows_path():
    with pytest.raises(ValidationError, match="'/' separators"):
        Component.model_validate({
            "component_id": "com.shop.Foo", "repo_id": "acme/shop", "snapshot": SHA,
            "simple_name": "Foo", "package": "com.shop", "kind": "CLASS",
            "file_path": "src\\main\\java\\com\\shop\\Foo.java",
        })


def test_short_sha_rejected():
    with pytest.raises(ValidationError):
        EvidenceItem.model_validate(git_item(snapshot="abc1234"))


def test_labelled_case_needs_rule_version():
    with pytest.raises(ValidationError, match="label_rule_version"):
        ChangeCase.model_validate({
            "case_id": "c1", "repo_id": "acme/shop", "commit_sha": SHA, "parent_sha": "b" * 40,
            "as_of": "2026-07-14T09:30:00Z", "target_component_id": "com.shop.Foo",
            "action": "MODIFY", "label": "HIGH",
        })


def test_risk_scores_must_sum_to_one():
    with pytest.raises(ValidationError, match="sum to 1"):
        RiskAssessment.model_validate({
            "repo_id": "acme/shop", "component_id": "com.shop.Foo", "action": "DELETE",
            "risk_class": "LOW", "class_scores": {"LOW": 0.9, "MEDIUM": 0.9, "HIGH": 0.1},
            "is_calibrated": False, "model_version": "m@0",
        })
