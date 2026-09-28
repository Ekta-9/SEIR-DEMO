# SEIR — Data & Evolution Handover to the Risk Model (Member 3)

**From:** Member 5 (Data/Evolution + AI Explanation)
**To:** Member 3 (AI/ML — risk prediction)
**Dataset version:** `v1` · **Label rules:** `labels@1.0` · **Built:** 2026-09-28
**Status:** Ready for model development. Structural (STATIC) features pending from Member 4; SZZ hand-review in progress.

---

## 0. TL;DR

- You have a **real, labelled, leakage-checked dataset of 7,808 change cases** mined from the Git history of `apache/commons-lang` and `apache/commons-io`.
- Each row = *"a production Java class was modified or deleted in a real commit"*. **Features** describe the class **just before** the commit. The **label** (LOW / MEDIUM / HIGH) describes **what actually happened** at and after the commit.
- Splits are already assigned: **chronological** train / validation / test inside commons-lang, and **all of commons-io held out** as an unseen-project test.
- `manifest.json` tells you exactly which columns are **features**, which is the **label**, and which are **forbidden** (post-change facts the label is built from). Use it — do not select "all numeric columns".
- Your model's output must follow the shared **`RiskAssessment`** contract (§11) so the backend, dashboard and explainer can consume it.
- Important findings that affect modelling: **class imbalance**, **strong concept drift** between the validation and test periods, heavily **skewed** count features, and **training currently comes from one repository** (§8).

---

## 1. Where your module sits

```
                   ┌──────────────── Git repository (Java) ────────────────┐
                   │                                                       │
   Member 4: code structure (AST, graph)      Member 5: Git / config / runtime evidence
                   │                                       │
                   └──────────────► EvidenceItem ◄─────────┘   (one shared clue format)
                                         │
                ┌────────────────────────┼─────────────────────────────┐
                │ (history, offline)     │ (live, per request)          │
                ▼                        ▼                              │
   Phase 3 dataset builder     Evidence for the component               │
   cases.parquet + labels      the user selected                        │
                │                        │                              │
                ▼                        ▼                              │
        YOU: train model  ──────►  YOU: predict ──► RiskAssessment ──► Member 5 explainer
                                                          │                    │
                                                          ▼                    ▼
                                                   Member 2 backend  ──►  Member 1 dashboard
```

Two things connect us:

1. **Training data (offline):** the dataset described in this report.
2. **Inference (live):** at prediction time you receive the *same* features, computed by the *same* code, for the component the user picked (§10). No re-implementation of feature logic on your side is needed.

The research question your model helps answer (main report §6.13, Data report §14): **do Git / configuration / runtime evidence improve risk prediction over code structure alone?** That is the ablation study (§9).

---

## 2. Where the files are

All paths are relative to the project root (`D:\SEIR`).

| File | What it is |
|---|---|
| `seir-evidence/data/dataset/v1/cases.parquet` | **The training table** (7,808 rows × 24 columns) |
| `seir-evidence/data/dataset/v1/manifest.json` | Column roles (features / label / forbidden / ids / split), settings, repo snapshots |
| `seir-evidence/data/dataset/v1/quality_report.md` / `.json` | Exclusion counts, class balance, missing rates, leakage checks |
| `seir-evidence/data/dataset/v1/change_cases.jsonl` | Same cases in the shared `ChangeCase` contract (includes impacted classes + fix commits) |
| `seir-evidence/data/dataset/v1/static_feature_requests.csv` | What Member 4 must compute for the structural features |
| `seir-evidence/data/dataset/v1/szz_review_sample.csv` | 30 bug-cause links being hand-verified |
| `seir-evidence/docs/DATASET.md` | Short usage guide (this report is the long version) |
| `contracts/CONVENTIONS.md`, `contracts/schemas/risk_assessment.schema.json` | Shared contracts, including **your output format** |

> ⚠️ `seir-evidence/data/` is **git-ignored** (large, regenerable). You will not get it from a `git pull`. Either ask me for the files, or regenerate them yourself (identical output — the build is deterministic):
>
> ```bash
> cd seir-evidence
> python -m venv .venv && .venv/Scripts/activate      # Linux/macOS: source .venv/bin/activate
> pip install -e ".[dev]"
> python -m scripts.build_dataset --version v1          # ~1 minute; clones the repos on first run
> ```

