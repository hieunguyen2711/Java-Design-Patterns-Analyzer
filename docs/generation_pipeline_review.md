# Generation Pipeline Review (Part 1 — Map, read-only)

> **Note (superseded in part):** §7 below proposed an OpenRouter + budget design.
> The shipped implementation evolved per later decisions: it now runs **two
> Hugging Face models in-process on GPU** (Llama 3.1 8B, Qwen 2.5 7B), **no API
> key and no cost/budget tracking**. For how to actually run it, see
> **[how_to_run_on_slurm.md](how_to_run_on_slurm.md)**. §§1–6 (the codebase map)
> remain accurate.

**Date:** 2026-07-28
**Scope:** Review-and-harden the **code-generation** side of the DP Recognition Backend so it can
run unattended on a Slurm cluster for a ~10-model study, within a hard ~$50 API budget.
**This document changes no code.** It reports what is actually in the repo, traces the generation
path end to end, audits config/secrets/deps, and inventories the robustness that already exists so
we don't rebuild it. It ends with a proposed Part 2 design and the decisions I need confirmed
before writing any code.

> **Headline finding.** There is **no batch/CLI generation runner** today. Generation is a
> **FastAPI web service** (`BatchGenerationService`, reached over HTTP) that sweeps the **83
> "pass" patterns** with **one shared project context and one model per job**. It has **no
> domains, no k-repetitions, no multi-model grid, no cost tracking, no budget cap, and no
> cross-run resume** (each run mints a new `job_id` and re-pays from scratch). The study grid
> (models × patterns × domains × k) cannot be expressed with it as-is. The good news: the
> **scoring side already contains every robustness primitive we need** — in
> `run_judge_evaluation.py` — so Part 2 is mostly *assembling proven patterns into one standalone
> script*, not inventing them.

---

## 1. Repository tour

Top-level (trimmed to what matters):

```
app/                     ← the live application package (FastAPI)
  api/        analyze.py, metrics.py, models.py        HTTP routers (incl. generation endpoints)
  core/       config.py                                 all settings (pydantic-settings, reads .env)
  llm/        client.py, chunker.py                     OpenAI-compatible HTTP client (OpenRouter + local)
  schemas/    request_models.py, response_models.py     Pydantic request/response models
  services/   batch_generation_service.py  ← GENERATION orchestrator
              prompt_service.py            ← prompt build + parse-into-Java-files
              file_service.py              ← save/extract/walk java files, zip packaging
              piqs_service.py              ← SCORING (validated; DO NOT TOUCH)
              analysis_pipeline.py, analysis_service.py, ck_metrics.py,
              halstead.py, mi_calculator.py, batch_metrics_service.py   ← SCORING/metrics
  utils/      validators.py
main.py                  ← FastAPI entrypoint (uvicorn main:app)
run_judge_evaluation.py  ← SCORING (LLM-as-judge). **Robustness gold-reference** (see §5)
scripts/                 ← data/pipeline drivers (all SCORING/recognition; none generate code — see below)
validation/              ← SCORING oracle: mutation batteries, Kim comparison, reports (DO NOT TOUCH)
data/  input|config|outputs|reports/                    ← JSON inputs, outputs, checkpoints (§ table below)
generated_batches/       ← 14 completed generation jobs (hex job-id dirs); OUTPUT workspace
generated_batches_piqs/  ← 2 curated projects (PIQS-supported patterns, unpacked)
requirements.txt         ← INCOMPLETE vs. what actually runs (see §4)
.env                     ← secrets (gitignored); OPEN_ROUTER_API_KEY lives here
llm/ models/ routes/ services/ utils/   ← STALE leftovers of an older flat layout: __pycache__ only, no .py
```

### 1a. Which files are generation vs scoring

**Generation (produces Java code) — in scope for Part 2 (reuse where sensible, never regress):**

