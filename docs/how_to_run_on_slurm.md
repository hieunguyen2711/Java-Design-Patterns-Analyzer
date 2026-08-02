# How to run the generation pipeline on Slurm

A runbook for someone who did **not** write the code. It generates the
**8 PIQS-scoreable patterns × 12 project contexts × k=1 = 96 units** for each of
**two Hugging Face models**, loaded **in-process on a GPU** (no inference server,
**no API key**):

- **Llama 3.1 8B Instruct** → `slurm/run_llama31_8b.sh` / `configs/llama31_8b.yaml`
- **Qwen 2.5 7B Instruct** → `slurm/run_qwen25_7b.sh` / `configs/qwen25_7b.yaml`

Each `.sh` runs the whole grid for one model in a single GPU task (the model
loads once). One Python file (`generation/run_generation.py`) does the work.

> **Golden rule:** re-submitting the same job is always safe. Completed units are
> skipped, so a preempted or failed job just resumes — `sbatch` again.

---

## 0. One-time setup (on the cluster, from the repo root)

```bash
python -m venv .venv && source .venv/bin/activate        # or a conda env

# Core runner deps:
pip install -r requirements-generation.txt               # PyYAML (+ requests)

# GPU backend: install torch matching your cluster CUDA FIRST, then the HF libs.
module load cuda/12.1                                     # (or your cluster's module)
pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements-hf.txt                        # transformers + accelerate
```

**Hugging Face model access:**
- **Qwen 2.5 7B** is ungated — nothing to do.
- **Llama 3.1 8B** is **gated**: accept the license on its HF model page, then
  authenticate once so the weights can download (this is a *download* token, not
  an inference API key):
  ```bash
  huggingface-cli login          # paste an HF token, OR:
  mkdir -p ~/.config/dp-generation
  printf 'export HF_TOKEN="hf_..."\n' > ~/.config/dp-generation/hf.sh   # the .sh sources this
  chmod 600 ~/.config/dp-generation/hf.sh
  ```

**Optional — cache weights on scratch** so they persist across jobs:
```bash
export HF_HOME="$SCRATCH/hf_cache"
```

---

## 1. Dry run first (no GPU, no generation)

Confirms the grid and config parse. Run on a login node:
```bash
python generation/run_generation.py --config configs/llama31_8b.yaml --dry-run
python generation/run_generation.py --config configs/qwen25_7b.yaml  --dry-run
```
Each prints `Grid: 8 patterns x 12 contexts x k=1 = 96 total units`.

---

## 2. Submit the two jobs

Edit each `.sh`'s `#SBATCH` header for your cluster — set your real
`--partition` (a **GPU** partition) and `--account`. The GPU request
(`--gres=gpu:1`), time, mem, and CPUs are pre-filled with sensible defaults.

```bash
# optional: point output at fast scratch
export OUTPUT_DIR="$SCRATCH/gen_llama31_8b"
sbatch slurm/run_llama31_8b.sh

export OUTPUT_DIR="$SCRATCH/gen_qwen25_7b"
sbatch slurm/run_qwen25_7b.sh
```

(Or run directly on any GPU machine without Slurm: `bash slurm/run_llama31_8b.sh`.)

Watch it:
```bash
squeue --me
tail -f logs/dp-gen-llama31-8b_*.out              # stdout (also in the output dir's run.log)
find "$OUTPUT_DIR" -name unit.json | wc -l         # completed units (out of 96)
```

The first unit is slow (the model loads); after that each unit is a generate call.

---

## 3. Preemption / requeue / failure — just re-submit

Each unit is written **atomically** (temp file + rename), so a task killed
mid-unit never leaves a half-written record that looks complete. On the next run
that unit re-generates; finished units are skipped.

- With `#SBATCH --requeue` (commented; uncomment to enable), Slurm requeues
  preempted tasks automatically.
- Otherwise, or after any failure, **just submit again** — it resumes and does
  only the missing units:
  ```bash
  sbatch slurm/run_llama31_8b.sh     # same config, same OUTPUT_DIR
  ```

---

## 4. Output layout & exit codes

Per unit (`$OUTPUT_DIR/<pattern>/<context>/rep<k>/`):

```
unit.json          full metadata: model, model_returned, pattern, context, rep,
                   temperature, max_tokens, prompt hash, tokens in/out, status,
                   finish_reason, extracted files, parse method, latency
prompt.txt         the exact prompt sent
raw_response.txt   the raw model output
<ClassName>.java   one file per generated class/interface
```

`unit.json` is written **last**, so its presence = the unit is complete.

Exit codes: `0` success · `4` every attempted unit failed (e.g. model failed to
load / OOM — check `run.log`).

---

## 5. Quick reference

| Goal | Command |
|---|---|
| Dry run (free, no GPU) | `python generation/run_generation.py --config configs/qwen25_7b.yaml --dry-run` |
| Smoke test (3 real units) | `python generation/run_generation.py --config configs/qwen25_7b.yaml --limit 3` |
| Full run, Llama 3.1 8B | `sbatch slurm/run_llama31_8b.sh` |
| Full run, Qwen 2.5 7B | `sbatch slurm/run_qwen25_7b.sh` |
| Resume after preemption | `sbatch slurm/run_<model>.sh` (same config + `OUTPUT_DIR`) |
| Count completed units | `find "$OUTPUT_DIR" -name unit.json | wc -l` |

**Config knobs** (`configs/<model>.yaml`): `model.id/dtype/device`, the 8
`patterns`, `contexts_file`, `generation.k/temperature/max_tokens`.
**Env vars:** `OUTPUT_DIR` (scratch path) · `HF_HOME` (weight cache) · `HF_TOKEN`
(only to download the gated Llama model).