---

## 3. What one row means — with real examples

**One row = one change case:** a *production* (non-test) Java class that **existed before** a real commit and was **modified or deleted** by it.

Two real rows from the test split:

| Column | Row A | Row B |
|---|---|---|
| `target_component_id` | `org.apache.commons.lang3.Validate` | `org.apache.commons.lang3.RandomStringUtils` |
| `commit_sha` (the change) | `e9d7d350…` | `bd247e45…` |
| `as_of` (feature cutoff = commit time) | 2026-03-21 | 2026-03-17 |
| `action` | MODIFY | MODIFY |
| `git_historical_commit_count` | 108 | 116 |
| `git_recent_commit_count` (90 d) | 1 | 2 |
| `git_days_since_last_change` | 79 | 56 |
| `git_unique_contributors` | 22 | 28 |
| `git_co_change_count` | 45 | 58 |
| `label_spread` *(forbidden)* | 0 other classes changed | 0 other classes changed |
| `label_caused_bug_fix` *(forbidden)* | False | **True** — a later bug fix traced back to this change |
| **`label`** | **LOW** | **HIGH** |

Row B is HIGH even though nothing else changed with it, because **SZZ** (§4.4) traced a later bug fix back to this exact change in this exact class.

---

## 4. How the dataset was built

### 4.1 Reading history correctly

History is read with a single `git log --numstat` pass per repository (seconds, not minutes), then indexed so features can be computed **as of any point in time**. Several correctness problems were found on real repositories and fixed, each now guarded by a test that fails without the fix:

| Problem found | Effect if unfixed | Fix |
|---|---|---|
| Renamed / moved classes | History "starts over" at the rename | Renames are followed back through all history |
| Edits on a parallel branch to a file renamed on another branch | Commits attributed to a "dead" class | Rename chains resolved across the whole commit graph |
| Git's default *history simplification* | Real commits silently missing | `--full-history` |
| Co-change partners that were deleted years ago | Inflated `co_change_count` | Only partners still alive at the cutoff count |
| `package-info.java` treated as a class | Invalid component | Excluded by a shared rule |

**Verification (Phase 2):** feature values were compared with an independent per-file `git log` on 2 repositories → **100 % agreement** on all comparable cases (315 checks), **no component ever under-counted** (656/656), and **two runs produce byte-identical output**.

### 4.2 Mining candidate cases

For every non-merge commit touching Java code, every **production** class that **existed before** the commit and was changed becomes a candidate. Test classes are never targets (their "risk" is not what the dashboard asks about).

### 4.3 Exclusions (every one counted)

| Reason | commons-lang | commons-io | Why excluded |
|---|---|---|---|
| `bulk_commit` (> 30 Java files) | 3,716 | 2,651 | Mass edits (initial imports, reformatting, package moves): "spread" is meaningless |
| `cosmetic_commit` | 2,706 | 2,043 | Javadoc / checkstyle / formatting / typo commits: no behavioural change |
| `new_component` | 430 | 323 | The class was *created* in the commit — there is no "before" |
| `censored_recent_change` | 244 | 62 | Last 180 days before the snapshot: bugs they caused may not be found yet (**right-censoring**) |
| `duplicate_commit` | 18 | 4 | Cherry-picked copies of the same patch (`git patch-id`) |
| **Kept** | **4,708** of 11,822 | **3,100** of 8,183 | |

The cosmetic filter uses **phrases**, not single words, after reviewing real commit messages: e.g. *"[LANG-1637] Fix 2 digit week year formatting"* is a real bug fix and is **kept**, while *"Fix formatting"* is excluded. Real commit subjects are used as regression tests.

### 4.4 Labels — `labels@1.0` (fixed before any training)

Two post-change signals are measured:

