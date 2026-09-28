"""SEIR shared contracts. Import models from here, not from submodules."""

from app.schema.change_case import ChangeCase
from app.schema.common import (
    SCHEMA_VERSION,
    Availability,
    ChangeAction,
    ComponentKind,
    EdgeType,
    RiskClass,
    RuntimeCoverage,
    Source,
    TimeWindow,
)
from app.schema.component import Component, DependencyEdge
from app.schema.evidence import EVIDENCE_TYPES, EvidenceItem, FileLocation, Provenance
from app.schema.explanation import Explanation, GroundedClaim
from app.schema.risk import FeatureContribution, RiskAssessment

# Contracts exported to JSON Schema for the non-Python modules.
EXPORTED_CONTRACTS = {
    "component": Component,
    "dependency_edge": DependencyEdge,
    "evidence_item": EvidenceItem,
    "change_case": ChangeCase,
    "risk_assessment": RiskAssessment,
    "explanation": Explanation,
}

__all__ = [
    "SCHEMA_VERSION",
    "EXPORTED_CONTRACTS",
    "EVIDENCE_TYPES",
    "Availability",
    "ChangeAction",
    "ChangeCase",
    "Component",
    "ComponentKind",
    "DependencyEdge",
    "EdgeType",
    "EvidenceItem",
    "Explanation",
    "FeatureContribution",
    "FileLocation",
    "GroundedClaim",
    "Provenance",
    "RiskAssessment",
    "RiskClass",
    "RuntimeCoverage",
    "Source",
    "TimeWindow",
]
