# Three new models on the two-tier comparison — minimal update

Scores three already-generated model corpora (`qwen25_7b`, `llama31_8b`, `qwen25_14b`) on the
paper's 5 patterns, using the paper's existing formulas and the committed entropy weights. No new
generation, no re-derived weights, no change to the instrument.

The fourth model (`qwen3-coder-30b-a3b-instruct`) needed no work: its rows are already scored in
`data/outputs/generated_evaluation_scores.json`.

## Ground rules followed in this document

- **Predictions were written before the corresponding run and are never edited afterwards.** Where a
  prediction was wrong it stays wrong here, with the outcome recorded beneath it.
- Every number in an "Outcome" section came from running code. None was copied from a brief.
- Where a document and the code disagreed, the code won and the disagreement is recorded in
  "Corrections" at the end.

---

## Checkpoint 0 — CK tool availability

`analyze_project` catches `FileNotFoundError` / `RuntimeError` / `TimeoutError` from `run_ck` and
returns MI-only results **with no error** (`app/services/analysis_pipeline.py:73-76`). Had Java or
the CK JAR been missing, every CK column below would be empty and the run would still have looked
successful. So this was checked first.

**Outcome: PASS.**

Unit: `qwen25_7b/seed_40/Singleton/banking-account-management/rep0` (4 `.java` files —
`Account.java`, `AuditHistory.java`, `Main.java`, `StatementGenerator.java`).

`analyze_project(unit_dir, pattern_name="Singleton")` returned:

```json
{
  "total_classes": 5, "total_methods": 11, "total_files": 4,
  "pattern_name": "Singleton",
  "avg_mi_score": 62.88, "min_mi_score": 48.25, "max_mi_score": 72.01,
  "mi_distribution": {"green": 2, "yellow": 2, "red": 0},
  "avg_wmc": 2.8,
  "avg_cbo": 1.4,
  "avg_lcom_star": 0.16666666800000002,
  "avg_tcc": 0.0,
  "avg_rfc": 2.2,
  "avg_dit": 1.0,
  "ck_overall_score": 84.8,
  "ck_q_score": 84.8,
  "cqs_score": 73.02,
  "avg_halstead_volume": 235.79, "avg_halstead_difficulty": 5.63,
  "total_estimated_bugs": 0.3144, "avg_sloc": 12.0
}
```

`avg_cbo`, `avg_lcom_star`, `avg_rfc`, `avg_dit` are all present, non-`None`, and not all zero.

Two assertions were added beyond the four requested, because those four are weaker evidence than
they appear — MI and `mi_distribution` are populated even on the fallback path. Per-class `ck`
sub-dicts (`analysis_pipeline.py:97-141`) and the `methods[]` list (`:164-178`) are built **only**
when `run_ck` succeeds. Both were non-empty: 5 classes, 11 methods.

Environment on which this holds:

- Java: OpenJDK 21.0.9 (Homebrew).
- CK JAR: `/Users/hieunguyen/Documents/Coding Projects/ck/target/ck-0.7.1-SNAPSHOT-jar-with-dependencies.jar`
  (19.7 MB), the hardcoded default at `app/services/ck_metrics.py:25`.

**Reproducibility note.** That JAR path is hardcoded and lives *outside* the repository, overridable
only through the `CK_JAR_PATH` environment variable. On any other machine this study degrades to
MI-only without raising. Worth a line in the artifact section.

---

## Task 1 — The 180-row work list

Script: `scripts/three_models_minimal.py` (stage `inventory`).

### Prediction (written 2026-08-22, before running)

3 models x 5 patterns x 12 contexts = 60 units each, 180 total, every one with Java files.

### Outcome — the prediction held exactly

| model | patterns | contexts | units | units with >=1 .java file |
|---|---|---|---|---|
| qwen25_7b | 5 | 12 | 60 | 60 |
| llama31_8b | 5 | 12 | 60 | 60 |
| qwen25_14b | 5 | 12 | 60 | 60 |

TOTAL units: 180, all 180 with at least one `.java` file, 1030 `.java` files in total.

The pattern set and the context set are identical across all three models — not merely the same
size — so the grid is balanced and the cross-model comparison is like-for-like. Every unit is
`rep0` only, consistent with k=1.

Two join checks were run before the table, because they are the two ways this task silently
produces wrong numbers:

- **Context bridge.** All 12 context slugs found in the tree map to a `project_context` through
  `data/input/common_java_projects.json` (12 entries available, 12 used, no leftovers). The zip's
  slug is `slugify(project_title)`; `slugify` was reimplemented byte-for-byte from
  `generation/run_generation.py:99` rather than imported, because that module does not import on
  `main`.
- **`unit_id` exactness.** All 60 generated `unit_id`s per model are present verbatim in the
  matching `data/outputs/piqs_<model>.csv` (96 rows each; the 5-pattern subset selects 60). The
  join in Task 4 is therefore exact, not approximate.

The corpora also contain Builder, Decorator and Template Method. Those are excluded here because
they are not in the paper: 96 units per model minus 36 = 60.

---

## Task 2 — MI + CK on the 180 units

Script: `scripts/three_models_minimal.py` (stage `score`).
Output: `data/outputs/three_models_minimal_metrics.csv`.

### Prediction (written 2026-08-22, before running)

All 180 rows get real CK values, because all 96 units per model have `gen_status = ok`.

### Outcome — the prediction held

180 rows written in 99 s. 60 rows per model. **`ck_status` counts: `ok` = 180, and nothing else.**
No unit failed, no unit was dropped, and no metric cell is blank in any of the 180 rows. Every
(model, pattern) cell holds exactly 12 rows, and all 12 contexts are present with a non-empty
`project_context`.

`ck_status` distinguishes three failure modes that would otherwise be invisible: `no_java_files`,
`ck_unavailable: <columns>` (MI ran, CK silently did not — the fallback path at
`analysis_pipeline.py:73-76`), and `error: <type>: <msg>`. None of them occurred.

Per-model min / mean / max:

**qwen25_7b (n=60)**

| metric | min | mean | max |
|---|---|---|---|
| n_files | 2.000 | 5.817 | 10.000 |
| avg_mi_score | 54.740 | 63.813 | 76.860 |
| avg_cbo | 0.625 | 1.502 | 2.400 |
| avg_lcom_star | 0.000 | 0.169 | 0.542 |
| avg_rfc | 0.000 | 1.617 | 4.500 |
| avg_dit | 1.000 | 1.074 | 1.500 |
| ck_overall_score | 74.000 | 84.894 | 88.000 |

**llama31_8b (n=60)**

| metric | min | mean | max |
|---|---|---|---|
| n_files | 2.000 | 5.950 | 10.000 |
| avg_mi_score | 51.860 | 63.472 | 73.850 |
| avg_cbo | 0.750 | 1.577 | 2.857 |
| avg_lcom_star | 0.000 | 0.153 | 0.485 |
| avg_rfc | 0.500 | 1.766 | 4.000 |
| avg_dit | 1.000 | 1.109 | 1.600 |
| ck_overall_score | 77.500 | 85.314 | 88.000 |

**qwen25_14b (n=60)**

| metric | min | mean | max |
|---|---|---|---|
| n_files | 2.000 | 5.400 | 10.000 |
| avg_mi_score | 52.030 | 65.402 | 81.360 |
| avg_cbo | 1.000 | 1.566 | 2.400 |
| avg_lcom_star | 0.000 | 0.146 | 0.500 |
| avg_rfc | 0.000 | 1.587 | 4.250 |
| avg_dit | 1.000 | 1.119 | 1.625 |
| ck_overall_score | 80.000 | 85.388 | 88.000 |

**Observation, not yet a claim.** The three models are already nearly indistinguishable on every CK
input. Mean `ck_overall_score` spans 84.89 -> 85.39, a range of 0.49 points, and all three share the
same maximum of 88.0. Mean MI spans 63.47 -> 65.40. Whether that flatness survives into CQS, and
how it compares to the PIQS spread, is Task 4's question.

**Note on the `pattern` column.** It holds the Pattern Name form (`Factory Method`), matching both
the zip directories and the `pattern` column of the PIQS CSVs. The paper's rows use the
lower-case hyphenated form (`factory-method`); the mapping between them is `PAPER_PATTERNS` in the
script and is applied at join time in Task 4.

---

## Task 3 — Reconstruction check against the paper's 60 rows

### Outcome

_(filled in after the run)_

---

## Task 4 — The new table

### Prediction

_(to be written before that run)_

### Outcome

_(filled in after the run)_

---

## Corrections — where a number in the task brief disagreed with the code

_(filled in as they are found)_