1. **Spread** (`label_spread`) = number of **other production classes that existed before and changed in the same commit**. Test classes are excluded (writing tests with a change is normal, not impact). This is the standard *change-propagation* proxy.
2. **Caused a bug** (`label_caused_bug_fix`) via the **SZZ algorithm** (Śliwerski, Zimmermann & Zeller, 2005):
   - find later **bug-fix commits** (subject mentions fix/bug/regression/broken/wrong… and is not cosmetic);
   - take the lines each fix **deleted or modified** (ignoring whitespace, comments, blank lines, imports);
   - `git blame` those lines on the fix's parent → the commit that last wrote them **introduced the bug**;
   - that (commit, class) pair is marked as bug-inducing.

| Label | Rule |
|---|---|
| **HIGH** | caused a later bug fix **or** spread ≥ 4 |
| **MEDIUM** | spread 1–3 |
| **LOW** | spread 0 and caused no bug |

These thresholds are a **versioned definition**, not tuning parameters. They must **not** be changed to improve model scores; any change means a new `labels@x.y` and a rebuilt dataset.

### 4.5 Features

Features are produced by `build_git_evidence(...)` — **the same function the live service uses** — then flattened to columns. This rules out *training/serving skew* (training on numbers computed differently from what the model sees in production).

Every feature is computed with `as_of = commit time` as an **exclusive cutoff**: the change itself and everything after it are invisible. A guard raises an error during the build if any feature can see the change commit or later commits; the build completed, so the guard passed for every row.

### 4.6 Splits

| Split | Rows | Period | Purpose |
|---|---|---|---|
| `train` | 3,295 | commons-lang, 2002-07 → 2020-06 | fitting |
| `validation` | 706 | commons-lang, 2020-06 → 2023-07 | model selection, early stopping, calibration, threshold choices |
| `test` | 707 | commons-lang, 2023-07 → 2026-03 | **final** temporal generalisation — report once |
| `holdout` | 3,100 | all of commons-io, 2002 → 2026 | **final** unseen-project generalisation — report once |

Cut points are **times**, so all cases from one commit always fall into the same split.

---

## 5. Dataset statistics

### 5.1 Label distribution

| | LOW | MEDIUM | HIGH | Total |
|---|---|---|---|---|
| **All** | 3,761 (48 %) | 1,589 (20 %) | 2,458 (31 %) | 7,808 |
| train | 1,711 (52 %) | 602 (18 %) | 982 (30 %) | 3,295 |
| validation | 287 (41 %) | 146 (21 %) | 273 (39 %) | 706 |
| test | 462 (65 %) | 162 (23 %) | 83 (12 %) | 707 |
| holdout (commons-io) | 1,301 (42 %) | 679 (22 %) | 1,120 (36 %) | 3,100 |

### 5.2 Where HIGH comes from

| Split | Caused a bug (SZZ) | Spread ≥ 4 | HIGH |
|---|---|---|---|
| train | 6.9 % | 23.2 % | 30 % |
| validation | 2.3 % | 36.7 % | 39 % |
| test | 4.2 % | 7.8 % | 12 % |
| holdout | 5.2 % | 31.6 % | 36 % |

Only **5.1 %** of all cases are HIGH *solely* because of SZZ; the rest of HIGH comes from spread. SZZ's flag rate (2–7 %) is in the typical range reported in defect-prediction research.

### 5.3 Other facts

- Actions: **7,652 MODIFY, 156 DELETE** (2 %).
- **No missing values** in v1 features (every kept case has prior history by construction; total churn is always > 0 because class creation adds lines).
- Distinct pre-change snapshots (`parent_sha`): **4,924**.

---

## 6. Column dictionary

### 6.1 Identifiers (never use as features)

| Column | Meaning |
|---|---|
| `case_id` | `repo@shortsha:ComponentId`, unique |
| `repo_id` | `owner/name` |
| `commit_sha` | the change being labelled |
| `parent_sha` | the pre-change snapshot the features describe |
| `as_of` | feature cutoff (UTC) = the change's commit time; exclusive |
| `target_component_id` | fully qualified class name |
| `target_parent_path` | file path of the class at `parent_sha` |
| `action` | `MODIFY` or `DELETE` (string version of `action_is_delete`) |

