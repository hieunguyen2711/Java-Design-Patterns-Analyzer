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

The script that wrote `data/outputs/generated_evaluation_scores.json` is not in the repository, so
the formulas were reconstructed from the strings that file records:

```
formula_cqs    = "CQS = d_MI^0.5 * CK_q^0.5 * 100"
formula_compqs = "CompQS = d_PIQS^0.5 * d_MI^0.25 * CK_q^0.25 * 100"
```

CQS uses `_compute_cqs` (`app/services/analysis_pipeline.py:32`) unchanged. CompQS has no committed
implementation, so it was written to follow the same clamping convention.

The file holds 70 rows, all `model_used = qwen3-coder-30b-a3b-instruct`. Filtering to the 12 shared
contexts leaves **exactly 60 rows**, as expected. The two dropped contexts are
`'An e-commerce order management system in Java'` and `'a ticket booking system'` — confirmed as
out of scope for this comparison.

### Outcome — PASS, all 60 rows reproduce

| formula | exact to the stored 2dp | within the inputs' own rounding | real disagreement |
|---|---|---|---|
| CQS | 53 / 60 | 7 / 60 | **0** |
| CompQS | 53 / 60 | 7 / 60 | **0** |

**Why 7 rows are not bit-exact, and why that is not a failure.** The score file stores
`avg_mi_score`, `ck_q_score` and `piqs_score` rounded to 2 decimals, but computed `cqs_score` and
`compqs_score` from the *unrounded* values. Recomputing from the rounded columns therefore carries
an unavoidable error of up to one unit in the last place. Every one of the 7 differences is exactly
0.01.

This was verified rather than assumed. Both formulas are monotonically increasing in every input,
so for each row the interval reachable from inputs consistent with the stored 2dp values is just
`[f(inputs - 0.005), f(inputs + 0.005)]`. **The stored score falls inside that interval on all 60
rows, for both formulas.** Zero rows fall outside. In every one of the 7 cases the reachable
interval is a single 0.01-wide step containing both the stored and the recomputed value, e.g.
`stored=70.38 got=70.37 reachable=[70.37, 70.38]`.

Four alternative orderings of the CQS expression were also tried
(`d_mi**0.5 * d_ck**0.5`, `sqrt(d_mi*d_ck)`, `sqrt(mi*ck)`, `(mi**0.5)*(ck**0.5)`). All four give
the identical set of 7 non-exact rows, which rules out an operation-ordering or float-associativity
explanation and confirms the cause is the rounded inputs.

**Conclusion: the reconstruction is correct and the new models may be scored with it.**

An initial version of this check used a flat `abs(diff) > 0.01` tolerance. That was both arbitrary
and unreliable — float subtraction put some of the 0.01 differences fractionally above the
threshold and others fractionally below, reporting 3 mismatches on one comparison and 7 on an
exact-equality comparison of the same data. The committed check uses the interval test instead.

### Where the entropy weights enter — confirmed, not assumed

`ck_q_score` is not an independent quantity: `analysis_pipeline.py:250` assigns it
`ck_overall_score`, which comes from `compute_class_quality`, which prefers
`_entropy_ck_overall_score` whenever `data/config/entropy_weights.json` loads
(`app/services/ck_metrics.py:117-140`). The weights are read **once at module import** into the
module-level `_ENTROPY_WEIGHTS`. So the committed weights were used for the 180 new rows, exactly as
required, and no weight was recomputed from the new corpora.

That the reconstruction reproduces the Qwen3-Coder `cqs_score` from its stored `ck_q_score` is
independent evidence that the same weighted CK_q definition was in force when those rows were
produced.

---

## Task 4 — The new table

### Prediction (written 2026-08-22, before running)

Stated so it can be shown wrong:

1. **CQS is flat across all four models.** The spread of per-model mean CQS is under 2 points.
   Basis: Task 2 already showed the CK inputs nearly identical between the three new models (mean
   `ck_overall_score` 84.89 -> 85.39, a 0.49-point spread; mean MI 63.47 -> 65.40), and CQS is a
   geometric mean of exactly those two things. Qwen3-Coder could sit apart from the other three,
   since it is a much larger model scored in a separate run, so this is the part of the prediction
   most likely to fail.
2. **PIQS is not flat.** The spread of per-model mean PIQS across the four models is at least
   10 points, i.e. an order of magnitude wider than the CQS spread.
3. **Within each model, across the 5 patterns, the same asymmetry holds:** the CQS range is
   narrower than the PIQS range, for all four models.
