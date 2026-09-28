"""Contracts produced by the Software Analysis module (Member 4).

Every other module joins on `component_id`, so this file defines the
single source of truth for what a "component" is.
"""

from pydantic import Field, field_validator

from app.schema.common import (
    COMMIT_SHA_PATTERN,
    COMPONENT_ID_PATTERN,
    REPO_ID_PATTERN,
    ComponentKind,
    ContractModel,
    EdgeType,
)


class Component(ContractModel):
    """One top-level Java type (class/interface/enum/record/annotation)."""

    component_id: str = Field(pattern=COMPONENT_ID_PATTERN, examples=["com.shop.payment.LegacyPaymentService"])
    repo_id: str = Field(pattern=REPO_ID_PATTERN)
    snapshot: str = Field(pattern=COMMIT_SHA_PATTERN, description="Commit the component was extracted from")
    simple_name: str
    package: str = Field(description="Empty string for the default package")
    kind: ComponentKind
    file_path: str = Field(description="Repo-relative POSIX path, e.g. 'src/main/java/com/shop/Foo.java'")
    module: str | None = Field(default=None, description="Build module for multi-module repos, else null")
    is_test: bool = False
    loc: int | None = Field(default=None, ge=0)

    @field_validator("file_path")
    @classmethod
    def _repo_relative_posix(cls, path: str) -> str:
        if "\\" in path:
            raise ValueError("file_path must use '/' separators")
        if path.startswith("/") or (len(path) > 1 and path[1] == ":"):
            raise ValueError("file_path must be repo-relative, not absolute")
        return path


class DependencyEdge(ContractModel):
    """Directed edge: `source_id` depends on `target_id`."""

    repo_id: str = Field(pattern=REPO_ID_PATTERN)
    snapshot: str = Field(pattern=COMMIT_SHA_PATTERN)
    source_id: str = Field(pattern=COMPONENT_ID_PATTERN)
    target_id: str = Field(pattern=COMPONENT_ID_PATTERN)
    edge_type: EdgeType
    count: int = Field(default=1, ge=1, description="How many occurrences support this edge")
    evidence_ids: list[str] = Field(default_factory=list)
