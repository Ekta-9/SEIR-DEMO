# SEIR — Data & Evolution Handover to the Risk Model (Member 3)

**From:** Member 5 (Data/Evolution + AI Explanation)
**To:** Member 3 (AI/ML — risk prediction)
**Dataset version:** **`v4`** · **Label rules:** `labels@1.0` · **Features:** `features@1.0` · **Contracts:** `1.2.0`
**Updated:** 2026-09-30 (replaces the v1 handover of 2026-09-28)

---

## 0. Your five open items — status

| # | Your item | Status | What to do on your side |
|---|---|---|---|
| 1 | More projects in the training data | ✅ **Done in the official builder (v4)** — your 5 libraries + 2 applications, 9 projects; **jsoup stays sealed** | Switch to `data/dataset/v4/`; retire your own v2 (see §0.1, §0.1b) |
| 2 | Check of the "caused a bug" (SZZ) answers | ⏳ Member 5 reviewing; fresh 30-link sample drawn from **v4**; scoring script ready | Nothing yet — precision + 95 % interval will be shared |
| 3 | Settings-file and live-usage clues | ✅ **Settings: done** (`config_config_reference_count`) · ⏳ **Live usage: Phase 5**, and it will **never** be a historical training column (§0.3) | Nothing — your code picks up the settings column via the manifest |
| 4 | One shared function turning clues into model inputs | ✅ **Done: `seir_features.evidence_to_features`** — the dataset builder now uses it | **Replace your `evidence_to_features` in `predictor.py` with an import** (§10) |
| 5 | How the "reasons" are read | ✅ **Decided: "predicted class"** — written into the contract | Keep your current setting; follow the rule in §11 exactly |

### 0.1 Why one official dataset (and no more "v2" twins)

You extended the corpus in your own copy and called it "v2"; our side also had a v2 (settings column) and v3 (mall). To end the name clash there is now **one builder and one version line**, and **v4 supersedes all of them**:

- your five projects (commons-collections, commons-text, commons-codec, commons-compress, jsoup) are in `seir-evidence/corpus.yaml`;
- every project is **pinned** to the exact commit v4 was built from, so anyone rebuilding v4 gets byte-identical data;
- your finding that more libraries improved generalisation but not accuracy is valuable — please keep it for the report; v4 lets you re-test it with the application repos included.

### 0.1b Response to your "Report for Betterment" (2026-09-30)