### 6.2 Features (`manifest.json → feature_columns`)

All Git features use **only commits strictly before `as_of`**, follow renames, and exclude merge commits.

| Column | Definition | Unit | Range in v1 (min / median / max) | Notes |
|---|---|---|---|---|
| `action_is_delete` | 1 if the proposed change deletes the class | 0/1 | — | Known before the change (it *is* the question being asked) |
| `git_recent_commit_count` | commits touching the class in the 90 days before `as_of` | commits | 0 / 2 / 62 | |
| `git_historical_commit_count` | all commits touching the class before `as_of` | commits | 1 / 31 / 737 | very skewed |
| `git_days_since_last_change` | days since the last commit touching the class | days | 0 / 11 / 2,030 | skewed |
| `git_unique_contributors` | distinct author e-mails | authors | 1 / 7 / 98 | one person with two e-mails counts twice |
| `git_lines_added` | lifetime lines added | lines | 24 / 845 / 46,214 | very skewed |
| `git_lines_deleted` | lifetime lines deleted | lines | 0 / 321 / 36,551 | very skewed |
| `git_total_churn` | added + deleted | lines | 24 / 1,157 / 82,765 | ≈ collinear with the two above |
| `git_churn_ratio` | churn in last 90 days ÷ lifetime churn | ratio | 0 / 0.014 / 1.0 | NaN if lifetime churn = 0 (none in v1) |
| `git_co_change_count` | other classes (still alive) changed together with this one ≥ 2 times, excluding bulk commits | classes | 0 / 16 / 189 | historical coupling |

**Missing values:** `NaN` means **unknown**, never zero. None occur in v1's Git features, but structural and runtime features (coming) will have genuine gaps. XGBoost/LightGBM handle NaN natively; for Logistic Regression impute **and** add a `<feature>_missing` indicator.

### 6.3 Forbidden columns (`manifest.json → forbidden_columns`)

| Column | Meaning | Why forbidden |
|---|---|---|
| `label_spread` | other production classes changed in the same commit | the label is computed from it |
| `label_impacted_test_count` | test classes changed in the same commit | post-change information |
| `label_caused_bug_fix` | SZZ found a later fix caused by this change | the label is computed from it |
| `label_fix_commit_count` | number of such fixes | the label is computed from it |

They are kept in the table **only** for analysis (e.g. error analysis, regression experiments on spread). Any model trained with them will look excellent and be worthless.

### 6.4 Target and split

| Column | Values |
|---|---|
| `label` | `LOW`, `MEDIUM`, `HIGH` |
| `split` | `train`, `validation`, `test`, `holdout` |

---

## 7. Leakage protections already in place

| Protection | How |
|---|---|
| No future information in features | Exclusive `as_of` cutoff + build-time guard that the change commit is invisible to its own features |
| Label independent of features | Labels come from the change commit and later history; features only from earlier history |
| No post-change columns as features | Listed as `forbidden_columns` in the manifest; a quality check asserts no overlap |
| No duplicate cases | `case_id` uniqueness check; cherry-picked duplicates removed |
| Temporal splits | Chronological cut points; check that every train case precedes every validation case, and so on |
| Unseen project test | commons-io fully held out |
| Right-censoring | Last 180 days dropped so "no bug yet" is not mislabelled as "no bug" |

**What you must still do on your side:**

1. Select features **only** from `manifest["feature_columns"]`.
2. **Never shuffle across splits**, and do not use random K-fold on the whole table (near-identical cases from neighbouring commits would leak).
3. Fit every preprocessing step (scalers, imputers, encoders, calibrators) on `train` only (calibrators: on `validation`).
4. Look at `test` and `holdout` **once**, at the end.

---

## 8. Findings that affect your modelling

