# Vertex (Gemini 2.5) arm of the logprob pilot — how-to

The `vertex` provider is an **additive** backend on `run_generation_logprobs.py`. It
generates the same 8 PIQS patterns × 12 contexts grid via **Google Gemini 2.5 on
Vertex AI** and captures per-token chosen logprobs, producing `unit.json` /
`token_logprobs.json` in the **identical join-ready shape** as the HuggingFace path —
so `score_piqs_logprobs.py` and `analyze_logprob_separation.py` work on Gemini output
**with no changes**.

- **Gemini 2.5 ONLY** (`gemini-2.5-flash`, `gemini-2.5-pro`). `response_logprobs` is
  broken on Gemini 3.x on Vertex ("Logprobs is not supported"); the script rejects
  any `gemini-3*` id at config time.
- **No GPU, no weights, no torch/transformers.** Runs on a laptop; the SDK is imported
  lazily only when you actually use `--provider vertex`.
- **Auth = Application Default Credentials via gcloud.** No key or JSON is ever read or
  embedded in code. Project/location come from env vars.
- **API-billed** (your Google credits). Each call logs its token count; cumulative
  input/output/thoughts totals print at the end of the run.

## 0. One-time setup (env vars + ADC)

```bash
# Authenticate once — the SDK finds ~/.config/gcloud/application_default_credentials.json
gcloud auth application-default login

# Required: your GCP project id. Location defaults to us-central1 if unset.
export GOOGLE_CLOUD_PROJECT=your-gcp-project-id
export GOOGLE_CLOUD_LOCATION=us-central1

# SDK (already in this repo's .venv; only needed on the vertex path):
pip install google-genai
```

## 1. Verify without spending (dry-run — lists units, calls NO API)

```bash
python generation/run_generation_logprobs.py \
  --provider vertex --model-id gemini-2.5-flash \
  --k 1 --temperature 0.7 \
  --contexts-file data/input/common_java_projects.json \
  --output-dir generated_logprobs_vertex_flash \
  --dry-run
```

Expect: `Grid: 8 patterns x 12 contexts x k=1 = 96 units` and a list of "WOULD
GENERATE" lines. No credentials required for `--dry-run`.

## 2. Generate — two runs, two output dirs (worse-vs-better)

Run **one model per invocation** with its own `--output-dir`, so the two models stay
cleanly separated and each is independently resumable (a killed run resumes and does
only the missing units). Logprob scales are not comparable across tokenizers, so keep
each model's analysis within its own tree.

**Model 1 (worse baseline): `gemini-2.5-flash`**

```bash
python generation/run_generation_logprobs.py \
  --provider vertex --model-id gemini-2.5-flash \
  --k 1 --temperature 0.7 \
  --contexts-file data/input/common_java_projects.json \
  --rate-limit-per-min 60 \
  --output-dir generated_logprobs_vertex_flash
# -> tree: generated_logprobs_vertex_flash/gemini-2-5-flash/seed_40/...
```

**Model 2 (better): `gemini-2.5-pro`**

```bash
python generation/run_generation_logprobs.py \
  --provider vertex --model-id gemini-2.5-pro \
  --k 1 --temperature 0.7 \
  --contexts-file data/input/common_java_projects.json \
  --rate-limit-per-min 60 \
  --output-dir generated_logprobs_vertex_pro
# -> tree: generated_logprobs_vertex_pro/gemini-2-5-pro/seed_40/...
```

Notes:
- `--rate-limit-per-min 60` throttles to 60 requests/min (Vertex has per-model quotas);
  tune to your quota, or drop it (`0` = no throttle). It reuses the existing per-process
  limiter.
- Transient errors (429 / 500 / 503 / timeouts) retry with the existing capped backoff
  (`--retry-max-attempts`, `--retry-backoff`); an exhausted or safety-blocked unit is
  recorded `failed`/`parse_failed` (with the reason saved to `raw_response.txt`) and the
  run **moves on** — one bad unit never crashes the whole run.
- At the end each run prints `Vertex token totals (API-billed): calls=… prompt(in)=…
  candidates(out)=… thoughts=… total=…` for a spend eyeball.

## 3. Score with the existing PIQS scorer (unchanged) — one CSV per model

```bash
python generation/score_piqs_logprobs.py \
  --output-dir generated_logprobs_vertex_flash \
  --out piqs_gemini_flash.csv

python generation/score_piqs_logprobs.py \
  --output-dir generated_logprobs_vertex_pro \
  --out piqs_gemini_pro.csv
```

PIQS is emitted as a raw percent (0–100); pick the pass rule at analyze time.

## 4. Run the separation report (unchanged) — one per model

```bash
python generation/analyze_logprob_separation.py \
  --output-dir generated_logprobs_vertex_flash \
  --piqs-results piqs_gemini_flash.csv \
  --threshold 70

python generation/analyze_logprob_separation.py \
  --output-dir generated_logprobs_vertex_pro \
  --piqs-results piqs_gemini_pro.csv \
  --threshold 70
```

`--threshold 70`: pass := PIQS ≥ 70. Sweep the threshold freely without re-scoring.

## Where the three numbers come from (identical to the HF path)

`mean_logprob`, `min_logprob`, `min_logprob_critical` are computed by the **same**
`compute_logprob_summary` function the HuggingFace backend uses — not a reimplementation.
For Gemini we parse `resp.candidates[0].logprobs_result.chosen_candidates` (each item has
`.token` and `.log_probability`), in generation order, and feed those into it.

- `mean_logprob` / `min_logprob` are exact (they use only the float logprobs).
- `min_logprob_critical` uses the identical keyword/critical-line proxy, fed Gemini's
  `.token` strings as the decoded pieces. This is the same documented approximation as on
  HF; `critical_fallback` is set when a generation has no critical line (then it equals
  the global min), exactly as before.

## Offline tests (no credits, no network)

```bash
python -m pytest tests/test_vertex_logprobs.py -q
```

Covers the chosen-token parsing (incl. empty and no-critical-line cases), the
three-number computation via the shared function, `vertex_generate` end-to-end with a
**stub client** (asserting `response_logprobs`/`logprobs` are set), the transient-vs-
permanent retry mapping, the save path (`generate_unit` → `unit.json` +
`token_logprobs.json` with the identical schema), safety-block → `parse_failed`, and the
gemini-3.x config guard.
