"""End-to-end evidence pipeline for one repository snapshot.

Git history (Phase 2) and configuration (Phase 4); runtime evidence (Phase 5)
plugs in here too, so the web service (Phase 6) only ever calls `analyze_repository`.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.collectors.config_files import ComponentResolver, ConfigScan, build_config_evidence, package_of, scan_revision
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
    config_scan: ConfigScan | None = None
    stats: dict = field(default_factory=dict)

    def write(self, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, records in (("components", self.components), ("evidence", self.evidence), ("edges", self.edges)):
            payload = [r.model_dump(mode="json") for r in records]
            (out_dir / f"{name}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        (out_dir / "stats.json").write_text(json.dumps(self.stats, indent=2, default=str), encoding="utf-8")
        if self.config_scan:
            # every reference found, including UNRESOLVED (possibly stale) and EXTERNAL ones
            refs = [asdict(r) for r in self.config_scan.references]
            (out_dir / "config_references.json").write_text(json.dumps(refs, indent=2), encoding="utf-8")


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

    # Packages of classes that ever existed, so references to deleted classes
    # are reported as UNRESOLVED (possibly stale) instead of EXTERNAL.
    resolver = ComponentResolver(component_ids, known_packages={package_of(c) for c in index.component_ids})
    config_scan = scan_revision(checkout.path, checkout.snapshot, resolver, timeout=settings.git_timeout_seconds)
    evidence += build_config_evidence(config_scan, component_ids, checkout.repo_id, checkout.snapshot, as_of)

    stats = {
        "components": len(components),
        "components_with_history": len(index.component_ids & set(component_ids)),
        "java_commits": len(commits),
        "bulk_commits": sum(len(c.files) > settings.bulk_commit_file_threshold for c in commits),
        "evidence_items": len(evidence),
        "co_change_edges": len(edges),
        "config": config_scan.stats(),
        "as_of": as_of.isoformat(),
    }
    return AnalysisResult(checkout.repo_id, checkout.snapshot, as_of, components, evidence, edges,
                          config_scan, stats)