4. **Singleton rises and Composite falls** in at least 3 of the 4 models. Singleton is the easiest
   of the five to implement correctly, so its PIQS should be high relative to its middling code
   metrics; Composite is the most structurally demanding, so it should score well on CK/MI while
   PIQS penalises incorrect structure.
5. **Zero rows are lost in the join.** Exactly 240.

Prediction 4 is the one I hold most loosely: rank movement depends on the whole ordering, and with
5 patterns a single tie or near-tie can move a rank without meaning anything.

### Outcome

The join produced **exactly 240 rows** — 4 models x 5 patterns x 12 contexts, 60 per model, no row
lost and none duplicated.

For the three new models, CQS and CompQS are computed from full-precision MI and CK_q. For
`qwen3-coder-30b-a3b-instruct` the **stored** `cqs_score` / `compqs_score` are used rather than
recomputed, because those were computed from unrounded inputs whereas the file's own `avg_mi_score`
/ `ck_q_score` columns are rounded to 2dp (Task 3). Using the stored values keeps the paper's
published numbers intact; Task 3 established the two agree to within that rounding.

`delta` = avg CompQS - avg CQS. Rank 1 = best.

#### qwen25_7b

| pattern | avg CQS | avg PIQS | avg CompQS | delta | CQS rank | CompQS rank |
|---|---|---|---|---|---|---|
| singleton | 71.66 | 100.00 | 84.63 | +12.97 | 4 | 1 |
| factory-method | 75.08 | 69.46 | 69.98 | -5.10 | 2 | 3 |
| strategy | 76.88 | 92.58 | 84.24 | +7.36 | 1 | 2 |
| observer | 72.67 | 65.72 | 67.67 | -4.99 | 3 | 4 |
| composite | 71.59 | 63.95 | 63.66 | -7.93 | 5 | 5 |

CQS 71.59-76.88 (range 5.29) · PIQS 63.95-100.00 (range 36.05) · mean CQS 73.57, mean PIQS 78.34,
mean CompQS 74.03

#### llama31_8b

| pattern | avg CQS | avg PIQS | avg CompQS | delta | CQS rank | CompQS rank |
|---|---|---|---|---|---|---|
| singleton | 70.49 | 100.00 | 83.94 | +13.45 | 5 | 1 |
| factory-method | 74.53 | 67.95 | 69.70 | -4.82 | 2 | 4 |
| strategy | 76.14 | 87.95 | 78.34 | +2.20 | 1 | 2 |
| observer | 74.08 | 71.89 | 71.44 | -2.64 | 3 | 3 |
| composite | 72.55 | 69.86 | 69.22 | -3.33 | 4 | 5 |

CQS 70.49-76.14 (range 5.65) · PIQS 67.95-100.00 (range 32.05) · mean CQS 73.56, mean PIQS 79.53,
mean CompQS 74.53

#### qwen25_14b

| pattern | avg CQS | avg PIQS | avg CompQS | delta | CQS rank | CompQS rank |
|---|---|---|---|---|---|---|
| singleton | 72.95 | 100.00 | 85.35 | +12.41 | 4 | 2 |
| factory-method | 77.86 | 98.49 | 87.54 | +9.68 | 1 | 1 |
| strategy | 76.07 | 91.67 | 80.16 | +4.09 | 2 | 3 |
| observer | 74.80 | 85.80 | 79.53 | +4.74 | 3 | 4 |
| composite | 71.75 | 82.81 | 76.93 | +5.18 | 5 | 5 |

CQS 71.75-77.86 (range 6.11) · PIQS 82.81-100.00 (range 17.19) · mean CQS 74.68, mean PIQS 91.75,
mean CompQS 81.90

#### qwen3-coder-30b-a3b-instruct (the paper's existing model, unchanged)

| pattern | avg CQS | avg PIQS | avg CompQS | delta | CQS rank | CompQS rank |
|---|---|---|---|---|---|---|
| singleton | 61.56 | 100.00 | 78.35 | +16.78 | 4 | 2 |
| factory-method | 72.88 | 78.31 | 75.45 | +2.57 | 2 | 3 |
| strategy | 75.62 | 90.72 | 82.65 | +7.03 | 1 | 1 |
| observer | 71.00 | 71.25 | 70.90 | -0.10 | 3 | 4 |
| composite | 60.34 | 60.29 | 59.39 | -0.95 | 5 | 5 |

