"""Configuration evidence *as it was* just before each historical change.

Each case's pre-change snapshot (`parent_sha`) is scanned straight from git
objects. Many cases share a parent, and configuration files rarely change, so
snapshots are scanned once and file contents are cached by blob SHA.
"""

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.collectors.config_files import ComponentResolver, TokenCache, build_config_evidence, package_of, scan_revision
from app.collectors.git_history import GitHistoryIndex
from app.config import Settings
from app.dataset.cases import CandidateCase
from app.schema import EvidenceItem


def config_evidence_by_case(repo_dir: Path, cases: list[CandidateCase], index: GitHistoryIndex,
                            settings: Settings) -> dict[str, list[EvidenceItem]]:
    by_parent: dict[str, list[CandidateCase]] = defaultdict(list)
    for case in cases:
        by_parent[case.parent_sha].append(case)
    # Packages only decide UNRESOLVED vs EXTERNAL, neither of which is counted
    # as a feature, so using all historical packages cannot leak information.
    known_packages = {package_of(c) for c in index.component_ids}
    cache: TokenCache = {}

    def scan_parent(parent: str) -> dict[str, list[EvidenceItem]]:
        group = by_parent[parent]
        # Resolve only against classes that existed at that moment.
        resolver = ComponentResolver(index.alive_components(min(c.as_of for c in group)), known_packages)
        scan = scan_revision(repo_dir, parent, resolver, cache, timeout=settings.git_timeout_seconds)
        return {
            case.case_id: build_config_evidence(scan, [case.target_component_id], case.repo_id, parent, case.as_of)
            for case in group
        }

    result: dict[str, list[EvidenceItem]] = {}
    with ThreadPoolExecutor(max_workers=settings.szz_workers) as pool:
        for items_by_case in pool.map(scan_parent, by_parent):
            result.update(items_by_case)
    return result