1. **Class imbalance.** MEDIUM is the minority (≈ 20 %). Use `class_weight="balanced"` (or sample weights) and report **macro-F1** and **per-class recall**, not only accuracy.
2. **Strong concept drift.** Large multi-class changes fall from 37 % (validation period) to 8 % (test period); HIGH falls from 39 % to 12 %. commons-lang moved to small, focused GitHub pull requests in recent years. Expect **lower test scores than validation scores**. That is a genuine research finding to report, not a modelling failure. It also means probability calibration fitted on validation may be off for test — report calibration on both.
3. **Skewed counts.** Churn and commit counts span 4–5 orders of magnitude. Irrelevant for trees; for Logistic Regression apply `log1p` and standardise.
4. **Collinearity.** `git_total_churn = git_lines_added + git_lines_deleted`. Fine for trees; for LR drop one, or rely on regularisation, and do not interpret LR coefficients of collinear features.
5. **Counter-intuitive signal.** LOW cases have *more* history than HIGH (median 42 vs 21 past commits; co-change 21 vs 13). Heavily maintained "hub" classes (e.g. `StringUtils`) receive many small, self-contained changes. Good material for the SHAP discussion.

   | Median by label | LOW | MEDIUM | HIGH |
   |---|---|---|---|
   | historical commits | 42 | 25 | 21 |
   | days since last change | 5 | 14 | 26 |
   | contributors | 8 | 6 | 6 |
   | total churn | 1,952 | 916 | 644 |
   | co-change partners | 21 | 13 | 13 |

6. **DELETE is rare** (156 cases). The model will learn little about deletions specifically; report per-action performance if possible.
7. **Training uses one repository.** With commons-io held out, all training data is commons-lang. Holdout results therefore measure true cross-project generalisation, but the training distribution is narrow. Adding 2–3 more Java projects (e.g. `apache/commons-collections`, `apache/commons-text`, `jhy/jsoup`) to training is proposed; it costs about a minute of build time each and produces `v2`.

---

## 9. Recommended modelling plan

This follows the main project report (§6.5–6.13) and the Data & Evolution report (§13–18).

### 9.1 Required baseline (non-ML)

The main report requires a transparent **rule-based score** to compare against (§6.5). For example: standardise each feature on `train`, combine with fixed weights of plausible sign (e.g. more co-change → higher risk), then map to LOW/MEDIUM/HIGH with two thresholds chosen on `validation`.

It must use **features only** — the label rules cannot be used as a baseline, because spread and SZZ are post-change information.

### 9.2 Candidate models

| Model | Why | Notes |
|---|---|---|
| Logistic Regression (multinomial) | Interpretable baseline | `log1p` + standardise, `class_weight="balanced"` |
| Random Forest | Robust non-linear baseline, native feature importance | Few hyper-parameters |
| XGBoost / LightGBM | Strongest for tabular data | Handles NaN (needed once STATIC/RUNTIME features arrive); tune on validation with early stopping |

A neural network is **not** justified at this data size (main report §6.6).

### 9.3 Cross-validation inside `train` (optional)

Use time-ordered folds grouped by commit. For example:

```python
import json
import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

DATA = "seir-evidence/data/dataset/v1"
manifest = json.load(open(f"{DATA}/manifest.json"))
df = pd.read_parquet(f"{DATA}/cases.parquet")

FEATURES = manifest["feature_columns"]          # never "all numeric columns"
LABEL = manifest["label_column"]
CLASSES = ["LOW", "MEDIUM", "HIGH"]

train = df[df[manifest["split_column"]] == "train"].sort_values("as_of")
commits = train["commit_sha"].drop_duplicates().to_numpy()   # already in time order

for fit_idx, val_idx in TimeSeriesSplit(n_splits=5).split(commits):
    fit = train[train["commit_sha"].isin(commits[fit_idx])]
    val = train[train["commit_sha"].isin(commits[val_idx])]
    # model.fit(fit[FEATURES], fit[LABEL]); evaluate on val ...
```

### 9.4 Final evaluation

Fit on `train`, select and calibrate on `validation`, then report **once** on:

- `test` — temporal generalisation within a project;
- `holdout` — generalisation to an unseen project.

| Metric | Why |
|---|---|
| Macro precision / recall / F1 | Imbalanced classes |
| Per-class recall, especially HIGH | Missing a HIGH-risk change is the costly error |
| Confusion matrix | Which classes are confused |
| Calibration (reliability diagram, Brier score / ECE) | Required before the UI may call scores "probabilities" |
| Comparison with the rule-based baseline | Main research requirement |