| File | Role |
|---|---|
| `app/services/batch_generation_service.py` | The only batch generation orchestrator (async, over pass patterns) |
| `app/services/prompt_service.py` | `build_generate_prompt` / `build_batch_generate_prompt`, and `parse_generated_files` (local parse recovery) |
| `app/llm/client.py` (`OllamaClient`) | OpenAI-compatible `/v1/chat/completions` client — used for **both** OpenRouter and local LM Studio/Ollama (name is misleading) |
| `app/api/analyze.py` | HTTP endpoints: `POST /generate`, `POST /api/v1/generate-pass-projects` (+ status/download) |
| `app/core/config.py` | model, temperature, `MAX_OUTPUT_TOKENS`, `BATCH_*` knobs, paths |
| `app/schemas/request_models.py` | `GenerateRequest`, `BatchGeneratePassProjectsRequest` |
| `app/services/file_service.py` | save/extract/walk java, zip packaging (shared with scoring) |
| `main.py` | FastAPI app wiring |

**Current generation entry points:** HTTP only.
- `POST /generate` — one pattern, returns parsed files inline.
- `POST /api/v1/generate-pass-projects` — async job over all 83 pass patterns, one shared
  `project_context`, one `model`; writes to `generated_batches/<job_id>/`.
- **There is no `python … generate` CLI.** The `scripts/run_*.py` files do **not** generate code —
  they POST existing zips to the `/analyze` (recognition) endpoint and score the answers. They are
  scoring/recognition drivers.

**Scoring / validation (DO NOT MODIFY):** `app/services/piqs_service.py`, `analysis_*`,
`ck_metrics.py`, `halstead.py`, `mi_calculator.py`, `batch_metrics_service.py`; all of
`validation/`; `run_judge_evaluation.py`; `scripts/generate_judge_pairs.py`,
`scripts/extract_judge_sources.py`, `scripts/run_generated_batches_quality.py`,
`scripts/run_generated_batches_recognition.py`, `scripts/run_test*.py`,
`scripts/validate_*_evaluation.py`.

### 1b. The referenced artifacts (inputs / outputs / checkpoints)

| File | Size | Kind | What it is |
|---|---|---|---|
| `data/input/pass.json` | 8.4 KB | **INPUT** | 83 objects `{pattern, llm_answer, Status:"Pass"}` — the pattern list the batch generator sweeps |
| `data/input/common_java_projects.json` | 2.3 KB | **INPUT** | 12 `{project_title, project_context}` seeds — the closest thing to "domains" today |
| `data/input/results.json` | 18 KB | **INPUT/ref** | 173 recognition rows `{pattern, llm_answer, Status}` |
| `generated_batches/<job>/manifest.json` | — | **CHECKPOINT (per-job only)** | Live job state: status, per-pattern results, model, context. Not used to resume across runs |
| `generated_batches/<job>/results.json` | — | **OUTPUT** | 83 rows `{pattern, status, files_count, duration_ms, output_zip_relative_path, error}` |
| `generated_batches/<job>/<pattern>/{prompt.txt, raw_response.txt, <pattern>.zip}` | — | **OUTPUT** | The raw prompt, raw model text, and the packaged Java project |
| `data/outputs/generated_batches_quality_results.json` | 1.43 MB | **OUTPUT (scoring)** | MI+CK+PIQS aggregated over the 14 jobs |
| `data/outputs/generated_evaluation_scores.json` | 42 KB | **OUTPUT (scoring)** | 70 rows of CQS/CompQS derived from the file above |
| `data/outputs/results_code_*.json` (deepseek, quwen, llama33 smoke) | — | **OUTPUT (recognition)** | Per-model recognition Pass/Not-Pass |
| `data/reports/judge_pairs.json` | 25 KB | **intermediate** | 25 A/B pairs (output of pair-gen, input to the judge) |
| `data/reports/judge_prompts.json` | 159 KB | **INPUT to judge** | Rendered judge prompts |
| `data/reports/judge_results_checkpoint.jsonl` | 72 KB | **CHECKPOINT** | Append-only JSONL, one line per `(pair_id, judge_model)` call, with tokens/cost/retries — the resume log for `run_judge_evaluation.py` |
| `data/reports/judge_validation_results.json` | 49 KB | **OUTPUT (scoring)** | Aggregated judge report |

