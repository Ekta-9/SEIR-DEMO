"""Git/evolution evidence (report §5): nine history features per component,
computed as of any cutoff time, plus CO_CHANGE edges.

Usage:
    index = GitHistoryIndex.build(commits, path_to_component, settings)
    items = build_git_evidence(index, component_ids, repo_id, snapshot, as_of, settings)

The index is built once per repository; computing features at a new cutoff
only filters in memory, which is what Phase 3 needs to create thousands of
pre-change examples quickly.
"""

from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.collectors.git_log import CommitRecord, attribute_changes
from app.config import Settings
from app.schema import Availability, DependencyEdge, EdgeType, EvidenceItem, Provenance, Source, TimeWindow
from app.schema.evidence import FileLocation

EXTRACTION_METHOD = "git_history@0.1.0"
SECONDS_PER_DAY = 86_400
CHURN_RATIO_DECIMALS = 4
TOP_PARTNERS_IN_NOTE = 10


@dataclass(frozen=True)
class Touch:
    """One commit's effect on one component."""

    sha: str
    timestamp: datetime
    author: str
    added: int
    deleted: int
    paths: frozenset[str]
    partners: frozenset[str]  # other components in the same (non-bulk) commit
    removes_component: bool  # every file of the component was deleted in this commit


@dataclass(frozen=True)
class GitFeatures:
    component_id: str
    as_of: datetime
    touches: tuple[Touch, ...]  # before as_of, oldest first
    recent: tuple[Touch, ...]  # inside the recent window
    recent_window: TimeWindow
    partners: Counter  # co-change partner -> shared commit count (>= min support)

    @property
    def historical_commit_count(self) -> int:
        return len(self.touches)

    @property
    def recent_commit_count(self) -> int:
        return len(self.recent)

    @property
    def lines_added(self) -> int:
        return sum(t.added for t in self.touches)

    @property
    def lines_deleted(self) -> int:
        return sum(t.deleted for t in self.touches)

    @property
    def total_churn(self) -> int:
        return self.lines_added + self.lines_deleted

    @property
    def recent_churn(self) -> int:
        return sum(t.added + t.deleted for t in self.recent)

    @property
    def unique_contributors(self) -> int:
        return len({t.author for t in self.touches})

    @property
    def days_since_last_change(self) -> int | None:
        if not self.touches:
            return None
        return int((self.as_of - self.touches[-1].timestamp).total_seconds() // SECONDS_PER_DAY)

    @property
    def churn_ratio(self) -> float | None:
        """Share of the component's lifetime churn that happened recently."""
        if self.total_churn == 0:
            return None
        return round(self.recent_churn / self.total_churn, CHURN_RATIO_DECIMALS)


class GitHistoryIndex:
    def __init__(self, touches: dict[str, list[Touch]], settings: Settings):
        self._touches = touches  # component -> touches, oldest first
        self._times = {c: [t.timestamp for t in ts] for c, ts in touches.items()}
        self._settings = settings

    @classmethod
    def build(
        cls, commits: list[CommitRecord], path_to_component: dict[str, str], settings: Settings
    ) -> "GitHistoryIndex":
        # 1) group each commit's file changes by component
        per_commit: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        commit_by_sha = {c.sha: c for c in commits}
        for commit, change, component_id in attribute_changes(commits, path_to_component):
            per_commit[commit.sha][component_id].append(change)

        # 2) one Touch per (commit, component); partners only for non-bulk commits
        touches: dict[str, list[Touch]] = defaultdict(list)
        for sha, by_component in per_commit.items():
            commit = commit_by_sha[sha]
            is_bulk = len(commit.files) > settings.bulk_commit_file_threshold
            members = frozenset(by_component)
            for component_id, changes in by_component.items():
                touches[component_id].append(
                    Touch(
                        sha=sha,
                        timestamp=commit.timestamp,
                        author=commit.author,
                        added=sum(ch.added for ch in changes),
                        deleted=sum(ch.deleted for ch in changes),
                        paths=frozenset(ch.path for ch in changes),
                        partners=frozenset() if is_bulk else members - {component_id},
                        removes_component=all(ch.is_file_deletion for ch in changes),
                    )
                )
        for component_touches in touches.values():
            component_touches.sort(key=lambda t: (t.timestamp, t.sha))
        return cls(dict(touches), settings)

    @property
    def component_ids(self) -> set[str]:
        return set(self._touches)

    def latest_timestamp(self) -> datetime | None:
        latest = [ts[-1] for ts in self._times.values() if ts]
        return max(latest) if latest else None

    def _touches_before(self, component_id: str, as_of: datetime) -> list[Touch]:
        cutoff = bisect_left(self._times.get(component_id, []), as_of)
        return self._touches.get(component_id, [])[:cutoff]

    def is_alive(self, component_id: str, as_of: datetime) -> bool:
        """Did the component exist just before `as_of`? (created and not since deleted)"""
        before = self._touches_before(component_id, as_of)
        return bool(before) and not before[-1].removes_component

    def alive_components(self, as_of: datetime) -> set[str]:
        """Every component that existed just before `as_of`."""
        return {c for c in self._touches if self.is_alive(c, as_of)}

    def features(self, component_id: str, as_of: datetime) -> GitFeatures:
        """Features using only commits strictly before `as_of` (no leakage)."""
        before = self._touches_before(component_id, as_of)

        window_start = as_of - timedelta(days=self._settings.recent_window_days)
        recent = [t for t in before if t.timestamp >= window_start]

        # Partners deleted before the cutoff are history, not current coupling.
        shared = Counter(partner for t in before for partner in t.partners)
        partners = Counter({
            p: n for p, n in shared.items()
            if n >= self._settings.co_change_min_support and self.is_alive(p, as_of)
        })

        return GitFeatures(
            component_id=component_id,
            as_of=as_of,
            touches=tuple(before),
            recent=tuple(recent),
            recent_window=TimeWindow(start=window_start, end=as_of),
            partners=partners,
        )


# ---- EvidenceItem construction ------------------------------------------------

def _latest_shas(touches: tuple[Touch, ...], limit: int) -> list[str]:
    return [t.sha for t in reversed(touches)][:limit]


def _files(touches: tuple[Touch, ...]) -> list[FileLocation]:
    paths = sorted({p for t in touches for p in t.paths})
    return [FileLocation(path=p) for p in paths]


def _history_note(features: GitFeatures, limit: int) -> str:
    total = features.historical_commit_count
    shown = min(total, limit)
    return (
        f"{total} non-merge commits touching this component before as_of "
        f"(latest {shown} listed); renames followed"
    )


def build_git_evidence(
    index: GitHistoryIndex,
    component_ids: list[str],
    repo_id: str,
    snapshot: str,
    as_of: datetime,
    settings: Settings,
) -> list[EvidenceItem]:
    limit = settings.max_provenance_commits
    items: list[EvidenceItem] = []

    for component_id in component_ids:
        f = index.features(component_id, as_of)
        if not f.touches:
            # No history before the cutoff: we cannot say anything reliable.
            items.extend(_unknown_items(component_id, repo_id, snapshot, as_of))
            continue

        lifetime = TimeWindow(start=f.touches[0].timestamp, end=as_of)
        history = Provenance(commits=_latest_shas(f.touches, limit), files=_files(f.touches),
                             note=_history_note(f, limit))
        recent = Provenance(commits=_latest_shas(f.recent, limit), files=_files(f.touches),
                            note=f"{f.recent_commit_count} commits in the last {settings.recent_window_days} days")
        top_partners = ", ".join(f"{p} ({n})" for p, n in f.partners.most_common(TOP_PARTNERS_IN_NOTE))
        co_change = Provenance(
            files=_files(f.touches),
            note=(f"partners changed together >= {settings.co_change_min_support} times: {top_partners}"
                  if f.partners else "no partner reached the minimum co-change support"),
        )

        rows = [
            ("recent_commit_count", f.recent_commit_count, "commits", f.recent_window, recent),
            ("historical_commit_count", f.historical_commit_count, "commits", lifetime, history),
            ("days_since_last_change", f.days_since_last_change, "days", None,
             Provenance(commits=[f.touches[-1].sha], files=_files(f.touches))),
            ("unique_contributors", f.unique_contributors, "authors", lifetime, history),
            ("lines_added", f.lines_added, "lines", lifetime, history),
            ("lines_deleted", f.lines_deleted, "lines", lifetime, history),
            ("total_churn", f.total_churn, "lines", lifetime, history),
            ("churn_ratio", f.churn_ratio, "ratio", f.recent_window, recent),
            ("co_change_count", len(f.partners), "components", lifetime, co_change),
        ]
        for evidence_type, value, unit, window, provenance in rows:
            items.append(EvidenceItem(
                repo_id=repo_id, snapshot=snapshot, component_id=component_id,
                source=Source.GIT, evidence_type=evidence_type,
                value=value, unit=unit if value is not None else None,
                availability=Availability.AVAILABLE if value is not None else Availability.UNKNOWN,
                as_of=as_of, window=window,
                provenance=provenance if value is not None else Provenance(note="total churn is zero"),
                extraction_method=EXTRACTION_METHOD,
            ))
    return items


def _unknown_items(component_id: str, repo_id: str, snapshot: str, as_of: datetime) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            repo_id=repo_id, snapshot=snapshot, component_id=component_id,
            source=Source.GIT, evidence_type=evidence_type,
            availability=Availability.UNKNOWN, as_of=as_of,
            provenance=Provenance(note="no commits found for this component before as_of"),
            extraction_method=EXTRACTION_METHOD,
        )
        for evidence_type in (
            "recent_commit_count", "historical_commit_count", "days_since_last_change",
            "unique_contributors", "lines_added", "lines_deleted", "total_churn",
            "churn_ratio", "co_change_count",
        )
    ]


def build_co_change_edges(
    index: GitHistoryIndex, component_ids: list[str], repo_id: str, snapshot: str,
    as_of: datetime, evidence: list[EvidenceItem],
) -> list[DependencyEdge]:
    """One directed CO_CHANGE edge per (component, partner) — co-change is
    symmetric, so each pair appears in both directions."""
    in_scope = set(component_ids)
    evidence_id = {
        e.component_id: e.evidence_id for e in evidence if e.evidence_type == "co_change_count"
    }
    edges = []
    for component_id in component_ids:
        for partner, count in sorted(index.features(component_id, as_of).partners.items()):
            if partner not in in_scope:
                continue  # partner no longer exists at this snapshot
            edges.append(DependencyEdge(
                repo_id=repo_id, snapshot=snapshot, source_id=component_id, target_id=partner,
                edge_type=EdgeType.CO_CHANGE, count=count,
                evidence_ids=[evidence_id[component_id]] if component_id in evidence_id else [],
            ))
    return edges
