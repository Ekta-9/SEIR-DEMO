# seir-evidence

SEIR's Data/Evolution module (Member 5): Git, configuration and runtime evidence,
the risk-model dataset, and the evidence-grounded explainer.

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows (use .venv/bin/activate on Linux/macOS)
pip install -e ".[dev]"
pytest
```

## Run

```bash
# analyze a repository (clones into workspace/, writes JSON into data/)
python -m scripts.run_analysis https://github.com/spring-projects/spring-petclinic

# verify Git evidence against independent git queries + repeatability
python -m scripts.verify_git_history https://github.com/spring-projects/spring-petclinic --sample 20
```

```bash
# build the labelled risk dataset from corpus.yaml (repos with role 'dataset')
python -m scripts.build_dataset --version v1
```

Dataset guide for the ML module: [docs/DATASET.md](docs/DATASET.md).

Tunables live in `app/config.py` and can be overridden with `SEIR_*` env vars
(e.g. `SEIR_RECENT_WINDOW_DAYS=180`).

## Layout

```
app/
  schema/            shared contracts (source of truth for /contracts)
  collectors/
    git_log.py       one-pass git log parsing + rename-following attribution
    git_history.py   9 Git features as of any cutoff + CO_CHANGE edges
  dataset/
    commit_filters.py  bug-fix / cosmetic commit classification
    cases.py           mine change cases + exclusion reasons
    szz.py             which changes caused later bug fixes (SZZ)
    labels.py          labels@1.0 (versioned, fixed before training)
    features.py        pre-change features via the live evidence code
    splits.py          chronological + repository-holdout splits
    quality.py         data-quality and leakage report
    build.py           orchestrates everything -> data/dataset/<version>/
  inventory.py       interim component list (until Member 4's parser is plugged in)
  repo_fetcher.py    clone/update + pin snapshot
  pipeline.py        analyze_repository(): everything for one snapshot
  config.py          all tunable numbers
  ids.py             deterministic IDs + path -> component mapping
scripts/
  run_analysis.py         analyze a real repo
  verify_git_history.py   Phase 2 verification
  build_dataset.py        Phase 3 dataset build
  export_schemas.py       regenerate /contracts/schemas after changing app/schema
tests/
corpus.yaml          candidate repositories for experiments
```

Team-wide conventions: [../contracts/CONVENTIONS.md](../contracts/CONVENTIONS.md)