`BATCH_RETRY_COUNT` (mentioned in prior work) is a **config knob** (`app/core/config.py`), consumed
by `BatchGenerationService._generate_pattern_with_retries`. `judge_results_checkpoint.jsonl` is the
**judge resume log**. Both are described precisely in §5.

---

## 2. The generation path, end to end

Tracing one generation as it happens today (batch path, the closest to the study):

```
HTTP POST /api/v1/generate-pass-projects   {project_context, model, concurrency, patterns_limit?}
        │   (app/api/analyze.py)
        ▼
BatchGenerationService.start_job()          app/services/batch_generation_service.py
        │  • load_pass_patterns()  ← reads data/input/pass.json, keeps Status=="pass"
        │      └─ HARD GUARD: raises unless exactly EXPECTED_PASS_PATTERN_COUNT (83) unless patterns_limit set
        │  • job_id = uuid4().hex ; mkdir generated_batches/<job_id>/
        │  • seed results[] = one "queued" row per pattern ; write manifest.json
        │  • asyncio.create_task(_run_job)   → returns 202 immediately
        ▼
_run_job()  (background asyncio task)
        │  • Semaphore(min(concurrency, BATCH_MAX_CONCURRENCY=2))
        │  • for each pattern:  asyncio.to_thread(_generate_pattern_with_retries)
        ▼
_generate_pattern_with_retries()            retry: BATCH_RETRY_COUNT+1 attempts, FIXED 1.0s delay
        ▼
_generate_single_pattern()
        │  • prompt = PromptService.build_batch_generate_prompt(pattern, project_context)
        │  • raw    = OllamaClient.generate(prompt, model)          ← the ONE model call
        │  • files  = PromptService.parse_generated_files(raw)      ← regex extract "### FILE:" blocks
        │  • write  prompt.txt, raw_response.txt
        │  • _package_project_zip(...)  → <pattern>.zip with src/main/java/*.java + pom.xml
        │  • return {pattern, status:"success", files_count, duration_ms, output_zip_relative_path}
        ▼
_record_pattern_result() → update manifest.json after each pattern (in-memory dict + rewrite file)
        ▼
_create_final_bundle() → generated_projects_bundle.zip   ;  _finalize_job() → status "completed"
```

**The single model call** (`app/llm/client.py:37`):

```
POST {base}/v1/chat/completions
  body: {model, messages:[{role:user, content:prompt}], stream:false,
         temperature: settings.LLM_TEMPERATURE, max_tokens: settings.MAX_OUTPUT_TOKENS}
  base = OPEN_ROUTER_BASE_URL if USE_OPEN_ROUTER else OLLAMA_BASE_URL
  headers (OpenRouter only): Authorization: Bearer <key>, HTTP-Referer, X-Title
  returns: data["choices"][0]["message"]["content"]   ← content string ONLY
```

**Parsing** (`prompt_service.parse_generated_files`): regex matches `### FILE: Name.java` blocks with
an optional ```` ```java ```` fence; on **zero matches** it falls back to dumping the whole response
into a single `GeneratedCode.java`. That fallback is the only parse-recovery today.

### Data-flow (text diagram)

```
 pass.json (83 patterns) ─┐
 project_context (1 str) ─┼─▶ prompt ─▶ [OpenRouter | local /v1/chat/completions] ─▶ raw text
                          │                                                             │
                          │                                        parse_generated_files│(regex + whole-file fallback)
                          │                                                             ▼
                          │                                              [{filename, content}, ...]
                          │                                                             │
                          ▼                                                             ▼
             generated_batches/<job_id>/<pattern>/{prompt.txt, raw_response.txt, <pattern>.zip}
                          │                                                             │
                          └───────────────▶ manifest.json / results.json ◀─────────────┘
