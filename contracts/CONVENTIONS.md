# SEIR Data Contracts & Conventions — v1.2.0

> **Changelog** — **1.2.0**: `RiskAssessment.top_features[].contribution` is read for the **predicted class** (rule in §4); `feature` must be an exact column from `seir_features.FEATURE_COLUMNS`; new optional `feature_spec_version`. Features for the risk model are produced **only** by the shared `seir_features.evidence_to_features`.
> **1.1.0** (additive): `config_reference` items may occur several times per component, so their `evidence_id` also hashes the provenance file locations (rule 4). `CONFIG` `config_reference.value` is the file category (`RUNTIME` / `TEST` / `BUILD`).

**Status:** Proposed by Member 5 (Data/Evolution) — please review and reply with objections by end of Day 2. After that, changes go through a PR that updates this file and the schemas together.

Every module (frontend, backend, analysis, ML, evidence) exchanges data in these shapes. If your module produces or consumes one of these objects, it must follow this document.

| Where | What |
|---|---|
| `contracts/schemas/*.schema.json` | Machine-readable JSON Schemas (generated — do not edit by hand) |
| `contracts/examples/*.json` | One valid example per contract (checked by automated tests) |
| `seir-evidence/app/schema/` | Source of truth (Pydantic models) that generates the schemas |

---

## 1. Naming rules

| Thing | Rule | Example |
|---|---|---|
| **Component** | One **top-level Java type** (class / interface / enum / record / annotation) | — |
| `component_id` | **Fully qualified name** (FQCN). Nested types use `$` but are *not* separate components in v1 — they roll up to their top-level type | `com.shop.payment.LegacyPaymentService` |
| `repo_id` | `owner/name` exactly as in the GitHub URL | `spring-projects/spring-petclinic` |
| `snapshot`, any commit SHA | **Full 40-char lowercase hex**. Never short SHAs | `3f2a9c1e…4a39` |
| `file_path` | **Repo-relative, forward slashes**, no leading `/` | `payment-service/src/main/java/com/shop/Pay.java` |
| `module` | Folder before `src/…` in multi-module builds, else `null` | `payment-service` |
| JSON field names | `snake_case` | `evidence_type` |
| Enum values | `UPPER_SNAKE` strings | `AVAILABLE`, `CONFIG_REF` |
| Timestamps | ISO-8601 **with timezone**, stored in UTC | `2026-09-01T00:00:00Z` |
| Versions of a tool/model | `name@semver` | `git_history@0.1.0`, `xgb-risk@0.1.0` |

**Java (Jackson) tip:** set `PropertyNamingStrategies.SNAKE_CASE` and `WRITE_DATES_AS_TIMESTAMPS=false`, and use `Instant`/`OffsetDateTime` — never `LocalDateTime`.

**Scope (v1):** test classes are included but flagged `is_test: true`. Methods are not components in v1.

---

## 2. Contracts at a glance

| Contract | Produced by | Consumed by | Purpose |
|---|---|---|---|
| `Component` | Member 4 | everyone | The list of pieces of code |
| `DependencyEdge` | Member 4 (+ Member 5 for `CONFIG_REF`, `RUNTIME_CALL`, `CO_CHANGE`) | Member 4 impact, Member 1 graph | "A depends on B" |
| `EvidenceItem` | Members 4 & 5 | Member 3, Member 5 explainer, Member 2, Member 1 | One clue about one component |
| `ChangeCase` | Member 5 | Member 3 | One labelled training/evaluation example |
| `RiskAssessment` | Member 3 | Member 5 explainer, Member 2, Member 1 | Risk class + scores + top features |
| `Explanation` | Member 5 | Member 2, Member 1 | Grounded plain-English explanation |

---

## 3. EvidenceItem — the core rules

```jsonc
{
  "evidence_id": "ev_…",                       // auto-generated, deterministic
  "repo_id": "acme/shop",
  "snapshot": "<40-char sha>",
  "component_id": "com.shop.payment.LegacyPaymentService",
  "source": "GIT",                             // STATIC | GIT | CONFIG | RUNTIME | EXTERNAL
  "evidence_type": "recent_commit_count",      // must be in the registry below
  "value": 2,
  "unit": "commits",
  "availability": "AVAILABLE",                 // AVAILABLE | UNAVAILABLE | UNKNOWN
  "as_of": "2026-09-01T00:00:00Z",             // only data strictly before this was used
  "window": {"start": "…", "end": "…"},        // for time-based values
  "provenance": {"commits": [], "files": [{"path": "…", "line": 42}], "trace_ids": [], "note": null},
  "extraction_method": "git_history@0.1.0"
}
```

