# Data Layout

JSON files are grouped by purpose under `data/`:

- `data/config/` - reusable configuration artifacts, for example `entropy_weights.json`
- `data/input/` - source inputs consumed by scripts and services, for example `common_java_projects.json`, `results.json`, `pass.json`
- `data/outputs/` - generated batch results, LLM test outputs, and metric artifacts
- `data/reports/` - analysis and validation outputs intended for review, for example `spearman_validation_result.json`

The batch job workspace remains in `generated_batches/` because it is a structured artifact directory rather than a flat JSON dump.