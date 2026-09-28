"""ChangeCase — one training/evaluation example for the risk model.

A case is a real historical change to a target component. Features come from
evidence computed `as_of` the change (strictly before it); the label comes
from what happened at and after the change. Keeping those two time zones
separate is the main defence against data leakage.
"""

from pydantic import Field, model_validator

from app.schema.common import (
    COMMIT_SHA_PATTERN,
    COMPONENT_ID_PATTERN,
    REPO_ID_PATTERN,
    SCHEMA_VERSION,
    ChangeAction,
    ContractModel,
    RiskClass,
    UtcDatetime,
)


class ChangeCase(ContractModel):
    case_id: str
    schema_version: str = SCHEMA_VERSION
    repo_id: str = Field(pattern=REPO_ID_PATTERN)
    commit_sha: str = Field(pattern=COMMIT_SHA_PATTERN, description="The change being labelled")
    parent_sha: str = Field(pattern=COMMIT_SHA_PATTERN, description="Pre-change snapshot used for features")
    as_of: UtcDatetime = Field(description="Feature cutoff: the change commit's timestamp")
    target_component_id: str = Field(pattern=COMPONENT_ID_PATTERN)
    action: ChangeAction

    # --- ground truth (post-change information; never used as a feature) ---
    impacted_component_ids: list[str] = Field(
        default_factory=list, description="Other components that actually had to change"
    )
    fix_commit_shas: list[str] = Field(
        default_factory=list, description="Follow-up fix commits linked to this change"
    )
    label: RiskClass | None = Field(default=None, description="None until the labelling rules are applied")
    label_rule_version: str | None = Field(default=None, examples=["labels@1.0"])

    @model_validator(mode="after")
    def _label_needs_rule_version(self) -> "ChangeCase":
        if self.label is not None and self.label_rule_version is None:
            raise ValueError("a labelled case must record which label_rule_version produced it")
        if self.target_component_id in self.impacted_component_ids:
            raise ValueError("the target itself must not appear in impacted_component_ids")
        return self
