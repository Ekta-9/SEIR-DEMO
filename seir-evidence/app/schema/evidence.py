"""EvidenceItem — the one format every clue in SEIR is stored in.

Design rules enforced here (from the Data & Evolution report §8):
  * every item points to the raw observation that supports it (provenance);
  * "unknown" is never encoded as 0 — non-AVAILABLE items must have value=None;
  * every item states the cutoff time it was computed at (`as_of`), which is
    how pre-change features are kept free of future information.
"""

from typing import Any

from pydantic import Field, TypeAdapter, model_validator

from app.ids import make_evidence_id
from app.schema.common import (
    COMMIT_SHA_PATTERN,
    COMPONENT_ID_PATTERN,
    REPO_ID_PATTERN,
    SCHEMA_VERSION,
    Availability,
    ContractModel,
    Source,
    TimeWindow,
    UtcDatetime,
)

# Controlled vocabulary. Adding a type = a one-line change here, reviewed by
# the team, so every module spells the same concept the same way.
EVIDENCE_TYPES: dict[Source, frozenset[str]] = {
    Source.STATIC: frozenset({
        "dependency_count",
        "dependent_count",
        "transitive_dependent_count",
        "graph_depth",
        "loc",
        "cyclomatic_complexity",
    }),
    Source.GIT: frozenset({
        "recent_commit_count",
        "historical_commit_count",
        "days_since_last_change",
        "unique_contributors",
        "lines_added",
        "lines_deleted",
        "total_churn",
        "churn_ratio",
        "co_change_count",
    }),
    Source.CONFIG: frozenset({
        "config_reference",
        "config_reference_count",
    }),
    Source.RUNTIME: frozenset({
        "observed_use",
        "execution_count",
        "days_since_last_observed",
        "runtime_coverage",
    }),
    Source.EXTERNAL: frozenset({
        "possible_external_reference",
        "public_endpoint_count",
    }),
}

# Types where one component can have several items (e.g. one per config file
# line). Their ID also hashes the provenance file locations, so each is unique.
MULTI_VALUED_EVIDENCE_TYPES = frozenset({"config_reference"})

EvidenceValue = bool | int | float | str | None

_UTC_ADAPTER = TypeAdapter(UtcDatetime)


def _canonical_time(value: Any) -> str | None:
    """Same instant -> same string, whether given as str or datetime, any tz."""
    if value is None:
        return None
    return _UTC_ADAPTER.validate_python(value).isoformat()


def _canonical_locations(provenance: Any) -> str:
    """'path:line,path:line' in sorted order, from a dict or a Provenance."""
    if provenance is None:
        return ""
    files = provenance.files if isinstance(provenance, Provenance) else provenance.get("files", [])
    locations = []
    for location in files:
        path, line = (location.path, location.line) if isinstance(location, FileLocation) else (
            location.get("path"), location.get("line"))
        locations.append(f"{path}:{line or ''}")
    return ",".join(sorted(locations))


class FileLocation(ContractModel):
    path: str = Field(description="Repo-relative POSIX path")
    line: int | None = Field(default=None, ge=1)


class Provenance(ContractModel):
    """Pointers back to the raw observations behind a value."""

    commits: list[str] = Field(default_factory=list, description="Full commit SHAs")
    files: list[FileLocation] = Field(default_factory=list)
    trace_ids: list[str] = Field(default_factory=list)
    note: str | None = None

    def is_empty(self) -> bool:
        return not (self.commits or self.files or self.trace_ids or self.note)


class EvidenceItem(ContractModel):
    evidence_id: str = Field(description="Deterministic; filled in automatically when omitted")
    schema_version: str = SCHEMA_VERSION
    repo_id: str = Field(pattern=REPO_ID_PATTERN)
    snapshot: str = Field(pattern=COMMIT_SHA_PATTERN, description="Repository commit analyzed")
    component_id: str = Field(pattern=COMPONENT_ID_PATTERN)
    source: Source
    evidence_type: str
    value: EvidenceValue = None
    unit: str | None = Field(default=None, examples=["commits", "days", "lines"])
    availability: Availability
    as_of: UtcDatetime = Field(description="Only data strictly before this instant was used")
    window: TimeWindow | None = None
    provenance: Provenance = Field(default_factory=Provenance)
    extraction_method: str = Field(examples=["git_history@0.1.0"])

    @model_validator(mode="before")
    @classmethod
    def _fill_evidence_id(cls, data: Any) -> Any:
        if isinstance(data, dict) and not data.get("evidence_id"):
            window = data.get("window") or {}
            if isinstance(window, TimeWindow):
                window = window.model_dump()
            parts = [
                data.get("repo_id"),
                data.get("snapshot"),
                data.get("component_id"),
                data.get("source"),
                data.get("evidence_type"),
                _canonical_time(data.get("as_of")),
                _canonical_time(window.get("start")),
                _canonical_time(window.get("end")),
            ]
            if data.get("evidence_type") in MULTI_VALUED_EVIDENCE_TYPES:
                parts.append(_canonical_locations(data.get("provenance")))
            data = {**data, "evidence_id": make_evidence_id(*parts)}
        return data

    @model_validator(mode="after")
    def _check_rules(self) -> "EvidenceItem":
        allowed = EVIDENCE_TYPES[self.source]
        if self.evidence_type not in allowed:
            raise ValueError(
                f"evidence_type '{self.evidence_type}' is not registered for source {self.source}; "
                f"allowed: {sorted(allowed)}"
            )
        if self.availability is Availability.AVAILABLE:
            if self.value is None:
                raise ValueError("AVAILABLE evidence must carry a value")
            if self.provenance.is_empty() and self.window is None:
                raise ValueError("AVAILABLE evidence needs provenance or an observation window")
        elif self.value is not None:
            raise ValueError(f"{self.availability} evidence must have value=None (unknown is not zero)")
        return self