```

**What is missing for the study:** the model is fixed per job; there is no domain axis (only a
single free-text `project_context`); no repetition index `k`; no token/cost capture (the client
discards the `usage` block the API returns); no record of the *returned* model-id; and re-running
produces a brand-new `job_id` rather than resuming.

---

## 3. Configuration & secrets audit

**Where knobs live today** (`app/core/config.py`, pydantic-settings, `env_file=".env"`):

| Setting | Default | Notes |
|---|---|---|
| `USE_OPEN_ROUTER` | `False` | routes client to OpenRouter vs local |
| `OPEN_ROUTER_BASE_URL` | `https://openrouter.ai/api` | |
| `OPEN_ROUTER_API_KEY` | `""` | **secret**, read from `.env` |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:1234` | actually LM Studio's port |
| `DEFAULT_MODEL` | `qwen3-coder-30b-a3b-instruct` | |
| `LLM_TEMPERATURE` | `0.1` | **single** temperature, global |
| `LLM_TIMEOUT` | `600` | |
| `MAX_OUTPUT_TOKENS` | `2048` | per-call cap |
| `BATCH_MAX_CONCURRENCY` | `2` | |
| `BATCH_RETRY_COUNT` / `BATCH_RETRY_DELAY_SECONDS` | `2` / `1.0` | fixed delay, not exponential |
| `PASS_PATTERNS_FILE` / `BATCH_OUTPUT_DIR` | `data/input/pass.json` / `generated_batches` | |
| `EXPECTED_PASS_PATTERN_COUNT` | `83` | hard guard in `load_pass_patterns` |

- **Model list / prices / rate limits: not centralized.** Models are passed per HTTP request.
  `run_judge_evaluation.py` hardcodes `SUPPORTED_JUDGES` + `MODEL_COST_PER_MTOKENS`. Recognition
  scripts hardcode `MODEL = "qwen3-coder-30b-a3b-instruct"`. **There is no per-model price or
  per-model rate-limit table anywhere for the generation side.**
- **Patterns:** `data/input/pass.json` (83). **Domains:** no first-class concept;
  `common_java_projects.json` (12 contexts) is the nearest analogue. **k / repetitions:** none.
- **Temperature sweep:** none; one global value.

**Secrets:**
- `.env` **is gitignored** (`.gitignore` lists `.env`) — good. It currently holds a real
  `OPEN_ROUTER_API_KEY` locally.
- Two env-var spellings are in play: the app reads `OPEN_ROUTER_API_KEY` (pydantic);
  `run_judge_evaluation.py` accepts **either** `OPENROUTER_API_KEY` **or** `OPEN_ROUTER_API_KEY`,
  falling back to `.env`. Part 2 should accept both spellings from the environment and **never**
  read a committed file for the key on the cluster.

**Hard-coded absolute paths (machine-specific) — all on the SCORING side, none block generation:**
- `app/services/ck_metrics.py:26` — `CK_JAR_PATH` default `/Users/hieunguyen/.../ck-…jar` (already
  `os.getenv`-overridable; scoring only).
- `validation/*.py` — many `sys.path.insert("/Users/hieunguyen/…")` and `PROJECT=/Users/…`,
  `KIM_DIR=/Users/…`. Scoring/validation only; **out of scope** (I will not touch them).
- **The generation service itself is already path-clean:** `BatchGenerationService` derives paths
  from `Path(__file__).resolve().parent.parent` and config, so it has no `/Users/...` literals.
  Part 2 keeps that property and makes the output dir a `--output-dir`/config value.

---

## 4. Dependencies & entry (clean-checkout reality)

- **Python:** `.venv` is **3.13.7**.
- **`requirements.txt` is incomplete.** It lists `fastapi, uvicorn[standard], pydantic,
  pydantic-settings, requests, python-multipart`. But the installed venv (and actual runtime) also
  has **`openai==2.32.0`, `PyYAML==6.0.3`, `python-dotenv==1.2.1`**, which `run_judge_evaluation.py`
  and `.env` handling depend on. There is **no lockfile**.
- **For the NEW standalone generation script**, the only additional runtime need beyond stdlib is
  **`requests`** (already listed) and **`PyYAML`** (for `configs/study.yaml`; installed but not in
  `requirements.txt`). I will not require `openai` (the `requests`-based call gives us the `usage`
  block we need). I'll add a small `requirements-generation.txt` so a fresh clone can `pip install`
  exactly what the runner needs.
- **System deps:** Java/Maven and the CK jar are needed **only for scoring metrics**, not for
  generation. Local models need Ollama/LM Studio reachable. Generation itself needs only Python +
  network to OpenRouter.
- **Current launch command (generation):** `uvicorn main:app` then HTTP POSTs — i.e. there is **no
  headless command** suitable for `sbatch`. That's precisely the gap Part 2 fills.

---

## 5. What already exists for robustness (so we don't rebuild it)

| Capability | Generation side today | Best existing reference | Verdict |
|---|---|---|---|
| **Retry** | `BatchGenerationService._generate_pattern_with_retries`: `BATCH_RETRY_COUNT+1` attempts, **fixed 1.0s** delay, retries *any* exception | `run_judge_evaluation.call_judge_with_retries`: **exponential backoff `[2,4,8]`** | Reuse the **judge's** exponential-backoff shape; add 429/5xx/timeout classification |
| **Checkpoint / resume** | `manifest.json` + `results.json` per job, but **new `job_id` each run ⇒ no cross-run resume, re-pays everything** | `run_judge_evaluation`: append-only **JSONL keyed by (pair_id, model)**, skip-if-present on resume; `scripts/run_test_deepseek.py` also skips done patterns | Adopt the **JSONL + skip-if-exists** idiom, keyed by the 4-tuple `(model,pattern,domain,rep)` |
| **Rate-limit handling** | **none** (0 hits for rate-limit/429/backoff on the gen side) | — | Build new: per-model min-interval limiter + `%K` array throttle |
| **Cost tracking** | **none** (client discards the `usage` block) | `run_judge_evaluation`: `MODEL_COST_PER_MTOKENS`, `estimate_cost_usd`, token accounting, per-call + total | Reuse the pricing/estimation shape; **add the hard cap it lacks** |
| **Hard budget ceiling** | **none anywhere** | — | Build new: persisted ledger + pre-call estimate that STOPS before exceeding cap |
| **Parse recovery** | `parse_generated_files` (regex + whole-file fallback) | `run_judge_evaluation`: `strip_code_fences`, `extract_first_json_object` (local) — but it also spends **one extra paid retry** on truncation | Reuse **local** stripping/extraction; **never** make a paid parse-retry; save raw on unrecoverable |
| **Logging** | `logging` in app, `print` in scripts; no run-log file for generation | — | Add timestamped stdout+file logging (lands in Slurm `.out`/`.err`) |
| **Parallelism** | `asyncio` + `Semaphore(2)` | — | Keep it simple: Slurm array shards + a small in-process concurrency/limiter |
| **Returned model-id capture** | **none** | — | Record the API's returned `model` per unit (models drift) |

**Net:** every primitive we need exists in `run_judge_evaluation.py` except a **hard budget
ceiling**, a **rate limiter**, and the **(model,pattern,domain,rep) grid + sharding**. Part 2
assembles the proven pieces into one standalone file and adds those three.

---

## 6. Gap analysis — current pipeline vs. the study

| Study needs | Today | Action in Part 2 |
|---|---|---|
| ~10 models (OpenRouter paid+free, some local Ollama) | one model per job | model **list** in config; per-model provider/price/rate-limit |
| 8 patterns × 7 domains × k=3 | 83 patterns × 1 context × 1 | config-driven `patterns[]`, `domains[]`, `k`; unit = `(model,pattern,domain,rep)` |
| Hard $50 cap, default $40 | none | persisted ledger + pre-call estimate that halts (exit non-zero) |
| Resume under Slurm preempt/requeue | new job_id, re-pays | atomic one-file-per-unit + skip-if-exists |
| Sharded array jobs | n/a | deterministic `--shard i/n` from `$SLURM_ARRAY_TASK_ID/_COUNT` |
| Dry-run / pilot / limit | `run_judge_evaluation` has `--dry-run` only | `--dry-run`, `--pilot` (10/model + cost extrapolation), `--limit N` |
| Per-unit metadata (tokens, cost, latency, returned model-id, status) | discarded | full per-unit record |
| Offline test w/ mock client | none | mock client + robustness checks (Part 3) |

---

## 7. Proposed Part 2 design (for your approval — NOT yet built)

**Shape:** one standalone `generation/run_generation.py` (stdlib + `requests` + `PyYAML`, **no
dependency on the `app` package**, so it copies to a node and is debuggable from log files), one
`configs/study.yaml`, one `slurm/run_generation.sh`, one `docs/how_to_run_on_slurm.md`, plus a
mock-client test path.

**Deliberate, flagged decisions (want your yes/no):**

1. **Self-contained script (no `app` import).** The existing `OllamaClient.generate()` returns only
   the content string, raises FastAPI `HTTPException`, and pulls temperature/`max_tokens` from
   global settings — but the budget ledger **requires per-call token counts and the returned
   model-id**, which it discards. So I propose the standalone file carries its own ~30 lines of
   OpenAI-compatible call (via `requests`, returning `usage`), prompt template (kept **identical**
   to `build_batch_generate_prompt` so outputs stay comparable to the 14 existing jobs), and parse
   recovery. *Alternative:* import `app.services.prompt_service` for prompt+parse and add only the
   client — less duplication, but drags in `pydantic-settings` and couples the runner to the web
   app. **Recommendation: self-contained.**

2. **Output layout = one directory per unit + a JSONL ledger.**
   `<output-dir>/<model>/<pattern>/<domain>/rep<k>/` holding `unit.json` (full metadata) and the
   extracted `.java` files; plus append-only `ledger.jsonl` (cost) and `run.log`. "What's done" =
   `unit.json` with `status in {ok,parse_failed}` exists. Atomic via temp-file + `os.replace`.
   *Alternative:* single big JSONL of all units (compact, but the `.java` payloads bloat it and
   it's harder to eyeball). **Recommendation: per-unit dirs.**

3. **Budget = pre-call worst-case estimate.** Before each paid call, `spent + (est_prompt_tokens ×
   in_price + max_tokens × out_price)`; if that exceeds the cap, stop cleanly and exit non-zero.
   Conservative ⇒ literally cannot overspend. Free-tier/Ollama models priced `$0`. **Recommend.**

4. **The grid contents need your input** (config placeholders otherwise): the **exact 8 patterns**
   (from the 83), the **exact 7 domains** (I'll seed from `common_java_projects.json`), and the
   **real OpenRouter model slugs** (the study names "GPT-5", "Gemini 3.1 Pro", etc. — I'll put
   clearly-marked placeholders and per-model prices you edit; I will not invent billing slugs).

**Everything else** (config-driven knobs, no hard-coded paths/keys, `--shard`, atomic resumable
checkpointing, hard ledger, retry/backoff, rate limit, parse recovery, `--dry-run`, `--pilot`,
`--limit`) is fully specified by your brief and I'll implement it as written.

### Scoring baseline captured (to prove Part 3 leaves it untouched)
- `pytest -q` → **36 passed**
- `validation/run_mutation_battery.py` → **12/12 match label**
- `validation/synthetic_generality_tests.py` → **10/10 pass**
- `app/services/piqs_service.py` SHA-1 `cabe724d1ae7af85aaeca1b874e1c368539436db` (re-checked at the end)

---

**Pausing here** per the brief. Please confirm the four flagged decisions above (or just say "go
with your recommendations"), and I'll build Part 2 + Part 3.
