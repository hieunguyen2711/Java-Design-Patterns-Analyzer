# Code appendix: a two-tier evaluation of LLM-generated Java design patterns

Anonymous supplementary material for a double-blind submission. This repository
contains the evaluation instrument described in the paper, the artifacts it
produced, and the scripts that reproduce every number in the paper's tables.

The paper asks what a composite code-quality score actually measures. It builds
two scores over the same generated Java programs:

| Tier | Score | What it uses | Coverage |
|---|---|---|---|
| 1 | **CQS**, Code Quality Score | Maintainability Index + entropy-weighted CK metrics | any Java project |
| 2 | **CompQS**, Comprehensive Quality Score | CQS inputs **+ PIQS**, a predicate-logic check of whether the requested design pattern is structurally present | patterns with PIQS rules |

The claim the code supports is that these two numbers order the same programs
differently, and that the disagreement is exactly the part that says whether the
requested architecture exists.

---

## 1. What you can reproduce, and how

Every script below runs with no arguments. Paths are relative to the repository
root.

| Paper artifact | Command | Reads | Writes |
|---|---|---|---|
| Entropy weights for the CK sub-score | `python shannon_entropy.py` | `data/outputs/generated_common_projects_pipeline_results.json` | `data/config/entropy_weights.json` |
| Spearman correlation between tiers | `python spearman.py` | `data/outputs/generated_evaluation_scores.json` | stdout |
| Spearman check | `python validate_spearman.py` | same | stdout |
| Mann–Whitney separation analysis | `python scripts/validate_mann_whitney_evaluation.py` | `data/outputs/generated_evaluation_scores.json` | stdout |
| Monte Carlo weight sensitivity | `python scripts/validate_sensitivity_evaluation.py` | same | stdout |
| MI + CK over a batch of generated projects | `python scripts/run_generated_batches_quality.py` | `generated_batches/` | `data/outputs/generated_batches_quality_results.json` |
| Identifier obfuscation (the renaming test) | `python scripts/obfuscate.py` | `datasets_zipped/` | `datasets_obfuscated/` |
| LLM-judge comparison | `python run_judge_evaluation.py` | judge pair files under `data/` | judge report under `data/reports/` |

Pre-computed outputs for all of these are committed under `data/outputs/`, so
you can inspect the results without re-running anything.

### Scoring a single project directly

```python
from app.services.analysis_pipeline import analyze_project

result = analyze_project("path/to/java/project", pattern_name="Singleton")
print(result["summary"])   # avg_mi_score, avg_cbo, avg_lcom_star, avg_rfc, avg_dit, ck_q_score, cqs_score
```

PIQS alone:

```python
from app.services.piqs_service import PIQSService

PIQSService().evaluate("Singleton", {"Config.java": source_text})
```

---

## 2. Setup

Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`requirements-generation.txt` and `requirements-hf.txt` are only needed if you
want to re-run generation on a GPU. Scoring and analysis do not need them.

### The CK tool is a required external dependency

CK metrics are produced by an external Java tool invoked through `subprocess`.
You need a JDK and the CK JAR, then point the code at it:

```bash
export CK_JAR_PATH=/absolute/path/to/ck-<version>-jar-with-dependencies.jar
```

**This step is not optional, and skipping it fails quietly.** If the JAR is
missing, `analyze_project` returns Maintainability Index results with all CK
fields empty and raises no error, and `compute_class_quality` silently falls
back to a different, non-entropy formula that includes WMC. Every CK and CQS
number would then be wrong while the run still looks successful.

Verify before you trust any output:

```python
from app.services.analysis_pipeline import analyze_project
s = analyze_project("<any java project dir>", "Singleton")["summary"]
assert s["avg_cbo"] is not None and s["avg_lcom_star"] is not None
```

---

## 3. Repository layout

```
app/services/      the instrument
  analysis_pipeline.py   orchestration; analyze_project() and _compute_cqs()
  ck_metrics.py          CK invocation, desirability functions, entropy weighting
  piqs_service.py        predicate-logic pattern rules (PIQS)
  file_service.py        Java file discovery and parsing
app/api/           FastAPI routers (a convenience wrapper; not needed to reproduce results)
app/core/          settings and environment configuration

scripts/           pipeline and analysis scripts (see the table above)
validation/        checker validation against the published ground truth
generation/        the code-generation runner (GPU; see limitations)
configs/           per-model generation configs
tests/             automated tests

data/config/       entropy_weights.json, the committed weight vector
data/input/        application-domain definitions and pattern lists
data/outputs/      all committed result artifacts
data/reports/      validation and judge reports
generated_batches/ generated Java projects and per-job artifacts
datasets_zipped/, datasets_obfuscated/   corpora before and after renaming
```

### Where each formula lives

| Formula | File and role |
|---|---|
| Desirability functions, with both clamps | `app/services/ck_metrics.py` |
| Entropy weighting of the four CK metrics | `app/services/ck_metrics.py`, weights loaded once at import from `data/config/entropy_weights.json` |
| `CQS = d_MI^0.5 · CK_q^0.5 · 100` | `app/services/analysis_pipeline.py` |
| `CompQS = d_PIQS^0.5 · d_MI^0.25 · CK_q^0.25 · 100` | recorded in `data/outputs/generated_evaluation_scores.json` under `formula_compqs` |
| PIQS property rules | `app/services/piqs_service.py` |

Note that the desirability functions are implemented twice: `ck_metrics.py` is
the version that runs during scoring, and `shannon_entropy.py` contains a
second copy used only to derive the weights. They differ in the upper clamp.
Only `ck_metrics.py` affects any score reported in the paper.

---

## 4. Limitations of this artifact

- **Generation needs a GPU.** `generation/run_generation.py` runs the
  open-weight models locally through Hugging Face. Reproducing the generated
  corpora from scratch requires GPU access; all generated outputs are committed
  so that scoring can be reproduced without one.
- **The judge comparison needs API keys.** `run_judge_evaluation.py` calls
  hosted models through a routing service. Its outputs are committed.
- **Result artifacts are pre-computed.** Re-running a scoring script overwrites
  the corresponding file under `data/outputs/`. Copy anything you want to keep
  before re-running.
- **Two corpora sit on different grids.** The 1162-project corpus spans 83
  patterns and 14 application domains at one generation per cell. The matched
  grid spans 5 patterns and 12 domains with three seeds. The paper says which
  table rests on which.

---

## 5. Anonymity

This is an anonymized mirror prepared for double-blind review. Identifying
strings have been replaced. If any remain, they are an oversight and not an
attempt to signal authorship.