| Your point | What we did |
|---|---|
| **jsoup is your sealed, never-evaluated final test** | ✅ v4 marks jsoup as **holdout** (it was accidentally in training in the first v4 build — rebuilt). It is never in train/validation/test. Both holdout projects carry `split = "holdout"`; distinguish them by `repo_id`: **commons-io = already seen once (v1 final)**, **jsoup = sealed**. |
| Your `scripts/build_dataset_v2.py` calls our builder with a list of URLs | ✅ `build_dataset` accepts plain URLs **and** the new `RepoSpec` (cap + pinned commit); a test guards the old call style. |
| Your "v2" folder name clashes with ours | Please rename your copy (e.g. `dataset/m3-v2`). **v4 is the official line** from now on. |
| Rebuilding v1 today | ⚠️ Will **not** reproduce the original v1: the cosmetic filter gained "removed finals" + Chinese keywords, and v1's repositories were not pinned (they moved on). **Keep your existing v1 files** — they remain the record for `logreg-risk@0.1.0`. From v4 on every repository is pinned, so this cannot recur. |
| Shipped model `logreg-risk@0.1.0` | ⚠️ **Incompatible with v4 inputs**: `features@1.0` has 11 columns (settings added) in the shared `FEATURE_COLUMNS` order. Your predictor's mismatch check will (correctly) refuse it — train `0.2.0` on v4. |
| Reasons: you recommended risk-up | **Decision (Member 5 / team lead): keep "predicted class".** Your point about close scores flipping the label is noted — the explainer will state uncertainty when the top two class scores are close, so a fragile label is not presented as firm. Keep `EXPLANATION_TARGET = predicted class`. |
| Temporary code-structure stand-in (your recommendation #1) | Agreed it is the most valuable next experiment. **Whoever builds it: emit `EvidenceItem`s with `source: STATIC`** (types already registered: `dependent_count`, `dependency_count`, `loc`, …) at each case's `parent_sha`, so it flows through `seir_features` (new `FEATURE_SPEC_VERSION`) — not as side columns. Member 5's historical-snapshot reader (`app/dataset/config_history.py`, `app/git_cli.list_tree/read_blobs`) already reads the code at every pre-change commit and can be reused. |
| Your "reliable" targets (HIGH recall ≥ 80–90 %, etc.) | Good framing for the report; v4's balance differs from your v2 (Syncope adds many HIGH cases), so re-measure before comparing. |

### 0.2 Why two *application* projects were added

The seven libraries have **no runtime configuration in their entire history** — the settings column was 0 in every row, so the settings ablation could not be measured. `apache/syncope` and `apache/shiro` are applications whose configuration files name their classes (494 cases with references). `macrozheng/mall` (used briefly in v3) was **dropped**: 2 authors and 72 % "Update X.java" commit messages made its labels unreliable.

### 0.3 Why live usage will not become a training column

Runtime usage can only be recorded by *running* an application now. Nobody can observe how commons-lang executed in 2012, so historical cases can never have runtime values. Runtime evidence will be used (a) live on the dashboard and in explanations and (b) in a separate, small controlled experiment on Spring PetClinic (Phase 5). If a `runtime_*` column is ever added, it will be `NaN` for all historical cases — do not train on it.

---

## 1. Where your module sits

```
   Member 4: code structure          Member 5: Git / config / runtime evidence
                   └──────────────► EvidenceItem ◄─────────┘   (one shared clue format)
                                         │
                                         ▼
                        seir_features.evidence_to_features      ◄── ONE function, both paths
                         │                                 │
             (offline) dataset builder           (live) your predictor
                         │                                 │
                         ▼                                 ▼
                 cases.parquet  ──► YOU: train ──► model ──► RiskAssessment ──► Member 5 explainer
                                                                   │                   │
                                                                   ▼                   ▼
                                                            Member 2 backend ──► Member 1 dashboard
```

Research question your model answers (main report §6.13): **do Git and configuration evidence improve risk prediction over code structure alone?** That is the ablation (§9).

---

## 2. Files

All paths relative to the project root.

| File | What it is |
|---|---|
| `seir-evidence/data/dataset/v4/cases.parquet` | **The training table** — 27,877 rows |
| `seir-evidence/data/dataset/v4/manifest.json` | Column roles, `feature_spec_version`, pinned snapshots, settings |
| `seir-evidence/data/dataset/v4/quality_report.md` / `.json` | Exclusions, class balance, missing rates, leakage checks |
| `seir-evidence/data/dataset/v4/change_cases.jsonl` | Same cases in the shared `ChangeCase` contract |
| `seir-evidence/data/dataset/v4/static_feature_requests.csv` | What Member 4 must compute (13,005 distinct pre-change snapshots) |
| `seir-evidence/data/dataset/v4/szz_review_sample.csv` | 30 SZZ links under manual review |
| `seir-evidence/seir_features/__init__.py` | **The shared evidence → features function** |
| `seir-evidence/docs/DATASET.md` | Short usage guide |
| `contracts/CONVENTIONS.md` · `contracts/schemas/risk_assessment.schema.json` | Contracts, including your output format and the reasons rule |

> ⚠️ `seir-evidence/data/` is git-ignored (large, regenerable). Ask Member 5 for the files, or rebuild — identical output because every repository is pinned:
>
> ```bash
> cd seir-evidence
> python -m venv .venv && .venv/Scripts/activate      # Linux/macOS: source .venv/bin/activate
> pip install -e ".[dev]"
> python -m scripts.build_dataset --version v4          # ~10 minutes; downloads 9 repositories on first run
> ```

---

## 3. What one row means

**One row = one change case:** a *production* Java class that **existed before** a real commit and was **modified or deleted** by it.

- **Features** describe the class *just before* the commit (`as_of` = commit time, exclusive cutoff).
- **Label** describes what *actually happened* at and after the commit.

---

## 4. How the dataset is built (unchanged method, now 9 projects)

1. **History** is read in one `git log` pass per project, following renames, parallel branches and side branches (verified 100 % against independent git queries in Phase 2).
2. **Candidate cases**: every production class that existed and was changed by a non-merge commit.
3. **Exclusions** (all counted in the quality report): bulk commits (> 30 Java files), cosmetic commits (Javadoc, checkstyle, formatting, "removed finals"…, including Chinese equivalents), newly created classes, cherry-picked duplicates, and the last 180 days before each snapshot (right-censoring).
4. **Per-project cap (new):** Syncope alone had 17,270 eligible cases (and 78 % HIGH). It is capped at **5,000**, by sampling **whole commits at random across its whole history** (seed 42) — never half a commit, and the time spread needed for chronological splits is preserved. Counted as `sampled_out_repo_cap: 12,270`.
5. **Labels (`labels@1.0`, unchanged):**

   | Label | Rule |
   |---|---|
   | **HIGH** | caused a later bug fix (SZZ) **or** ≥ 4 other production classes changed in the same commit |
   | **MEDIUM** | 1–3 other production classes changed |
   | **LOW** | none changed and no bug was caused |

6. **Features** via `seir_features.evidence_to_features` — the same function your predictor will use.
7. **Splits:** chronological inside each training project (oldest 70 % / next 15 % / newest 15 %); **two projects held out entirely**: `apache/commons-io` (seen once in the v1 final) and `jhy/jsoup` (**sealed**, never evaluated).

---

## 5. Dataset statistics (v4)

### 5.1 Projects

| Project | Kind | Cases kept | HIGH | Notes |
|---|---|---|---|---|
| apache/commons-lang | library | 4,702 | 28 % | |
| apache/commons-compress | library | 4,845 | 39 % | |
| apache/commons-collections | library | 3,491 | 55 % | |
| jhy/jsoup | library | 2,708 | 38 % | **holdout — sealed** |
| apache/commons-codec | library | 1,408 | 34 % | |
| apache/commons-text | library | 822 | 27 % | |
| **apache/syncope** | **application** | 5,000 (capped) | **78 %** | 358 cases with settings references |
| **apache/shiro** | **application** | 1,837 | 51 % | 136 cases with settings references |
| apache/commons-io | library | 3,064 | 35 % | **holdout** |
| **Total** | | **27,877** | | |

Training split (15,451 rows): Syncope 23 %, commons-compress 22 %, commons-lang 21 %, commons-collections 16 %, Shiro 8 %, commons-codec 6 %, commons-text 4 % — no project dominates.

### 5.2 Labels by split

| Split | Rows | LOW | MEDIUM | HIGH |
|---|---|---|---|---|
| train | 15,451 | 28 % | 22 % | 50 % |
| validation | 3,320 | 31 % | 23 % | 47 % |
| test | 3,334 | 33 % | 25 % | 42 % |
| holdout — commons-io (seen once) | 3,064 | 42 % | 22 % | 35 % |
| holdout — jsoup (**sealed**) | 2,708 | 26 % | 36 % | 38 % |

### 5.3 Where HIGH comes from

| Split | Caused a bug (SZZ) | Spread ≥ 4 | HIGH |
|---|---|---|---|
| train | 7.6 % | 45.4 % | 49.9 % |
| validation | 2.7 % | 44.9 % | 46.6 % |
| test | 3.1 % | 39.6 % | 41.8 % |
| holdout (both) | 5.4 % | 32.4 % | 36.5 % |

Only 3.8 % of cases are HIGH *solely* because of SZZ. Note the lower SZZ rate in validation/test: recent changes have had less time for their bugs to be found (partly handled by the 180-day censoring).

### 5.4 Other facts

- Actions: 27,373 MODIFY, 504 DELETE (1.8 %).
- **No missing values** in any v4 feature.
- Distinct pre-change snapshots: 13,005.

---

## 6. Column dictionary

### 6.1 Identifiers (never features)

`case_id`, `repo_id`, `commit_sha`, `parent_sha`, `as_of`, `target_component_id`, `target_parent_path`, `action`.

### 6.2 Features — exactly `seir_features.FEATURE_COLUMNS` (= `manifest.json → feature_columns`), in this order

| Column | Definition | Range (min / median / max) |
|---|---|---|
| `action_is_delete` | 1 if the proposed change deletes the class; DEPRECATE counts as 0 | 0/1 |
| `git_churn_ratio` | churn in the last 90 days ÷ lifetime churn | 0 / 0.028 / 1 |
| `git_co_change_count` | still-existing classes changed together ≥ 2 times (bulk commits excluded) | 0 / 13 / 189 |
| `git_days_since_last_change` | days since the class last changed | 0 / 13 / 6,137 |
| `git_historical_commit_count` | commits touching the class before `as_of` | 1 / 18 / 737 |
| `git_lines_added` | lifetime lines added | 1 / 478 / 46,214 |
| `git_lines_deleted` | lifetime lines deleted | 0 / 160 / 36,551 |
| `git_recent_commit_count` | commits in the last 90 days | 0 / 2 / 73 |
| `git_total_churn` | added + deleted (≈ collinear with the two above) | 2 / 641 / 82,765 |
| `git_unique_contributors` | distinct author e-mails | 1 / 4 / 98 |
| `config_config_reference_count` | places in **runtime** configuration (Spring XML, `application*.yml/properties`, MyBatis mappers, ServiceLoader, `spring.factories`…) that name the class, at the pre-change snapshot; build-tool and test config not counted | 0 / 0 / 11 — **non-zero only for Syncope/Shiro (494 rows)** |

`NaN` means **unknown**, never zero. None occur in v4, but they will once structural features arrive; XGBoost/LightGBM handle NaN natively, Logistic Regression needs imputation plus a missing-indicator.

### 6.3 Forbidden columns (`manifest.json → forbidden_columns`)

`label_spread`, `label_impacted_test_count`, `label_caused_bug_fix`, `label_fix_commit_count` — post-change facts the label is built from. For analysis only; **never** model inputs.

### 6.4 Target and split

`label` ∈ {LOW, MEDIUM, HIGH}; `split` ∈ {train, validation, test, holdout}.

---

## 7. Leakage protections (all ✅ in the v4 quality report)

No forbidden column used as a feature · unique case IDs · non-negative ages · the change commit is invisible to its own features (build-time guard) · chronological splits · two projects fully held out (jsoup sealed) · 180-day right-censoring.

**On your side:** select features only from the manifest; never shuffle across splits or use random K-fold on the whole table; fit preprocessing on `train`, calibration on `validation`; look at `test` and commons-io once more at most, and at **jsoup exactly once** (your sealed final).

---

## 8. Findings that affect modelling

1. **HIGH is now the largest class in training (50 %)**, driven by Syncope (78 % HIGH) and commons-collections (55 %). MEDIUM is the minority. Keep `class_weight="balanced"` and report macro-F1 and per-class recall.
2. **Project style matters.** HIGH ranges from 27 % (commons-text) to 78 % (Syncope): some teams make many multi-class commits. Consider adding `repo_id` *only* as an analysis grouping (per-project scores), not as a feature — the dashboard must work on unseen projects.
3. **Concept drift is milder than in v1** (validation 47 % HIGH → test 42 %), because nine projects average out one project's workflow change. Report calibration on both validation and test anyway.
4. **Counter-intuitive signal holds across projects:** LOW cases have *more* history (median 29 past commits vs 14 for HIGH; contributors 6 vs 3; co-change 17 vs 11). Heavily maintained hub classes get many small, self-contained changes.
5. **Settings signal is weak on its own.** In Syncope/Shiro the mean number of settings references is almost equal across labels (LOW 0.12, MEDIUM 0.11, HIGH 0.13). Only the ablation can tell whether it helps in combination — report the result either way.
6. **DELETE is rare** (1.8 %). Report per-action performance if possible.
7. **Skewed counts** (4–5 orders of magnitude): irrelevant for trees; `log1p` + standardise for Logistic Regression.

---

## 9. Ablation plan

Same model type, same tuning budget, same v4 splits, same metrics; report every result.

| # | Feature set (by column prefix) | Status |
|---|---|---|
| 1 | Structural only (`static_*`) | ⏳ waiting for Member 4 (`static_feature_requests.csv`) |
| 2 | Structural + Git | ⏳ |
| 3 | Structural + Config | ⏳ |
| 4 | Structural + Git + Config | ⏳ |
| now | **Git only** (`action_is_delete` + `git_*`) | ✅ run today |
| now | **Git + Config** | ✅ run today — meaningful on Syncope/Shiro rows; also report per-project |

Suggested: evaluate the Git vs Git+Config comparison **on the application projects separately** too, because the config column is constant (0) in the seven libraries.

---

## 10. The shared feature function — replace your copy

Your `predictor.py` has its own `evidence_to_features`. Replace it with the shared one so training and prediction can never drift:

```python
from seir_features import FEATURE_COLUMNS, FEATURE_SPEC_VERSION, evidence_to_features, to_vector

row = evidence_to_features(evidence_json_list, action="DELETE")   # evidence for ONE component
x = to_vector(row)                                                # floats in FEATURE_COLUMNS order
proba = model.predict_proba([x])[0]
```

- **Input:** the evidence list exactly as the Evidence Service returns it (JSON dicts), or `EvidenceItem` objects. One component per call; mixing components raises `FeatureError`.
- **Output:** every column in `FEATURE_COLUMNS`; missing or unknown evidence → `NaN`; DEPRECATE is treated as MODIFY.
- **Guarantee:** a test builds evidence on a real git repository and checks that the JSON route (yours) and the object route (dataset builder) give **identical** vectors.
- **Dependency-free:** standard library only. Install the evidence package (`pip install -e path/to/seir-evidence`) or pin it from git; do **not** copy the file (a copy is exactly what drifts).
- **Versioning:** record `FEATURE_SPEC_VERSION` (`features@1.0`) with your trained model and put it in `RiskAssessment.feature_spec_version`. Any column change bumps it.
- Feed the model in `FEATURE_COLUMNS` order (it equals the manifest's `feature_columns`).

---

## 11. Your output contract: `RiskAssessment` (contracts 1.2.0)

```json
{
  "repo_id": "acme/shop",
  "component_id": "com.shop.payment.LegacyPaymentService",
  "action": "DELETE",
  "risk_class": "MEDIUM",
  "class_scores": {"LOW": 0.2, "MEDIUM": 0.55, "HIGH": 0.25},
  "is_calibrated": false,
  "top_features": [
    {"feature": "config_config_reference_count", "value": 2, "contribution": 0.18},
    {"feature": "git_recent_commit_count", "value": 2, "contribution": -0.07}
  ],
  "model_version": "xgb-risk@0.1.0",
  "feature_spec_version": "features@1.0"
}
```

| Field | Rule |
|---|---|
| `class_scores` | one score per class in [0, 1], summing to 1 (± 0.001) |
| `is_calibrated` | `true` only if calibration was fitted and validated — the UI then says "probability", else "model score" |
| `top_features[].feature` | **exact** column name from `FEATURE_COLUMNS` |
| `top_features[].contribution` | **"predicted class" reading** — see below |
| `feature_spec_version` | new, optional; please fill it |

### The reasons rule — "predicted class" (agreed 2026-09-30)

`contribution` is the attribution **for the predicted class `risk_class`** (e.g. that class's SHAP value). **Positive = pushes the prediction towards `risk_class`; negative = pushes away from it.** The explainer turns it into words by class:

| `risk_class` | positive contribution | negative contribution |
|---|---|---|
| HIGH | "raises the risk" | "lowers the risk" |
| MEDIUM | "supports a medium rating" | "argues against a medium rating" |
| LOW | "keeps the risk low" | "points to higher risk" |

So: **do not** switch to risk-up attributions without telling Member 5 — the explainer's wording depends on this rule. Sort `top_features` by absolute contribution, largest first.

Validate in Python:

```python
from app.schema import RiskAssessment
RiskAssessment.model_validate(output_dict)   # clear error if anything is off
```

---

## 12. Live inference flow

1. User selects a class and an action on the dashboard.
2. Backend fetches that class's evidence from the Evidence Service (Phase 6) at the current snapshot.
3. **You** call `evidence_to_features(evidence, action)` → `to_vector` → model.
4. You return a `RiskAssessment`.
5. The explainer receives your `RiskAssessment` plus the evidence and writes the grounded explanation, using the reasons rule above.

Ship the model as one file plus its own manifest (`FEATURE_COLUMNS` order, `feature_spec_version`, label order, `model_version`), and fail loudly if the feature spec does not match.

---

## 13. Verification status and open items

| Item | Status |
|---|---|
| Git feature accuracy / repeatability | ✅ 100 % on comparable cases; identical reruns |
| Leakage checks (5) | ✅ all pass on v4 |
| Automated tests | ✅ 140 passing |
| Shared feature function + JSON/object parity test | ✅ |
| Reproducible dataset (pinned repositories) | ✅ |
| **SZZ precision** (30-link hand review of v4) | ⏳ Member 5; scorer `scripts/evaluate_szz_review.py` ready (prints precision + 95 % interval) |
| **Settings-collector precision/recall** (hand review) | ⏳ Member 5 |
| Structural features | ⏳ Member 4 |
| Runtime evidence (live + PetClinic experiment) | ⏳ Phase 5 — never a historical training column (§0.3) |

---

## 14. Known limitations (cite in your evaluation chapter)

1. **Tangled commits:** "changed in the same commit" is a proxy for "had to change".
2. **SZZ is heuristic** (keyword-based fix detection, cannot trace add-only fixes); precision being measured.
3. **Label thresholds** (≥ 4 / ≥ 1) are fixed operational definitions, not ground truth.
4. **Label-side time overlap:** a training label may use a fix from the test period; features never do.
5. **Scope:** nine Java projects (seven libraries, two applications), mostly Apache; results may not transfer to other languages or to closed-source teams.
6. **Syncope is sampled** (5,000 of 17,270 cases); the sampling rule and seed are recorded.
7. One person with two e-mail addresses counts as two contributors; commit timestamps define the cutoff (rare clock skew).

---

## 15. How to request changes

- **New feature / definition change:** ask Member 5 — it goes into `seir_features` (new `FEATURE_SPEC_VERSION`) and a new dataset version.
- **Label thresholds:** only as a new rule version agreed by the team, never to raise scores.
- **Reasons rule:** changing it requires Member 5 to update the explainer at the same time.
- **Dataset versions:** one official line (v4, v5…), built by `scripts/build_dataset.py` from `corpus.yaml`; each has its own manifest and quality report.

---

## 16. Glossary

| Term | Meaning |
|---|---|
| Change case | One production class modified or deleted in one real commit |
| `as_of` | The cutoff; only information strictly before it is used for features |
| Spread | Other production classes changed in the same commit |
| SZZ | Links bug-fix commits back to the commits that introduced the bug, via `git blame` |
| Right-censoring | Recent changes whose consequences cannot be observed yet; excluded |
| Leakage | Information from after the change reaching the model |
| Ablation | Adding/removing one evidence family at a time to measure its value |
| Training/serving skew | Features computed differently in training than in prediction — prevented by `seir_features` |
| Predicted-class attribution | A reason's number says how much it pushed the prediction towards the class that was predicted |
