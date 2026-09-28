"""Explanation — output of the evidence-grounded explainer (Member 5).

Every claim must cite at least one evidence ID, which is what makes
hallucinations mechanically checkable (report §19).
"""

from pydantic import Field

from app.schema.common import COMPONENT_ID_PATTERN, ChangeAction, ContractModel


class GroundedClaim(ContractModel):
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class Explanation(ContractModel):
    component_id: str = Field(pattern=COMPONENT_ID_PATTERN)
    action: ChangeAction
    summary: str
    claims: list[GroundedClaim] = Field(default_factory=list)
    uncertainties: list[GroundedClaim] = Field(default_factory=list)
    recommendation: str
    checklist: list[str] = Field(default_factory=list)
    generator: str = Field(examples=["template@0.1.0", "ollama:llama3.1:8b"])
    validated: bool = Field(description="True once every claim passed the evidence checker")
