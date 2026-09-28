"""End-to-end evidence pipeline for one repository snapshot.

Phase 2 covers Git history; later phases add config and runtime collectors
here, so the web service (Phase 6) only ever calls `analyze_repository`.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.collectors.git_history import GitHistoryIndex, build_co_change_edges, build_git_evidence
from app.collectors.git_log import read_history
from app.config import Settings
from app.git_cli import run_git
from app.inventory import list_components
from app.repo_fetcher import RepoCheckout
from app.schema import Component, DependencyEdge, EvidenceItem

# Include the snapshot commit itself: as_of is exclusive.
SNAPSHOT_CUTOFF_MARGIN = timedelta(seconds=1)


@dataclass
class AnalysisResult:
    repo_id: str
    snapshot: str
    as_of: datetime
    components: list[Component]
    evidence: list[EvidenceItem]
    edges: list[DependencyEdge]
    stats: dict = field(default_factory=dict)

    def write(self, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, records in (("components", self.components), ("evidence", self.evidence), ("edges", self.edges)):
            payload = [r.model_dump(mode="json") for r in records]
            (out_dir / f"{name}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        (out_dir / "stats.json").write_text(json.dumps(self.stats, indent=2, default=str), encoding="utf-8")


def snapshot_cutoff(checkout: RepoCheckout, index: GitHistoryIndex) -> datetime:
    """as_of for 'current state' analysis: just after the snapshot commit.

    Committer clocks can be skewed, so an ancestor may carry a later timestamp
    than the snapshot; take the max so every reachable commit is included.
    """
    snapshot_time = datetime.fromtimestamp(
        int(run_git(checkout.path, "show", "-s", "--format=%ct", checkout.snapshot).strip()), tz=timezone.utc
    )
    latest = index.latest_timestamp()
    return max(snapshot_time, latest or snapshot_time) + SNAPSHOT_CUTOFF_MARGIN


def analyze_repository(checkout: RepoCheckout, settings: Settings) -> AnalysisResult:
    components = list_components(checkout.path, checkout.repo_id, checkout.snapshot)
    path_to_component = {c.file_path: c.component_id for c in components}

    commits = read_history(checkout.path, checkout.snapshot, timeout=settings.git_timeout_seconds)
    index = GitHistoryIndex.build(commits, path_to_component, settings)
    as_of = snapshot_cutoff(checkout, index)

    component_ids = [c.component_id for c in components]
    evidence = build_git_evidence(index, component_ids, checkout.repo_id, checkout.snapshot, as_of, settings)
    edges = build_co_change_edges(index, component_ids, checkout.repo_id, checkout.snapshot, as_of, evidence)

    stats = {
        "components": len(components),
        "components_with_history": len(index.component_ids & set(component_ids)),
        "java_commits": len(commits),
        "bulk_commits": sum(len(c.files) > settings.bulk_commit_file_threshold for c in commits),
        "evidence_items": len(evidence),
        "co_change_edges": len(edges),
        "as_of": as_of.isoformat(),
    }
    return AnalysisResult(checkout.repo_id, checkout.snapshot, as_of, components, evidence, edges, stats)
