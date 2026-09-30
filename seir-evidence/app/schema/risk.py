"""RiskAssessment — output of the ML risk model (Member 3).

How `top_features[].contribution` is read (agreed 2026-09-30, "predicted class"):
the attribution is computed for the PREDICTED class (`risk_class`), e.g. the SHAP
value of that class's score. Positive = pushes the prediction towards
`risk_class`; negative = pushes away from it. The explainer phrases it by class:
  HIGH   -> positive "raises the risk",          negative "lowers the risk"
  LOW    -> positive "keeps the risk low",        negative "points to higher risk"
  MEDIUM -> positive "supports a medium rating",  negative "argues against a medium rating"
"""

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
    feature: str = Field(description="Exact feature column name (seir_features.FEATURE_COLUMNS)",
                         examples=["git_recent_commit_count"])
    value: float | int | bool | str | None
    contribution: float = Field(
        description="Signed attribution (e.g. SHAP) for the PREDICTED class: positive pushes the "
                    "prediction towards risk_class, negative pushes away from it"
    )


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
    feature_spec_version: str | None = Field(
        default=None, description="seir_features.FEATURE_SPEC_VERSION the model was trained with",
        examples=["features@1.0"],
    )

    @model_validator(mode="after")
    def _scores_are_a_distribution(self) -> "RiskAssessment":
        if any(not 0.0 <= score <= 1.0 for score in self.class_scores.values()):
            raise ValueError("class_scores must lie in [0, 1]")
        if self.class_scores and abs(sum(self.class_scores.values()) - 1.0) > PROBABILITY_SUM_TOLERANCE:
            raise ValueError("class_scores must sum to 1")
        return self
