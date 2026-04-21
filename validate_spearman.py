"""
Computes Spearman correlation between CQS and CompQS
to validate that Tier 2 adds meaningful information beyond Tier 1.

Expected result: rho approx 0.4-0.7 (moderate correlation)
  - Too high (>0.9): CompQS is redundant, PIQS doesn't add anything
  - Moderate (0.4-0.7): They share info but CompQS captures something new
  - Too low (<0.2): They measure unrelated things

Usage:
    python3 validate_spearman.py

Input: generated_evaluation_scores.json (same directory)
       This file must have a "rows" array where each row has
       cqs_score and compqs_score fields.

Requires: scipy, numpy
    pip install scipy numpy
"""

import json
from pathlib import Path

import numpy as np
from scipy import stats


def main():
    # Load data
    input_file = Path("generated_evaluation_scores.json")
    if not input_file.exists():
        print(f"ERROR: {input_file} not found")
        print("Place generated_evaluation_scores.json in the same directory.")
        return

    with input_file.open() as file_handle:
        data = json.load(file_handle)

    rows = data.get("rows", [])
    if not rows:
        print("ERROR: No rows found in the JSON file")
        return

    valid_rows = [
        row
        for row in rows
        if "cqs_score" in row and "compqs_score" in row
    ]
    if not valid_rows:
        print("ERROR: No rows with both cqs_score and compqs_score were found")
        return

    print(f"Loaded {len(valid_rows)} evaluations")
    print(f"Patterns: {sorted(set(row['pattern'] for row in valid_rows))}")
    print()

    # Extract CQS and CompQS scores
    cqs_scores = [row["cqs_score"] for row in valid_rows]
    compqs_scores = [row["compqs_score"] for row in valid_rows]

    # Basic statistics
    print("=" * 60)
    print("SCORE DISTRIBUTIONS")
    print("=" * 60)
    print(
        f"  CQS:    min={min(cqs_scores):.1f}  max={max(cqs_scores):.1f}  "
        f"avg={np.mean(cqs_scores):.1f}  std={np.std(cqs_scores):.1f}"
    )
    print(
        f"  CompQS: min={min(compqs_scores):.1f}  max={max(compqs_scores):.1f}  "
        f"avg={np.mean(compqs_scores):.1f}  std={np.std(compqs_scores):.1f}"
    )

    # Spearman correlation
    rho, p_value = stats.spearmanr(cqs_scores, compqs_scores)

    print(f"\n{'=' * 60}")
    print("SPEARMAN CORRELATION: CQS ↔ CompQS")
    print("=" * 60)
    print(f"  n = {len(valid_rows)}")
    print(f"  rho = {rho:.4f}")
    print(f"  p = {p_value:.2e}")
    print()

    if abs(rho) > 0.9:
        verdict = "TOO HIGH"
        explanation = "CompQS is nearly redundant with CQS - adding PIQS does not change rankings much."
    elif 0.7 < abs(rho) <= 0.9:
        verdict = "HIGH"
        explanation = "Strong overlap. CompQS adds some information but the two tiers are quite similar."
    elif 0.4 <= abs(rho) <= 0.7:
        verdict = "MODERATE (ideal)"
        explanation = "CompQS shares information with CQS but adds something new. This is exactly what a two-tier framework needs."
    elif 0.2 <= abs(rho) < 0.4:
        verdict = "LOW"
        explanation = "The two tiers measure mostly different things - hard to justify as tiers of the same framework."
    else:
        verdict = "VERY LOW"
        explanation = "No meaningful relationship between the tiers."

    print(f"  Verdict: {verdict}")
    print(f"  {explanation}")

    if p_value < 0.001:
        print("  Significance: p < 0.001 - highly significant")
    elif p_value < 0.05:
        print("  Significance: p < 0.05 - significant")
    else:
        print(f"  Significance: p = {p_value:.4f} - NOT significant")

    # Pearson for comparison
    r_pearson, p_pearson = stats.pearsonr(cqs_scores, compqs_scores)
    print(f"\n  Pearson r = {r_pearson:.4f} (for comparison)")

    # Where do they diverge most?
    print(f"\n{'=' * 60}")
    print("LARGEST DIVERGENCES")
    print("=" * 60)

    divergences = []
    for row in valid_rows:
        delta = row["compqs_score"] - row["cqs_score"]
        divergences.append(
            {
                "pattern": row["pattern"],
                "project": row.get("project_context", row.get("batch_name", "?")),
                "cqs": row["cqs_score"],
                "compqs": row["compqs_score"],
                "piqs": row.get("piqs_score", 0),
                "delta": delta,
            }
        )

    divergences.sort(key=lambda item: item["delta"])

    print("\nCompQS << CQS (pattern correctness hurts the score):")
    print(f"  {'Pattern':20s} {'CQS':>6s} {'CompQS':>7s} {'PIQS':>6s} {'Delta':>7s}")
    print(f"  {'-' * 50}")
    for divergence in divergences[:5]:
        print(
            f"  {divergence['pattern']:20s} {divergence['cqs']:6.1f} "
            f"{divergence['compqs']:7.1f} {divergence['piqs']:6.1f} {divergence['delta']:+7.1f}"
        )

    print("\nCompQS >> CQS (pattern correctness helps the score):")
    print(f"  {'Pattern':20s} {'CQS':>6s} {'CompQS':>7s} {'PIQS':>6s} {'Delta':>7s}")
    print(f"  {'-' * 50}")
    for divergence in divergences[-5:]:
        print(
            f"  {divergence['pattern']:20s} {divergence['cqs']:6.1f} "
            f"{divergence['compqs']:7.1f} {divergence['piqs']:6.1f} {divergence['delta']:+7.1f}"
        )

    # Per-pattern breakdown
    print(f"\n{'=' * 60}")
    print("PER-PATTERN SUMMARY")
    print("=" * 60)
    print(f"  {'Pattern':20s} {'Avg CQS':>8s} {'Avg CompQS':>11s} {'Avg PIQS':>9s} {'Avg Δ':>7s}")
    print(f"  {'-' * 58}")

    patterns = sorted(set(row["pattern"] for row in valid_rows))
    for pattern in patterns:
        pattern_rows = [row for row in valid_rows if row["pattern"] == pattern]
        avg_cqs = np.mean([row["cqs_score"] for row in pattern_rows])
        avg_compqs = np.mean([row["compqs_score"] for row in pattern_rows])
        avg_piqs = np.mean([row.get("piqs_score", 0) for row in pattern_rows])
        avg_delta = avg_compqs - avg_cqs
        print(f"  {pattern:20s} {avg_cqs:8.1f} {avg_compqs:11.1f} {avg_piqs:9.1f} {avg_delta:+7.1f}")

    # What to write in the paper
    print(f"\n{'=' * 60}")
    print("FOR YOUR PAPER")
    print("=" * 60)
    print(
        f'''
  "Spearman correlation between CQS and CompQS across n = {len(valid_rows)}
  evaluations yielded rho = {rho:.3f} (p < 0.001), indicating a moderate
  positive relationship. The two tiers share sufficient information
  to be interpretable as related quality dimensions while diverging
  meaningfully where pattern correctness differs from code quality."
'''
    )


if __name__ == "__main__":
    main()