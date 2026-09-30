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

from app.collectors.config_files import EXTRACTION_METHOD as CONFIG_EXTRACTION_METHOD
from app.collectors.git_history import EXTRACTION_METHOD as GIT_EXTRACTION_METHOD
from app.collectors.git_history import GitHistoryIndex
from app.collectors.git_log import read_history
from app.config import Settings
from app.dataset.cases import SAMPLED_OUT, CandidateCase, find_duplicate_commits, mine_cases, sample_by_commit
from app.dataset.config_history import config_evidence_by_case
from app.dataset.features import FEATURE_SPEC_VERSION, feature_columns, feature_row
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


@dataclass(frozen=True)
class RepoSpec:
    url: str
    max_cases: int | None = None  # cap for very large repositories (corpus.yaml `max_cases`)
    ref: str | None = None  # pinned commit (corpus.yaml `ref`) so a dataset version can be rebuilt identically


@dataclass
class RepoBuild:
    rows: list[dict]
    change_cases: list[ChangeCase]
    stats: dict


def _snapshot_time(checkout: RepoCheckout) -> datetime:
    stamp = int(run_git(checkout.path, "show", "-s", "--format=%ct", checkout.snapshot).strip())
    return datetime.fromtimestamp(stamp, tz=timezone.utc)


def build_repository(url: str, settings: Settings, max_cases: int | None = None,
                     ref: str | None = None) -> RepoBuild:
    checkout = fetch_repository(url, settings, ref)
    components = list_components(checkout.path, checkout.repo_id, checkout.snapshot)
    path_to_component = {c.file_path: c.component_id for c in components}
    commits = read_history(checkout.path, checkout.snapshot, timeout=settings.git_timeout_seconds)
    index = GitHistoryIndex.build(commits, path_to_component, settings)

    censor_from = _snapshot_time(checkout) - timedelta(days=settings.censor_days)
    duplicates = find_duplicate_commits(checkout.path, checkout.snapshot, settings.git_timeout_seconds)
    cases, excluded = mine_cases(commits, index, path_to_component, checkout.repo_id,
                                 censor_from, duplicates, settings)
    if max_cases is not None and len(cases) > max_cases:
        sampled = sample_by_commit(cases, max_cases, settings.dataset_sample_seed)
        excluded[SAMPLED_OUT] = len(cases) - len(sampled)
        cases = sampled
    log.info("%s: %d cases mined, tracing bug fixes (SZZ)...", checkout.repo_id, len(cases))
    inducing, fixes_traced = find_bug_inducing(checkout.path, commits, path_to_component, settings)
    log.info("%s: scanning configuration at %d pre-change snapshots...", checkout.repo_id,
             len({c.parent_sha for c in cases}))
    config_items = config_evidence_by_case(checkout.path, cases, index, settings)

    rows, change_cases = [], []
    for case in cases:
        fixes = sorted(inducing.get((case.commit_sha, case.target_component_id), ()))
        label = assign_label(len(case.impacted), bool(fixes))
        rows.append(_row(case, label.value, fixes)
                    | feature_row(index, case, config_items[case.case_id], settings))
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
        "max_cases": max_cases,
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


def build_dataset(repos: list[RepoSpec | str], holdout_repos: set[str], settings: Settings, version: str) -> Path:
    """`repos` may be RepoSpec objects or plain URLs (the original API, still used by
    Member 3's `build_dataset_v2.py`); a plain URL means no cap and no pinned ref."""
    repos = [spec if isinstance(spec, RepoSpec) else RepoSpec(spec) for spec in repos]
    out_dir = settings.data_dir / "dataset" / version
    out_dir.mkdir(parents=True, exist_ok=True)

    builds = {}
    for spec in repos:
        build = build_repository(spec.url, settings, spec.max_cases, spec.ref)
        builds[spec.url] = build
        log.info("%s: %d cases kept", spec.url, build.stats["kept"])

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
            "dataset_sample_seed": settings.dataset_sample_seed,
        },
        "feature_spec_version": FEATURE_SPEC_VERSION,
        "feature_extractors": {"git": GIT_EXTRACTION_METHOD, "config": CONFIG_EXTRACTION_METHOD},
        "notes": "Structural (STATIC) features are pending from Member 4; see static_feature_requests.csv. "
                 "config_config_reference_count counts RUNTIME configuration references at the pre-change snapshot.",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    report = build_report(df, repo_stats, features, FORBIDDEN_COLUMNS)
    (out_dir / "quality_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (out_dir / "quality_report.md").write_text(to_markdown(report, manifest), encoding="utf-8")
    return out_dir
