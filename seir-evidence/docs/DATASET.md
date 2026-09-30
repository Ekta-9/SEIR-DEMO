# SEIR Risk Dataset — Guide for the ML module

**Owner:** Member 5 (Data/Evolution) · **Label rules:** `labels@1.0` · **Build:** `python -m scripts.build_dataset --version v1`

Numbers (case counts, class balance, missing rates) are in `data/dataset/<version>/quality_report.md`, generated with every build. This guide explains what the columns mean and how to use them without leaking information.

## 1. What one row is

One **change case**: a production Java class that existed before a real historical commit and was modified or deleted by it.

- The **features** describe the class *just before* the commit (`as_of` = commit time, exclusive).
- The **label** describes what *actually happened* at and after the commit.

## 2. Columns

| Group | Columns | Use for training? |
|---|---|---|
| IDs | `case_id`, `repo_id`, `commit_sha`, `parent_sha`, `as_of`, `target_component_id`, `target_parent_path`, `action` | ❌ identifiers only |
| Features | listed in `manifest.json → feature_columns` (`action_is_delete`, `git_*`) | ✅ |
| **Forbidden** | `label_spread`, `label_impacted_test_count`, `label_caused_bug_fix`, `label_fix_commit_count` | ⛔ **never** — these are post-change facts the label is built from |
| Label | `label` ∈ {LOW, MEDIUM, HIGH} | 🎯 target |
| Split | `split` ∈ {train, validation, test, holdout} | how to evaluate |

Always select features from `manifest.json["feature_columns"]` rather than "all numeric columns" — that is what keeps the forbidden columns out.

Column naming rule: every feature from evidence is `<source>_<evidence_type>` (`git_recent_commit_count`, `config_config_reference_count`, later `static_…`, `runtime_…`), so an ablation run is a filter on the column prefix.

**v2** adds `config_config_reference_count`: the number of places in **runtime** configuration (Spring XML, `application*.yml/properties`, MyBatis mappers, ServiceLoader, `spring.factories`…) that name the class, at the pre-change snapshot. Build-tool and test configuration are not counted. In the two Apache libraries it is **0 for every row** (libraries have no runtime configuration).

**v4 (current, recommended)** — 9 projects, 27,877 cases: commons-lang, commons-io (holdout), commons-collections, commons-text, commons-codec, commons-compress, jsoup, plus the applications `apache/syncope` (capped at 5,000 cases by sampling whole commits) and `apache/shiro`. `macrozheng/mall` was dropped (unreliable labels). Every repository is pinned (`ref` in `corpus.yaml`), so v4 rebuilds identically. Features are produced by the shared `seir_features.evidence_to_features` — use it for predictions too. Full handover: `../member 3 report.md`.

*(Historical)* **v3** added `macrozheng/mall`, a Spring Boot application whose MyBatis XML mappers name Java classes: 1,185 more training/validation/test cases, 226 of them with configuration references, so the configuration ablation has real signal. Training data now spans two repositories (no single repository > 60 %). Caveat: 72 % of mall's commit subjects are "Update X.java", so SZZ finds few bug fixes there (1.9 % of mall cases vs 5–7 % in Apache) — mall's HIGH labels come almost entirely from spread.

`NaN` means **unknown**, not zero (e.g. `git_churn_ratio` when total churn is 0). Tree models (XGBoost/LightGBM) handle NaN natively; for Logistic Regression impute *and* add a missing-indicator column.

## 3. How labels are made (`labels@1.0`, fixed before any training)

| Label | Rule |
|---|---|
| **HIGH** | The change later needed a bug fix (SZZ), **or** it spread to ≥ 4 other production classes |
| **MEDIUM** | It spread to 1–3 other production classes |
| **LOW** | It spread to no other production class and caused no bug |

- **Spread** = other production classes that existed before and changed in the same commit. Test classes are excluded (writing tests alongside a change is normal, not impact).
- **Caused a bug (SZZ):** a later commit whose subject marks it as a bug fix changed lines that `git blame` attributes to this commit, in this class.

**Excluded** (each counted in the quality report): root commits, cherry-picked duplicates, bulk commits (> 30 Java files), cosmetic commits (Javadoc/checkstyle/formatting…), newly created classes (no "before" state), and changes in the last 180 days before the snapshot (a bug they caused may not be found yet — right-censoring).

## 4. How to evaluate

| Split | Meaning | Use |
|---|---|---|
| `train` | oldest 70 % of each repo's changes | fit models |
| `validation` | next 15 % | model selection / hyper-parameters / calibration |
| `test` | newest 15 % | report once, at the end |
| `holdout` | every case of a repository never seen in training (`apache/commons-io`) | report once: generalization to an unseen project |

- **Do not shuffle across splits** or use random K-fold on the whole table: nearby commits of the same repo are near-duplicates, and mixing them inflates scores. If you need CV inside `train`, use time-ordered folds (e.g. `TimeSeriesSplit`) grouped by `commit_sha`.
- Classes are imbalanced → report **macro F1** and per-class recall, not only accuracy; consider `class_weight="balanced"`.

## 5. Structural (STATIC) features — pending Member 4

The ablation needs code-structure features (dependents, graph depth, LOC, complexity) **at the parent commit** of every case. `static_feature_requests.csv` lists exactly what is needed:

| Column | Meaning |
|---|---|
| `parent_sha` | check out / read this commit |
| `target_component_id`, `target_parent_path` | the class, and where its file was at that commit |
| `as_of` | use as the evidence `as_of` |

Member 4 returns them as `EvidenceItem`s (`source: STATIC`, `snapshot: parent_sha`, `as_of: as_of`) — see `contracts/CONVENTIONS.md` — and the dataset build will join them as `static_*` columns. Tip: many cases share the same `parent_sha`; group by it and parse each snapshot once.

## 6. Known limitations (state these in the report)

1. "Changed in the same commit" ≠ "had to change" — developers sometimes bundle unrelated edits (tangled commits).
2. SZZ is heuristic: keyword-based fix detection misses fixes without fix words, and fixes that only *add* lines cannot be traced.
3. Label thresholds (4 / 1) are operational choices fixed before training, not ground truth about "risk".
4. A training case's label may use fix commits that happened during the test period; features never do.
