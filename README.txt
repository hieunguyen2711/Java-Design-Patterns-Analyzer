DP RECOGNITION BACKEND - README
================================

What this project does
----------------------
This backend analyzes Java projects for design pattern usage and quality metrics.
It exposes FastAPI endpoints to:
- Analyze uploaded Java projects (ZIP or multiple .java files) with an LLM.
- Generate Java code for specific design patterns.
- Ask follow-up questions about a prior analysis.
- Package generated files into a downloadable Maven project ZIP.
- Run project metrics (CK + Maintainability Index) for uploaded ZIPs or local directories.
- Compute PIQS scores for supported patterns.
- Run batch generation jobs for passing patterns and track/download results.

The API is designed to work with:
- Ollama (local model server), and
- optional OpenRouter configuration via environment variables.


Core flow
---------
1) Client uploads Java input (ZIP or files) or sends generation request.
2) Backend validates input and checks LLM availability when needed.
3) Services orchestrate prompt building, LLM calls, parsing, and file processing.
4) API returns structured JSON responses (analysis, generation, metrics, status, etc.).


Project structure (important folders)
-------------------------------------
- app/api
  FastAPI routers and HTTP endpoints.
- app/core
  Application settings and environment configuration.
- app/schemas
  Request/response Pydantic models.
- app/services
  Business logic (analysis pipeline, metrics, batching, file handling).
- app/llm
  LLM client and chunking helpers.
- app/utils
  Utility helpers.
- scripts
  Pipeline and data-processing scripts.
- tests
  Automated tests.
- data/config
  Reusable config artifacts.
- data/input
  Input JSONs consumed by scripts/services.
- data/outputs
  Generated output artifacts.
- data/reports
  Validation/report files.
- generated_batches
  Batch generation workspace and job artifacts.


Main API endpoints
------------------
General + analysis:
- POST /analyze
  Upload a ZIP Java project and run pattern analysis.
- POST /analyze-folder
  Upload multiple .java files and run pattern analysis.
- POST /followup
  Ask a follow-up question based on a previous analysis response.
- GET /health
  Health status for API and model service.

Model information:
- GET /models
  List available Ollama models.

Code generation + packaging:
- POST /generate
  Generate Java files for a selected design pattern.
- POST /package
  Package generated files into a Maven project ZIP.

Batch generation workflow:
- POST /api/v1/generate-pass-projects
  Start async batch generation for pass patterns.
- GET /api/v1/generate-pass-projects/{job_id}
  Get batch job status/results.
- GET /api/v1/generate-pass-projects/{job_id}/download
  Download final ZIP for a completed job.
- GET /api/v1/generate-pass-projects/{job_id}/analyze-metrics
  Run metrics across generated outputs for that job.

Metrics + PIQS:
- POST /api/v1/analyze-metrics
  Upload ZIP and compute CK + MI.
- POST /api/v1/analyze-metrics-dir
  Compute CK + MI for a local directory path.
- POST /api/v1/analyze-piqs
  Compute PIQS for uploaded .java files and a supported pattern.


Requirements
------------
- Python 3.10+
- Dependencies in requirements.txt
- Ollama running if you use analysis/generation/follow-up/model-list endpoints
  (unless you switch to OpenRouter mode in settings)


Quick start
-----------
1) Create and activate a virtual environment:
   python -m venv .venv
   source .venv/bin/activate

2) Install dependencies:
   pip install -r requirements.txt

3) Configure environment (optional but recommended):
   Create/update .env in project root.

4) Start the API server:
   uvicorn main:app --reload

5) Open API docs:
   http://127.0.0.1:8000/docs


Key environment settings
------------------------
From app/core/config.py (defaults shown in code):
- OLLAMA_BASE_URL
- DEFAULT_MODEL
- USE_OPEN_ROUTER
- OPEN_ROUTER_BASE_URL
- OPEN_ROUTER_API_KEY
- MAX_FILE_SIZE_MB
- MAX_JAVA_FILES
- MAX_CHARS_PER_CHUNK
- BATCH_MAX_CONCURRENCY
- BATCH_RETRY_COUNT
- PASS_PATTERNS_FILE


Notes
-----
- Uploaded files are stored temporarily and cleaned up by file services.
- Batch generation outputs are persisted under generated_batches/.
- Metrics endpoints validate that .java files exist before processing.
- API startup logs show backend URL, Ollama status, and default model.