CQS 60.34-75.62 (range 15.27) · PIQS 60.29-100.00 (range 39.71) · mean CQS 68.28, mean PIQS 80.11,
mean CompQS 73.35

#### Summary table for the paper

| model | CQS range across 5 patterns | PIQS range across 5 patterns | Singleton rises? | Composite falls? |
|---|---|---|---|---|
| qwen25_7b | 71.59-76.88 (5.29) | 63.95-100.00 (36.05) | yes, 4 -> 1 | no, already last (5 -> 5) |
| llama31_8b | 70.49-76.14 (5.65) | 67.95-100.00 (32.05) | yes, 5 -> 1 | yes, 4 -> 5 |
| qwen25_14b | 71.75-77.86 (6.11) | 82.81-100.00 (17.19) | yes, 4 -> 2 | no, already last (5 -> 5) |
| qwen3-coder-30b-a3b-instruct | 60.34-75.62 (15.27) | 60.29-100.00 (39.71) | yes, 4 -> 2 | no, already last (5 -> 5) |

Across the four models: mean CQS spans 68.28-74.68 (spread **6.40**); mean PIQS spans 78.34-91.75
(spread **13.41**).

### Did the prediction hold?

| # | Prediction | Verdict |
|---|---|---|
| 1 | Per-model mean CQS spread under 2 points | **FAILED** — 6.40 |
| 2 | Per-model mean PIQS spread at least 10 points | held — 13.41 |
| 3 | Within every model, CQS range < PIQS range | held — 4 of 4 |
| 4 | Singleton rises and Composite falls in >=3 of 4 models | **half failed** — Singleton 4/4, Composite 1/4 |
| 5 | Exactly 240 rows, none lost | held |

**Prediction 1 failed, and it failed for the reason flagged when it was written.** The three new
models are indeed flat — mean CQS 73.57 / 73.56 / 74.68, a spread of 1.12 points, comfortably inside
the 2-point claim. Qwen3-Coder sits apart at 68.28, and it alone widens the spread to 6.40. The
prediction was stated over all four models, so it fails as written.

That gap is worth a sentence in the paper rather than being smoothed over: the largest model has the
*lowest* mean CQS of the four, driven by singleton (61.56) and composite (60.34), where the three
small models sit near 71-73. Its per-pattern CQS range, 15.27, is also 2.5x wider than any of the
three new models. Qwen3-Coder was scored in a separate April run over a different context set, so
run-to-run differences cannot be excluded as a contributing cause.

**Prediction 4 was half wrong, and the failure is a floor effect rather than a counter-result.**
Composite is *already* ranked 5th of 5 on CQS in three of the four models, so it has nowhere to
fall; in the fourth (llama31_8b) it does fall, 4 -> 5. Composite ends bottom-ranked on both metrics
in all four models. The right statement for the paper is "Composite ranks last on both CQS and
CompQS in all four models", not "Composite falls". Singleton rises in 4 of 4.

### What the table actually shows

Prediction 3 is the load-bearing result and it held without exception. In every model the code
quality score spans a far narrower band across the five patterns than PIQS does:

| model | CQS range | PIQS range | ratio |
|---|---|---|---|
| qwen25_7b | 5.29 | 36.05 | 6.8x |
| llama31_8b | 5.65 | 32.05 | 5.7x |
| qwen25_14b | 6.11 | 17.19 | 2.8x |
| qwen3-coder-30b-a3b-instruct | 15.27 | 39.71 | 2.6x |

Singleton is the sharpest single case. It scores **PIQS 100.00 in all four models** while ranking
4th or 5th of 5 on CQS in all four. A perfectly-implemented pattern is being ranked near-last by the
code-quality score. CompQS, which mixes PIQS back in, lifts it to rank 1 or 2 in all four models —
delta between +12.41 and +16.78.

The same holds between models rather than within them. Mean PIQS rises 78.34 -> 79.53 -> 91.75 from
qwen25_7b to llama31_8b to qwen25_14b, a 13.4-point climb in architectural correctness. Mean CQS
over the same three models moves 73.57 -> 73.56 -> 74.68: **1.12 points, and not even monotonic.**
The code-quality score is close to blind to a 13-point difference in pattern correctness.

### A ceiling effect in PIQS that the paper should disclose

Not something this task asked for, but it turned up in the data and it bears on how the table reads.