Where the sample allows, add **confidence intervals** (bootstrap over commits, not over rows) and **paired comparisons** between models on the same cases (Data report §16).

### 9.5 Calibration and `is_calibrated`

If you calibrate (e.g. `CalibratedClassifierCV` with isotonic or sigmoid on `validation`) **and** verify it on test/holdout, set `is_calibrated: true`; the UI may then say "probability". Otherwise set `false`; the UI will say "model score" (main report §14.5).

### 9.6 Explainability

Provide per-prediction **SHAP** values for tree models (TreeSHAP). The top contributions go into `top_features` of your output (§11). My explainer turns them into plain English and links each one back to its evidence item, so use the exact feature column names.

---

## 10. The ablation study — how we run it together

The central research experiment (main report §6.13, Data report §14): train the **same model** on the **same splits**, adding one evidence family at a time.

| # | Feature set | Columns | Status |
|---|---|---|---|
| 1 | Structural only | `static_*` | ⏳ waiting for Member 4 |
| 2 | Structural + Git | `static_*` + `git_*` | ⏳ |
| 3 | Structural + Config | `static_*` + `config_*` | ⏳ Phase 4 (me) |
| 4 | Structural + Runtime | `static_*` + `runtime_*` | ⏳ Phase 5 (me), available for fewer repos |
| 5–8 | Remaining combinations, full set | | ⏳ |
| now | **Git only** | `action_is_delete` + `git_*` | ✅ **you can start today** |

Every feature family follows the same naming rule: `<source>_<evidence_type>` (`git_…`, `static_…`, `config_…`, `runtime_…`). An ablation run is therefore just a filter on the column prefix.

**Rules for a valid ablation:** identical splits, identical model type and tuning budget, identical metrics, and results reported **even when an evidence family does not help** (Data report §14).

**How structural features will arrive.** `static_feature_requests.csv` lists, for each case, the `parent_sha` and the class's path at that snapshot. Member 4 returns `EvidenceItem`s (`source: STATIC`, `snapshot: parent_sha`, `as_of: as_of`). The next dataset version joins them as `static_*` columns — no change on your side beyond using the new manifest.

**Suggested start:** build the full training/evaluation pipeline now on the Git-only set, parameterised by a list of feature prefixes. When `static_*` arrives, the ablation becomes a loop.

---

## 11. Your output contract: `RiskAssessment`

Defined in `seir-evidence/app/schema/risk.py`, exported as `contracts/schemas/risk_assessment.schema.json`, example in `contracts/examples/risk_assessment.json`.

```json
{
  "repo_id": "spring-projects/spring-petclinic",
  "component_id": "org.springframework.samples.petclinic.owner.OwnerController",
  "action": "DELETE",
  "risk_class": "MEDIUM",
  "class_scores": {"LOW": 0.20, "MEDIUM": 0.55, "HIGH": 0.25},
  "is_calibrated": false,
  "top_features": [
    {"feature": "git_co_change_count", "value": 30, "contribution": 0.18},
    {"feature": "git_recent_commit_count", "value": 1, "contribution": -0.07}
  ],
  "model_version": "xgb-risk@0.1.0"
}
```

| Field | Rule (validated automatically) |
|---|---|
| `risk_class` | `LOW` / `MEDIUM` / `HIGH` |
| `class_scores` | one score per class, each in [0, 1], **summing to 1** (± 0.001) |
| `is_calibrated` | `true` **only** if calibration was fitted and validated (§9.5) |
| `top_features[].feature` | **exact** dataset column name, so the explainer can map it to evidence |
| `top_features[].contribution` | signed attribution (e.g. SHAP); positive pushes towards the predicted risk |
| `model_version` | `name@semver`; bump on every retrain |
| Unknown fields | rejected (the contract forbids extra fields) |

If you work in Python you can validate directly:

```python
import sys
sys.path.insert(0, "seir-evidence")
from app.schema import RiskAssessment

RiskAssessment.model_validate(my_output_dict)   # raises with a clear message if anything is wrong
```

Otherwise validate against the JSON Schema file.

---

