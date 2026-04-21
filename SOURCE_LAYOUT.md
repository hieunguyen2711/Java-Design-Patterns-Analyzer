# Source Layout

The source code is now organized under the `app/` package by category:

- `app/api` - FastAPI routers and request handling
- `app/core` - shared application configuration
- `app/schemas` - Pydantic request/response models
- `app/services` - business logic and orchestration
- `app/llm` - model client and chunking helpers
- `app/utils` - validation helpers

Main entrypoint:

- `main.py` imports routers and settings from `app/*`.

Supporting folders outside `app/`:

- `scripts/` - data and pipeline scripts
- `tests/` - automated tests
- `data/` - categorized JSON inputs, outputs, reports, and config artifacts