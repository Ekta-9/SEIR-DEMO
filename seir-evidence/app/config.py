"""Central settings. Every tunable number lives here — no magic numbers in code.

Values can be overridden with environment variables prefixed `SEIR_`,
e.g. `SEIR_RECENT_WINDOW_DAYS=180`.
"""

import os
from dataclasses import dataclass, field, fields
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    # Where cloned repositories and generated data are stored.
    workspace_dir: Path = field(default=PROJECT_ROOT / "workspace")
    data_dir: Path = field(default=PROJECT_ROOT / "data")

    # --- Git history ---------------------------------------------------------
    # "Recent" activity window for recent_commit_count / churn_ratio.
    recent_window_days: int = 90
    # Commits touching more Java files than this are bulk edits (initial
    # import, licence headers, reformatting). They still count as real changes
    # for commit counts and churn, but are excluded from co-change: touching
    # 300 files together says nothing about how those files relate.
    # 30 follows common practice in co-change mining (Zimmermann et al., 2005).
    bulk_commit_file_threshold: int = 30
    # Two components must change together at least this often to count as
    # co-change partners (filters one-off coincidences).
    co_change_min_support: int = 2
    # Cap on commit SHAs listed in one evidence item's provenance; the full
    # set is always reproducible from the query described in the note.
    max_provenance_commits: int = 20

    # --- Dataset (Phase 3) -------------------------------------------------------
    # Changes this close to the snapshot are dropped: a bug they caused may not
    # have been found and fixed yet (right-censoring).
    censor_days: int = 180
    # Parallel git processes for SZZ blame (git is process-safe).
    szz_workers: int = 8
    # Chronological split inside each repository (the rest is the test period).
    train_fraction: float = 0.70
    validation_fraction: float = 0.15

    # --- Network ---------------------------------------------------------------
    git_timeout_seconds: int = 600

    @property
    def repos_dir(self) -> Path:
        return self.workspace_dir / "repos"


def load_settings() -> Settings:
    overrides = {}
    for f in fields(Settings):
        raw = os.environ.get(f"SEIR_{f.name.upper()}")
        if raw is None:
            continue
        overrides[f.name] = Path(raw) if f.name.endswith("_dir") else type(f.default)(raw)
    return Settings(**overrides)
