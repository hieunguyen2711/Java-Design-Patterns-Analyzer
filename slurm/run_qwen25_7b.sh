#!/bin/bash
# =============================================================================
# run_qwen25_7b.sh -- generate the full grid with Qwen 2.5 7B Instruct,
# loading the model IN-PROCESS on a GPU node (Hugging Face transformers).
# No inference server and NO API key.
#
# Works two ways from the same file:
#   * Slurm:    sbatch slurm/run_qwen25_7b.sh
#   * Directly: bash slurm/run_qwen25_7b.sh       (on a machine with a GPU)
#
# The model loads once and generates all 96 units, so this is a SINGLE task
# (no array). Every unit is checkpointed and resume-skips completed units, so
# re-running is idempotent -- if it's preempted or fails, just submit again.
#
# EDIT the #SBATCH placeholders (partition/account) for your cluster.
# =============================================================================

# ---- Slurm directives (used by `sbatch`; ignored by `bash`) -----------------
#SBATCH --job-name=dp-gen-qwen25-7b
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --gres=gpu:1                          # 7B in bf16 needs ~15 GB VRAM; one GPU is enough
# #SBATCH --partition=YOUR_GPU_PARTITION      # <-- set your real GPU partition
# #SBATCH --account=YOUR_ACCOUNT              # <-- set your real account/allocation
# #SBATCH --requeue                           # <-- optional: safe (resume is idempotent)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
mkdir -p logs

CONFIG="${CONFIG:-configs/qwen25_7b.yaml}"
# Point OUTPUT_DIR at fast scratch, e.g.: export OUTPUT_DIR="$SCRATCH/gen_qwen25_7b"
OUTPUT_DIR="${OUTPUT_DIR:-generated_batches_qwen25_7b}"

# ---- Environment (edit to match your cluster) -------------------------------
if [[ -f "$REPO_ROOT/.venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "$REPO_ROOT/.venv/bin/activate"
# else
#   module load cuda/12.1
#   source /path/to/conda/etc/profile.d/conda.sh && conda activate dp-gen
fi

# ---- Hugging Face cache (Qwen 2.5 is ungated -- no token needed) -------------
# Cache weights on scratch so they persist across jobs (optional):
# export HF_HOME="$SCRATCH/hf_cache"

echo "[$(date -u +%FT%TZ)] host=$(hostname) job=${SLURM_JOB_ID:-none} gpu=${CUDA_VISIBLE_DEVICES:-none}"
echo "[$(date -u +%FT%TZ)] config=${CONFIG} output=${OUTPUT_DIR}"

python generation/run_generation.py --config "$CONFIG" --output-dir "$OUTPUT_DIR"
EXIT_CODE=$?

echo "[$(date -u +%FT%TZ)] run_generation.py exited ${EXIT_CODE}"
exit $EXIT_CODE
