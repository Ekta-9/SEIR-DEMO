"""RiskAssessment — output of the ML risk model (Member 3)."""

from pydantic import Field, model_validator

from app.schema.common import (
    COMPONENT_ID_PATTERN,
    REPO_ID_PATTERN,
    ChangeAction,
    ContractModel,
    RiskClass,
)

PROBABILITY_SUM_TOLERANCE = 1e-3


class FeatureContribution(ContractModel):
    feature: str = Field(examples=["recent_commit_count"])
    value: float | int | bool | str | None
    contribution: float = Field(description="Signed attribution (e.g. SHAP); positive pushes risk up")


class RiskAssessment(ContractModel):
    repo_id: str = Field(pattern=REPO_ID_PATTERN)
    component_id: str = Field(pattern=COMPONENT_ID_PATTERN)
    action: ChangeAction
    risk_class: RiskClass
    class_scores: dict[RiskClass, float] = Field(description="Per-class score in [0, 1], summing to 1")
    is_calibrated: bool = Field(
        description="True only if scores were calibrated and may be read as probabilities (report §14.5)"
    )
    top_features: list[FeatureContribution] = Field(default_factory=list)
    model_version: str = Field(examples=["xgb-risk@0.1.0"])

    @model_validator(mode="after")
    def _scores_are_a_distribution(self) -> "RiskAssessment":
        if any(not 0.0 <= score <= 1.0 for score in self.class_scores.values()):
            raise ValueError("class_scores must lie in [0, 1]")
        if self.class_scores and abs(sum(self.class_scores.values()) - 1.0) > PROBABILITY_SUM_TOLERANCE:
            raise ValueError("class_scores must sum to 1")
        return self