## 12. How live inference will work

At prediction time the flow is:

1. The user selects a component and an action on the dashboard.
2. The backend asks my Evidence Service (Phase 6) for that component's evidence at the **current snapshot** (`as_of` = just after the latest commit).
3. The evidence is flattened with **the same code** as the dataset: each `EvidenceItem` becomes the column `<source lowercased>_<evidence_type>`, e.g. `GIT` + `recent_commit_count` → `git_recent_commit_count`. Items with availability `UNKNOWN` or `UNAVAILABLE` become `NaN`.
4. `action_is_delete` = 1 if the user chose DELETE, else 0.
5. Your model predicts → `RiskAssessment`.
6. My explainer receives the `RiskAssessment` **and** the evidence, and writes the grounded explanation.

Two points to agree on:

- **DEPRECATE** has no training examples (history has no reliable "deprecation" signal). Proposal: treat it as MODIFY (`action_is_delete = 0`) and let the UI state this.
- **Packaging:** ship the trained model as one file (e.g. `joblib`/`json` for XGBoost) plus its manifest (feature list and order, `model_version`, label order), so the service can load it and fail loudly if the feature list does not match.

---

## 13. Verification status and open items

| Item | Status |
|---|---|
| Git feature accuracy vs independent git queries | ✅ 100 % on comparable cases, 2 repos |
| Repeatability (same input → identical output) | ✅ |
| Leakage checks (5) | ✅ all pass |
| Automated tests (collectors + dataset) | ✅ 76 passing |
| Cosmetic / bug-fix commit filters | ✅ reviewed on real commit messages; regression-tested |
| **SZZ precision** (hand-review of 30 links) | ⏳ in progress (Member 5). One false-positive pattern already found and fixed (92 false links removed). |
| **Structural features** | ⏳ Member 4 |
| Configuration features | ⏳ Phase 4 (Member 5) |
| Runtime features | ⏳ Phase 5 (Member 5); only for repos we can run |
| More training repositories (`v2`) | 💬 proposed (§8.7) |

---

## 14. Known limitations — please cite in your evaluation chapter

1. **Tangled commits:** "changed in the same commit" does not always mean "had to change"; developers sometimes bundle unrelated edits. Spread is a proxy for impact.
2. **SZZ is heuristic:** keyword-based fix detection misses fixes without fix words, and fixes that only *add* lines cannot be traced to an inducing change.
3. **Label thresholds** (≥ 4, ≥ 1) are operational definitions fixed in advance, not ground truth about "risk".
4. **Label-side time overlap:** a training case's label may depend on a fix that happened during the test period. Features never do.
5. **Generalisation scope:** two Apache Java libraries; results may not transfer to other languages, application code, or other development styles.
6. **Author identity:** one person using two e-mail addresses counts as two contributors.
7. **Commit timestamps** define the cutoff; rare clock skew can misplace a commit slightly.

---

## 15. How to request changes

- **New feature or definition change:** ask me — features are produced by the shared evidence code so that training and serving stay identical. Do not re-derive Git features yourself.
- **Different label thresholds:** only as a new rule version (`labels@1.1`) agreed with the team, and never motivated by model scores.
- **New dataset version:** I rebuild (≈ 1 minute) and bump the version (`v2`, …). Every version has its own manifest and quality report, so results always cite a specific data version.

---

## 16. Glossary

| Term | Meaning |
|---|---|
| Change case | One production class modified or deleted in one real commit |
| `as_of` | The cutoff moment; only information strictly before it is used for features |
| Spread | Other production classes that changed in the same commit |
| SZZ | Algorithm that links bug-fix commits back to the commits that introduced the bug, via `git blame` |
| Right-censoring | Recent changes whose consequences cannot be observed yet; excluded |
| Leakage | Information from after the change reaching the model; makes scores look good and meaningless |
| Concept drift | The relationship between features and labels changes over time |
| Holdout | A whole repository never used for training |
| Ablation | Adding or removing one evidence family at a time to measure its value |
| Training/serving skew | Features computed differently in training than in production |
| Calibration | Whether a score of 0.8 is correct about 80 % of the time |