Rules that JSON Schema cannot express (enforced in Python, **please enforce on your side too**):

1. **Unknown is not zero.** If `availability` is `UNAVAILABLE` or `UNKNOWN`, `value` **must be `null`**. If `AVAILABLE`, `value` must be present — and then `0` genuinely means zero.
2. **Every AVAILABLE item has proof:** non-empty `provenance` or a `window`.
3. **`evidence_type` must be registered** for its `source` (table below).
4. **`evidence_id` is deterministic**: `ev_` + first 16 hex chars of SHA-1 over `repo_id|snapshot|component_id|source|evidence_type|as_of|window.start|window.end` (timestamps as UTC ISO-8601). Same inputs → same ID, so re-running an analysis gives identical IDs and explanations can cite them. For **multi-valued** types (currently only `config_reference`) the provenance file locations are appended as `|path:line,path:line` (sorted), so several references of one component get distinct IDs.
5. **`as_of` is a hard cutoff** — nothing at or after it may influence the value. This is how we avoid data leakage.

### Evidence-type registry

| Source | Allowed `evidence_type` |
|---|---|
| STATIC | `dependency_count`, `dependent_count`, `transitive_dependent_count`, `graph_depth`, `loc`, `cyclomatic_complexity` |
| GIT | `recent_commit_count`, `historical_commit_count`, `days_since_last_change`, `unique_contributors`, `lines_added`, `lines_deleted`, `total_churn`, `churn_ratio`, `co_change_count` |
| CONFIG | `config_reference`, `config_reference_count` |
| RUNTIME | `observed_use`, `execution_count`, `days_since_last_observed`, `runtime_coverage` |
| EXTERNAL | `possible_external_reference`, `public_endpoint_count` |

Need a new type? Add it to `EVIDENCE_TYPES` in `seir-evidence/app/schema/evidence.py` and to this table in the same PR.

---

## 4. Other contract rules

- **DependencyEdge:** direction is *source depends on target* (`CheckoutController → LegacyPaymentService`). Impact of changing X = everything that can **reach** X.
- **ChangeCase:** fields above the "ground truth" line are pre-change; `impacted_component_ids`, `fix_commit_shas` and `label` are post-change and **must never be used as model features**. A labelled case must record `label_rule_version`.
- **RiskAssessment:** `class_scores` sum to 1. Set `is_calibrated: true` **only** if the scores were calibrated; the UI must then say "probability", otherwise "model score".
- **Reasons (`top_features`) — "predicted class" reading (agreed 2026-09-30):** `contribution` is the attribution (e.g. SHAP value) **for the predicted class `risk_class`**. Positive = pushes the prediction *towards* `risk_class`; negative = pushes *away* from it. `feature` is an exact column name from `seir_features.FEATURE_COLUMNS`. The explainer words it per class:

  | `risk_class` | positive contribution | negative contribution |
  |---|---|---|
  | HIGH | "raises the risk" | "lowers the risk" |
  | MEDIUM | "supports a medium rating" | "argues against a medium rating" |
  | LOW | "keeps the risk low" | "points to higher risk" |
- **Model inputs:** always built with `seir_features.evidence_to_features(evidence, action)` (in `seir-evidence/seir_features/`) — the same function the dataset builder uses. Never re-implement it.
- **Explanation:** every claim and uncertainty cites ≥ 1 `evidence_id`. `validated: true` only after the evidence checker has passed.

---

## 5. Changing a contract

1. Edit the Pydantic model in `seir-evidence/app/schema/`.
2. Update the example in `contracts/examples/` and this file.
3. Run `python -m scripts.export_schemas` and `pytest` from `seir-evidence/`.
4. Bump `SCHEMA_VERSION` (minor for additive changes, major for breaking ones) and tell the team.
