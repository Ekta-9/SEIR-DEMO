"""Build the labelled risk dataset from real repositories.

Outputs (in data/dataset/<version>/):
  cases.parquet                 one row per case: ids, features, label, split
  change_cases.jsonl            the same cases in the shared ChangeCase contract
  static_feature_requests.csv   (repo, parent snapshot, component) pairs Member 4
                                must compute structural features for
  manifest.json                 which columns are features / label / FORBIDDEN
  quality_report.json|.md       data-quality + leakage report
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from app.collectors.git_history import GitHistoryIndex
from app.collectors.git_log import read_history
from app.config import Settings
from app.dataset.cases import CandidateCase, find_duplicate_commits, mine_cases
from app.dataset.features import feature_columns, git_feature_row
from app.dataset.labels import LABEL_RULE_VERSION, assign_label
from app.dataset.quality import build_report, to_markdown
from app.dataset.splits import assign_splits
from app.dataset.szz import find_bug_inducing
from app.git_cli import run_git
from app.inventory import list_components
from app.repo_fetcher import RepoCheckout, fetch_repository
from app.schema import ChangeCase

log = logging.getLogger(__name__)

ID_COLUMNS = ["case_id", "repo_id", "commit_sha", "parent_sha", "as_of", "target_component_id",
              "target_parent_path", "action"]
# Post-change information: ingredients of the label. NEVER use as model input.
FORBIDDEN_COLUMNS = ["label_spread", "label_impacted_test_count", "label_caused_bug_fix",
                     "label_fix_commit_count"]
LABEL_COLUMN = "label"
SPLIT_COLUMN = "split"


@dataclass
class RepoBuild:
    rows: list[dict]
    change_cases: list[ChangeCase]
    stats: dict


def _snapshot_time(checkout: RepoCheckout) -> datetime:
    stamp = int(run_git(checkout.path, "show", "-s", "--format=%ct", checkout.snapshot).strip())
    return datetime.fromtimestamp(stamp, tz=timezone.utc)


def build_repository(url: str, settings: Settings) -> RepoBuild:
    checkout = fetch_repository(url, settings)
    components = list_components(checkout.path, checkout.repo_id, checkout.snapshot)
    path_to_component = {c.file_path: c.component_id for c in components}
    commits = read_history(checkout.path, checkout.snapshot, timeout=settings.git_timeout_seconds)
    index = GitHistoryIndex.build(commits, path_to_component, settings)

    censor_from = _snapshot_time(checkout) - timedelta(days=settings.censor_days)
    duplicates = find_duplicate_commits(checkout.path, checkout.snapshot, settings.git_timeout_seconds)
    cases, excluded = mine_cases(commits, index, path_to_component, checkout.repo_id,
                                 censor_from, duplicates, settings)
    log.info("%s: %d cases mined, tracing bug fixes (SZZ)...", checkout.repo_id, len(cases))
    inducing, fixes_traced = find_bug_inducing(checkout.path, commits, path_to_component, settings)

    rows, change_cases = [], []
    for case in cases:
        fixes = sorted(inducing.get((case.commit_sha, case.target_component_id), ()))
        label = assign_label(len(case.impacted), bool(fixes))
        rows.append(_row(case, label.value, fixes) | git_feature_row(index, case, settings))
        change_cases.append(ChangeCase(
            case_id=case.case_id, repo_id=case.repo_id, commit_sha=case.commit_sha,
            parent_sha=case.parent_sha, as_of=case.as_of, target_component_id=case.target_component_id,
            action=case.action, impacted_component_ids=list(case.impacted), fix_commit_shas=fixes,
            label=label, label_rule_version=LABEL_RULE_VERSION,
        ))

    stats = {
        "url": url,
        "snapshot": checkout.snapshot,
        "candidates": len(cases) + sum(excluded.values()),
        "kept": len(cases),
        "excluded": dict(excluded),
        "bug_fix_commits_traced": fixes_traced,
        "censored_from": censor_from.isoformat(),
    }
    return RepoBuild(rows, change_cases, stats)


def _row(case: CandidateCase, label: str, fixes: list[str]) -> dict:
    return {
        "case_id": case.case_id,
        "repo_id": case.repo_id,
        "commit_sha": case.commit_sha,
        "parent_sha": case.parent_sha,
        "as_of": case.as_of,
        "target_component_id": case.target_component_id,
        "target_parent_path": case.target_parent_path,
        "action": case.action.value,
        "label_spread": len(case.impacted),
        "label_impacted_test_count": case.impacted_test_count,
        "label_caused_bug_fix": bool(fixes),
        "label_fix_commit_count": len(fixes),
        LABEL_COLUMN: label,
    }


def build_dataset(urls: list[str], holdout_repos: set[str], settings: Settings, version: str) -> Path:
    out_dir = settings.data_dir / "dataset" / version
    out_dir.mkdir(parents=True, exist_ok=True)

    builds = {}
    for url in urls:
        build = build_repository(url, settings)
        builds[url] = build
        log.info("%s: %d cases kept", url, build.stats["kept"])

    df = pd.DataFrame([row for b in builds.values() for row in b.rows])
    df[SPLIT_COLUMN] = assign_splits(df, holdout_repos, settings.train_fraction, settings.validation_fraction)
    features = feature_columns()
    df = df[[*ID_COLUMNS, *features, *FORBIDDEN_COLUMNS, LABEL_COLUMN, SPLIT_COLUMN]]
    df.to_parquet(out_dir / "cases.parquet", index=False)

    with (out_dir / "change_cases.jsonl").open("w", encoding="utf-8") as handle:
        for build in builds.values():
            for case in build.change_cases:
                handle.write(case.model_dump_json() + "\n")

    requests = df[["case_id", "repo_id", "parent_sha", "target_component_id", "target_parent_path", "as_of"]]
    requests.to_csv(out_dir / "static_feature_requests.csv", index=False)

    repo_stats = {}
    for build in builds.values():
        repo_id = build.change_cases[0].repo_id if build.change_cases else build.stats["url"]
        repo_stats[repo_id] = build.stats

    manifest = {
        "dataset_version": version,
        "label_rule_version": LABEL_RULE_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "id_columns": ID_COLUMNS,
        "feature_columns": features,
        "forbidden_columns": FORBIDDEN_COLUMNS,
        "label_column": LABEL_COLUMN,
        "split_column": SPLIT_COLUMN,
        "holdout_repositories": sorted(holdout_repos),
        "repositories": {r: {"url": s["url"], "snapshot": s["snapshot"]} for r, s in repo_stats.items()},
        "settings": {
            "recent_window_days": settings.recent_window_days,
            "bulk_commit_file_threshold": settings.bulk_commit_file_threshold,
            "co_change_min_support": settings.co_change_min_support,
            "censor_days": settings.censor_days,
            "train_fraction": settings.train_fraction,
            "validation_fraction": settings.validation_fraction,
        },
        "notes": "Structural (STATIC) features are pending from Member 4; see static_feature_requests.csv.",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    report = build_report(df, repo_stats, features, FORBIDDEN_COLUMNS)
    (out_dir / "quality_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (out_dir / "quality_report.md").write_text(to_markdown(report, manifest), encoding="utf-8")
    return out_dir