**Every one of the 48 Singleton units — all 12 contexts, all 4 models — scores PIQS exactly 100.0.**
The distinct set of PIQS values for singleton across all 240 rows is `[100.0]`. Singleton therefore
contributes zero discriminating information to PIQS; it is a constant, not a measurement, and its
+12 to +17 CompQS delta is guaranteed by construction rather than observed.

The saturation is broader than singleton. Units scoring exactly 100.0, out of 12 per cell:

| model | singleton | factory-method | strategy | observer | composite |
|---|---|---|---|---|---|
| qwen25_7b | 12 | 3 | 8 | 3 | 2 |
| llama31_8b | 12 | 1 | 9 | 3 | 3 |
| qwen25_14b | 12 | 11 | 11 | 7 | 3 |
| qwen3-coder-30b-a3b-instruct | 12 | 0 | 7 | 0 | 2 |

For qwen25_14b that is 44 of 60 units pinned at the maximum. Much of its high mean PIQS is a ceiling
rather than a spread, which weakens any claim that PIQS cleanly separates the stronger model. The
honest framing is that PIQS discriminates well at the low end and saturates at the high end.

### Pattern ordering under CQS is stable across models

Best to worst by mean CQS:

- qwen25_7b: strategy > factory-method > observer > singleton > composite
- llama31_8b: strategy > factory-method > observer > composite > singleton
- qwen25_14b: factory-method > strategy > observer > singleton > composite
- qwen3-coder: strategy > factory-method > observer > singleton > composite

Observer is 3rd in all four. Strategy and factory-method take the top two places in all four.
Composite is last in three of four. This stability across two model families and a 4x parameter
range suggests CQS is largely measuring properties of the *pattern*, not of the model — consistent
with the paper's argument.

---

## Corrections — where a number in the task brief disagreed with the code

Everything checkable in the brief held up, with these exceptions and additions.

| # | Brief says | Code says |
|---|---|---|
| 1 | `analyze_project` returns `CBO`, `LCOM*`, `RFC`, `DIT` | The summary keys are `avg_cbo`, `avg_lcom_star`, `avg_rfc`, `avg_dit`, `avg_wmc` (`analysis_pipeline.py:243-248`). |
| 2 | Paper §3.3 floor is `max(0, ...)`, code uses `max(0.001, ...)` plus `min(1.0, ...)` on DIT | Correct but understated. `ck_metrics.py:136-140` applies **both** clamps to **all four** metrics, not just the floor and not just DIT. |
| 3 | The paper's `project_context` is "the full sentence" | True for 12 of the 14. The other two are `'An e-commerce order management system in Java'` and `'a ticket booking system'` — confirmed as out of scope. They are exactly the two that the 12-context filter drops. |
| 4 | `data/config/entropy_weights.json` says `n_evaluations = 996`, paper says 1162 | Confirmed: the file says 996. Not acted on. |
| 5 | `generation/run_generation.py` broken at lines 55 and 905 | Confirmed verbatim, both single-underscore. Not fixed — out of scope. Consequence: `slugify` had to be reimplemented in `scripts/three_models_minimal.py` rather than imported. |
| 6 | — | **Not in the brief:** there are two separate implementations of the desirability functions. `shannon_entropy.py` omits `min(1.0, ...)` on CBO/LCOM/RFC; `ck_metrics.py` includes it. Only `ck_metrics.py` runs in this study. Fix the paper against `ck_metrics.py`. |
| 7 | — | **Not in the brief:** `summary["ck_q_score"]` is simply assigned `ck_overall_score` (`analysis_pipeline.py:250`). CK_q is not an independent quantity. |
| 8 | — | **Not in the brief:** `configs/` contains only `llama31_8b.yaml` and `qwen25_7b.yaml`. There is **no `qwen25_14b.yaml`**, so the 14b grid is evidenced by its directory tree and PIQS CSV, not by a committed config. |
| 9 | — | **Not in the brief:** the CK JAR path is hardcoded to a location outside the repo (`ck_metrics.py:25`). Elsewhere this study silently degrades to MI-only. |

### Confirmed exactly as stated

- Three model runs, 96 units each, 8 patterns x 12 contexts x k=1, seed 40.
- 1528 `.java` files in the zip.
- All 96 units per model have `gen_status = ok`, all three models. **Zero parse failures** — worth
  the sentence the brief suggests: these small models did not fail to produce parseable Java.
- The 12 contexts are an exact subset of the paper's 14.
- The paper's 70 rows carry `project_context`, 5 rows per context, and filter to exactly 60.
- `generated_evaluation_scores.json` records both formula strings, and both reconstruct.
