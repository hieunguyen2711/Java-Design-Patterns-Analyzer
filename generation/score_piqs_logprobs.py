#!/usr/bin/env python3
"""
score_piqs_logprobs.py -- Stage A of the logprob pilot: PIQS-score a generated
output tree and emit a per-unit CSV keyed by unit_id.

This is the SEPARATE scoring step. It imports the existing, validated scorer
(app.services.piqs_service.PIQSService) UNMODIFIED -- exactly like
validation/run_scorer.py -- and applies it to the run_generation_logprobs.py
output layout:

    <output-dir>/<model-tag>/seed_<seed>/<pattern>/<context>/rep<n>/{*.java, unit.json}

For each unit it reads that unit's .java files + its pattern from unit.json,
runs PIQSService.evaluate (pure static analysis of source -- NO javac), and
records PSR / CPC / PIQS / grade. The output CSV is exactly what
analyze_logprob_separation.py consumes via --piqs-results.

PIQS is written as a raw percent (0-100), NOT a pass/fail label, so you pick the
pass rule at analyze time and can sweep it without re-scoring:
    * threshold on PIQS %:   analyze ... --piqs-results piqs_<model>.csv --threshold 70
    * (grade is also in the CSV for eyeballing / a grade-based rule later)

Run ONE per model so each analysis stays within a single model (logprob scales
are not comparable across models/tokenizers):

    python generation/score_piqs_logprobs.py \
        --output-dir data/outputs/generated_logprobs/qwen25_7b \
        --out piqs_qwen25_7b.csv

Depends only on the repo's PIQSService (no new third-party deps).
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import warnings
from collections import Counter
from pathlib import Path
from typing import Optional

# Quiet a harmless pydantic protected-namespace warning emitted on import of the
# app package; it has nothing to do with scoring.
warnings.filterwarnings("ignore", message='Field "model_used" has conflict')

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.piqs_service import PIQSService  # noqa: E402  (after sys.path insert)

# CSV columns. NOTE: do NOT name the generation-status column "status" -- the
# analyzer auto-detects its pass/fail column from ("status","passed","pass",
# "result","piqs","score",...) in order, and "status" would hijack "piqs".
# Hence "gen_status". The analyzer picks "piqs" (first value-field present).
FIELDNAMES = ["unit_id", "seed", "pattern", "gen_status", "num_files", "psr", "cpc", "piqs", "grade", "error"]


def pattern_to_slug(pattern: str) -> str:
    """'Factory Method' -> 'factory-method' (PIQSService keys are hyphenated,
    and evaluate() only lowercases -- it does not replace spaces)."""
    return pattern.strip().lower().replace(" ", "-")


def score_unit(svc: PIQSService, unit_json: Path) -> dict:
    """Score one unit dir. Never raises -- errors land in the 'error' column."""
    unit_dir = unit_json.parent
    row = {k: "" for k in FIELDNAMES}
    try:
        rec = json.loads(unit_json.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        row["error"] = f"bad unit.json: {exc}"
        return row

    row["unit_id"] = rec.get("unit_id", "")
    row["seed"] = rec.get("seed", "")
    row["pattern"] = rec.get("pattern", "")
    row["gen_status"] = rec.get("status", "")

    if rec.get("status") != "ok":
        # failed / parse_failed units have no usable .java -- leave PIQS blank.
        row["error"] = f"skipped: generation status={rec.get('status')!r}"
        return row

    java_files = {p.name: p.read_text(encoding="utf-8", errors="ignore")
                  for p in sorted(unit_dir.glob("*.java"))}
    row["num_files"] = len(java_files)
    if not java_files:
        row["error"] = "no .java files in unit dir"
        return row

    slug = pattern_to_slug(rec.get("pattern", ""))
    try:
        res = svc.evaluate(pattern_name=slug, java_files=java_files)
    except Exception as exc:  # unsupported pattern, parse error, etc.
        row["error"] = f"evaluate failed ({slug}): {exc}"
        return row

    row["psr"] = res["breadth_calculation_psr"]["result_percent"]
    row["cpc"] = res["depth_calculation_cpc"]["result_percent"]
    row["piqs"] = res["final_quality_result_piqs"]["result_percent"]
    row["grade"] = res["grade"]
    return row


def summarize(rows: list, out_path: Path) -> None:
    scored = [r for r in rows if r["piqs"] != ""]
    errored = [r for r in rows if r["error"]]
    print(f"\nWrote {out_path}")
    print(f"  units seen    : {len(rows)}")
    print(f"  units scored  : {len(scored)}")
    if errored:
        print(f"  units errored/skipped : {len(errored)} (see 'error' column)")
    if not scored:
        print("  !! nothing scored -- check --output-dir points at a generated tree.")
        return

    vals = [float(r["piqs"]) for r in scored]
    grades = Counter(r["grade"] for r in scored)
    print("\nPIQS distribution (to help you choose --threshold):")
    print(f"  n={len(vals)}  min={min(vals):.1f}  median={statistics.median(vals):.1f}  "
          f"mean={statistics.mean(vals):.1f}  max={max(vals):.1f}")
    print("  grades: " + ", ".join(f"{g}={grades[g]}" for g in ("Excellent", "Good", "Moderate", "Poor") if grades.get(g)))
    print("  pass counts at candidate thresholds (pass := PIQS >= T):")
    for t in (50, 70, 90, 100):
        n_pass = sum(1 for v in vals if v >= t)
        print(f"    T={t:>3}: pass={n_pass:>3}  fail={len(vals) - n_pass:>3}")
    print("\nNext: python generation/analyze_logprob_separation.py "
          f"--output-dir <same dir> --piqs-results {out_path} --threshold <T>")


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="PIQS-score a logprob-pilot output tree into a unit_id-keyed CSV.")
    ap.add_argument("--output-dir", required=True,
                    help="A model's output tree (searched recursively for unit.json). Score ONE model per run.")
    ap.add_argument("--out", default=None,
                    help="Output CSV path. Default: piqs_<output-dir-basename>.csv in the CWD.")
    ap.add_argument("--limit", type=int, default=None, help="Score at most N units (smoke test).")
    args = ap.parse_args(argv)

    out_dir = Path(args.output_dir)
    if not out_dir.exists():
        raise SystemExit(f"--output-dir not found: {out_dir}")
    out_path = Path(args.out) if args.out else Path(f"piqs_{out_dir.name}.csv")

    unit_jsons = sorted(out_dir.rglob("unit.json"))
    if args.limit is not None:
        unit_jsons = unit_jsons[:args.limit]
    if not unit_jsons:
        raise SystemExit(f"No unit.json found under {out_dir}.")

    svc = PIQSService()
    rows = [score_unit(svc, uj) for uj in unit_jsons]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    summarize(rows, out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
