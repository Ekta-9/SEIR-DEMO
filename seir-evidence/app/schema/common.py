"""Shared vocabulary for every SEIR contract.

All enums serialize as UPPER_SNAKE strings, all JSON fields are snake_case,
and all timestamps must be timezone-aware (serialized as ISO-8601 UTC).
"""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, model_validator

SCHEMA_VERSION = "1.2.0"

# Fully qualified Java class name; nested classes use '$' (JVM convention).
COMPONENT_ID_PATTERN = r"^[A-Za-z_$][\w$]*(\.[A-Za-z_$][\w$]*)*$"
# "owner/name", exactly as it appears in the GitHub URL.
REPO_ID_PATTERN = r"^[\w.-]+/[\w.-]+$"
# Full 40-character commit SHA — short SHAs are ambiguous across repos.
COMMIT_SHA_PATTERN = r"^[0-9a-f]{40}$"


def _require_utc(value: datetime) -> datetime:
    """Reject naive datetimes and normalize everything to UTC."""
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware (e.g. '2026-01-31T10:00:00Z')")
    return value.astimezone(timezone.utc)


UtcDatetime = Annotated[datetime, AfterValidator(_require_utc)]


class ContractModel(BaseModel):
    """Base for all contracts: unknown fields are errors, not silently dropped."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Source(StrEnum):
    STATIC = "STATIC"
    GIT = "GIT"
    CONFIG = "CONFIG"
    RUNTIME = "RUNTIME"
    EXTERNAL = "EXTERNAL"


class Availability(StrEnum):
    AVAILABLE = "AVAILABLE"  # measured; value is meaningful (0 really means 0)
    UNAVAILABLE = "UNAVAILABLE"  # this source does not exist for the repo
    UNKNOWN = "UNKNOWN"  # source exists but this value could not be determined


class ComponentKind(StrEnum):
    CLASS = "CLASS"
    INTERFACE = "INTERFACE"
    ENUM = "ENUM"
    RECORD = "RECORD"
    ANNOTATION = "ANNOTATION"


class EdgeType(StrEnum):
    IMPORTS = "IMPORTS"
    CALLS = "CALLS"
    EXTENDS = "EXTENDS"
    IMPLEMENTS = "IMPLEMENTS"
    INSTANTIATES = "INSTANTIATES"
    FIELD_TYPE = "FIELD_TYPE"
    ANNOTATED_BY = "ANNOTATED_BY"
    CONFIG_REF = "CONFIG_REF"
    RUNTIME_CALL = "RUNTIME_CALL"
    CO_CHANGE = "CO_CHANGE"


class ChangeAction(StrEnum):
    MODIFY = "MODIFY"
    DELETE = "DELETE"
    DEPRECATE = "DEPRECATE"


class RiskClass(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RuntimeCoverage(StrEnum):
    HIGH = "HIGH"
    PARTIAL = "PARTIAL"
    LOW = "LOW"
    UNAVAILABLE = "UNAVAILABLE"


class TimeWindow(ContractModel):
    """Half-open interval [start, end) that a time-sensitive value covers."""

    start: UtcDatetime
    end: UtcDatetime

    @model_validator(mode="after")
    def _start_before_end(self) -> "TimeWindow":
        if self.start > self.end:
            raise ValueError("window.start must not be after window.end")
        return self
