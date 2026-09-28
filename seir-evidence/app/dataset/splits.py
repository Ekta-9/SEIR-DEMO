"""Leakage-aware dataset splits (report §12.2).

* Chronological inside each repository: train on the past, test on the future.
  Cut points are *times*, so all cases from one commit land in the same split.
* Repository holdout: whole repositories reserved as an unseen-project test.
"""

import pandas as pd

TRAIN, VALIDATION, TEST, HOLDOUT = "train", "validation", "test", "holdout"


def assign_splits(df: pd.DataFrame, holdout_repos: set[str], train_fraction: float,
                  validation_fraction: float) -> pd.Series:
    if not 0 < train_fraction < train_fraction + validation_fraction < 1:
        raise ValueError("need 0 < train < train + validation < 1")
    split = pd.Series(TEST, index=df.index, dtype="object")
    for repo_id, group in df.groupby("repo_id"):
        if repo_id in holdout_repos:
            split[group.index] = HOLDOUT
            continue
        train_end = group["as_of"].quantile(train_fraction)
        validation_end = group["as_of"].quantile(train_fraction + validation_fraction)
        split[group.index[group["as_of"] < train_end]] = TRAIN
        split[group.index[(group["as_of"] >= train_end) & (group["as_of"] < validation_end)]] = VALIDATION
    return split
