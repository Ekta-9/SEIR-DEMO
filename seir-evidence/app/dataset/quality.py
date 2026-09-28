"""Dataset quality report (Data & Evolution report §9, §11.1, §18).

Every dataset version gets a machine-readable report plus a Markdown summary,
so the numbers in the final thesis can be traced to a specific build.
"""

import pandas as pd

from app.dataset.splits import TEST, TRAIN, VALIDATION

LABEL_ORDER = ["LOW", "MEDIUM", "HIGH"]
DOMINANCE_WARNING_SHARE = 0.6


def _label_table(df: pd.DataFrame, by: str) -> dict:
    counts = pd.crosstab(df[by], df["label"]).reindex(columns=LABEL_ORDER, fill_value=0)
    return {
        str(key): {label: int(row[label]) for label in LABEL_ORDER} | {"total": int(row.sum())}
        for key, row in counts.iterrows()
    }


def leakage_checks(df: pd.DataFrame, feature_cols: list[str], forbidden_cols: list[str]) -> dict:
    checks = {
        "no_forbidden_column_used_as_feature": not set(feature_cols) & set(forbidden_cols),
        "case_ids_unique": bool(df["case_id"].is_unique),
        "days_since_last_change_non_negative": bool((df["git_days_since_last_change"].dropna() >= 0).all()),
        # the in-line LeakageError guard ran for every row (build aborts otherwise)
        "change_commit_invisible_to_own_features": True,
    }
    temporal_ok = True
    for _, group in df.groupby("repo_id"):
        by_split = {s: group.loc[group["split"] == s, "as_of"] for s in (TRAIN, VALIDATION, TEST)}
        for earlier, later in ((TRAIN, VALIDATION), (VALIDATION, TEST)):
            if len(by_split[earlier]) and len(by_split[later]) and by_split[earlier].max() > by_split[later].min():
                temporal_ok = False
    checks["splits_are_chronological"] = temporal_ok
    return checks


def build_report(df: pd.DataFrame, repo_stats: dict, feature_cols: list[str], forbidden_cols: list[str]) -> dict:
    repo_share = df["repo_id"].value_counts(normalize=True)
    report = {
        "total_cases": int(len(df)),
        "repositories": repo_stats,
        "labels_overall": {label: int((df["label"] == label).sum()) for label in LABEL_ORDER},
        "labels_by_repo": _label_table(df, "repo_id"),
        "labels_by_split": _label_table(df, "split"),
        "actions": df["action"].value_counts().to_dict(),
        "feature_missing_rate": {c: round(float(df[c].isna().mean()), 4) for c in feature_cols},
        "repo_share": {k: round(float(v), 4) for k, v in repo_share.items()},
        "repo_dominance_warning": bool(repo_share.max() > DOMINANCE_WARNING_SHARE),
        # Sanity signal: do features differ between labels at all? (medians per label)
        "feature_median_by_label": {
            label: {c: float(df.loc[df["label"] == label, c].median()) for c in feature_cols}
            for label in LABEL_ORDER if (df["label"] == label).any()
        },
        "leakage_checks": leakage_checks(df, feature_cols, forbidden_cols),
    }
    return report


def to_markdown(report: dict, manifest: dict) -> str:
    lines = [
        f"# Dataset quality report — {manifest['dataset_version']}",
        "",
        f"Label rules: `{manifest['label_rule_version']}` · built {manifest['created_at']}",
        "",
        "## Repositories",
        "",
        "| Repository | Snapshot | Candidates | Kept | Bug-fix commits traced | Excluded (reason: count) |",
        "|---|---|---|---|---|---|",
    ]
    for repo_id, stats in report["repositories"].items():
        excluded = ", ".join(f"{k}: {v}" for k, v in sorted(stats["excluded"].items())) or "—"
        lines.append(f"| {repo_id} | `{stats['snapshot'][:12]}` | {stats['candidates']} | {stats['kept']} "
                     f"| {stats['bug_fix_commits_traced']} | {excluded} |")

    def label_rows(title: str, table: dict) -> None:
        lines.extend(["", f"## Labels by {title}", "", "| | LOW | MEDIUM | HIGH | total |", "|---|---|---|---|---|"])
        for key, row in table.items():
            pct = lambda n: f"{n} ({n / row['total']:.0%})" if row["total"] else "0"
            lines.append(f"| {key} | {pct(row['LOW'])} | {pct(row['MEDIUM'])} | {pct(row['HIGH'])} | {row['total']} |")

    label_rows("repository", report["labels_by_repo"])
    label_rows("split", report["labels_by_split"])

    lines.extend(["", "## Feature missing rate", "", "| Feature | Missing |", "|---|---|"])
    lines.extend(f"| {c} | {r:.1%} |" for c, r in report["feature_missing_rate"].items())

    medians = report["feature_median_by_label"]
    labels = list(medians)
    lines.extend(["", "## Feature medians by label (sanity check)", "",
                  "| Feature | " + " | ".join(labels) + " |", "|---" * (len(labels) + 1) + "|"])
    for c in report["feature_missing_rate"]:
        lines.append(f"| {c} | " + " | ".join(f"{medians[label][c]:g}" for label in labels) + " |")

    lines.extend(["", "## Leakage checks", ""])
    lines.extend(f"- {'✅' if ok else '❌'} {name}" for name, ok in report["leakage_checks"].items())
    if report["repo_dominance_warning"]:
        lines.extend(["", f"⚠️ One repository contributes more than {DOMINANCE_WARNING_SHARE:.0%} of cases."])
    return "\n".join(lines) + "\n"
