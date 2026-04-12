"""
shannon_entropy_weights.py

Computes Shannon entropy-based weights for the CK sub-metrics
(CBO, LCOM*, RFC, DIT) from your generated project data.

Entropy weighting gives higher weight to metrics that vary more
across your dataset — metrics with more variation carry more
discriminating information about which projects are better or worse.

Usage:
    python3 shannon_entropy_weights.py

Input:  generated_common_projects_pipeline_results.json (same directory)
Output: prints weights + saves to entropy_weights.json

Requires: numpy
    pip install numpy
"""

import json
import math
import numpy as np
from pathlib import Path


# ── Desirability normalization thresholds ───────────────────────

CBO_UPPER = 14.0    # Shatnawi (2010, IEEE TSE)
RFC_UPPER = 50.0    # Shatnawi (2010, IEEE TSE)
DIT_TARGET = 2.0    # Small LLM-generated projects
DIT_SPREAD = 3.0    # Score hits 0 at DIT = 5


def normalize(rows: list[dict]) -> list[dict]:
    """Apply desirability functions to raw metrics.
    
    Each metric is converted to [0, 1] where 1 = best quality.
    """
    normalized = []
    for r in rows:
        normalized.append({
            "project": r["project"],
            "pattern": r["pattern"],
            # Higher is better → divide by max
            "d_CBO": max(0.001, (CBO_UPPER - r["CBO"]) / CBO_UPPER),
            # Higher LCOM* = worse → flip
            "d_LCOM": max(0.001, 1.0 - r["LCOM*"]),
            # Higher RFC = worse → flip with threshold
            "d_RFC": max(0.001, (RFC_UPPER - r["RFC"]) / RFC_UPPER),
            # Target = 2 is best → tent function
            "d_DIT": max(0.001, min(1.0, 1.0 - abs(r["DIT"] - DIT_TARGET) / DIT_SPREAD)),
        })
    return normalized


def compute_entropy_weights(normalized: list[dict], metric_names: list[str]) -> dict:
    """Compute Shannon entropy weights step by step.
    
    Steps:
        1. For each metric, turn all values into proportions (p_i = value_i / sum)
        2. Compute entropy: E = -(1/ln(n)) × Σ(p × ln(p))
           - E close to 1 = all values similar = low information
           - E close to 0 = values vary a lot = high information
        3. Diversification: d = 1 - E (higher = more informative)
        4. Weight: w = d / sum(all d)
    """
    n = len(normalized)
    k = 1.0 / math.log(n)  # normalization constant
    eps = 1e-10

    print(f"Number of data points (n): {n}")
    print(f"Normalization constant (k = 1/ln({n})): {k:.6f}")
    print()

    diversifications = {}

    for name in metric_names:
        values = np.array([row[name] for row in normalized])

        # Show distribution
        print(f"{'─' * 50}")
        print(f"METRIC: {name}")
        print(f"  Range:  {values.min():.4f} to {values.max():.4f}")
        print(f"  Mean:   {values.mean():.4f}")
        print(f"  Std:    {values.std():.4f}")

        # Step 1: Proportions
        total = values.sum()
        p = values / total
        print(f"  Sum:    {total:.4f}")
        print(f"  Sample proportions: [{p[0]:.6f}, {p[1]:.6f}, {p[2]:.6f}, ...]")

        # Step 2: Entropy
        p_clipped = np.clip(p, eps, 1.0)
        E = -k * np.sum(p_clipped * np.log(p_clipped))
        print(f"  Entropy (E): {E:.6f}")
        print(f"    → {'HIGH (values are uniform — low information)' if E > 0.999 else 'MODERATE (some variation — carries information)' if E > 0.99 else 'LOW (high variation — very informative)'}")

        # Step 3: Diversification
        d = 1.0 - E
        diversifications[name] = d
        print(f"  Diversification (1 - E): {d:.6f}")
        print()

    # Step 4: Normalize to weights
    total_div = sum(diversifications.values())

    print(f"{'─' * 50}")
    print(f"FINAL WEIGHTS")
    print(f"{'─' * 50}")
    print(f"  Sum of diversifications: {total_div:.6f}")
    print()

    weights = {}
    for name in metric_names:
        w = diversifications[name] / total_div
        weights[name] = w
        bar = "█" * int(w * 40)
        print(f"  {name:6s}: {w:.4f}  {bar}")

    print(f"\n  Sum of weights: {sum(weights.values()):.4f}")
    return weights


def main():
    # Load data
    input_file = Path("generated_common_projects_pipeline_results.json")
    if not input_file.exists():
        print(f"ERROR: {input_file} not found")
        return

    with open(input_file) as f:
        data = json.load(f)

    # Extract raw metrics
    rows = []
    for p in data["projects"]:
        for pat in p["metrics"]["patterns"]:
            if pat["status"] != "success":
                continue
            rows.append({
                "project": p["project_title"],
                "pattern": pat["pattern"],
                "CBO": pat["ck"]["avg_cbo"],
                "LCOM*": pat["ck"]["avg_lcom_star"],
                "RFC": pat["ck"]["avg_rfc"],
                "DIT": pat["ck"]["avg_dit"],
            })

    print(f"Loaded {len(rows)} evaluations\n")

    # Normalize
    normalized = normalize(rows)

    # Compute weights
    print("=" * 50)
    print("SHANNON ENTROPY WEIGHT COMPUTATION")
    print("=" * 50)
    print()

    metric_names = ["d_CBO", "d_LCOM", "d_RFC", "d_DIT"]
    weights = compute_entropy_weights(normalized, metric_names)

    # Clean names for output
    clean_weights = {
        "CBO": weights["d_CBO"],
        "LCOM*": weights["d_LCOM"],
        "RFC": weights["d_RFC"],
        "DIT": weights["d_DIT"],
    }

    # Show the resulting formula
    print(f"\n{'=' * 50}")
    print("YOUR CK SUB-SCORE FORMULA")
    print("=" * 50)
    print()
    print("  CK_q = d_CBO^{:.3f} × d_LCOM^{:.3f} × d_RFC^{:.3f} × d_DIT^{:.3f}".format(
        clean_weights["CBO"], clean_weights["LCOM*"],
        clean_weights["RFC"], clean_weights["DIT"]
    ))
    print()
    print("  where:")
    print(f"    d_CBO  = (14 - CBO) / 14")
    print(f"    d_LCOM = 1 - LCOM*")
    print(f"    d_RFC  = (50 - RFC) / 50")
    print(f"    d_DIT  = 1 - |DIT - 2| / 3")

    # Save
    output = {
        "config": {
            "n_evaluations": len(rows),
            "cbo_upper": CBO_UPPER,
            "rfc_upper": RFC_UPPER,
            "dit_target": DIT_TARGET,
            "dit_spread": DIT_SPREAD,
        },
        "weights": {k: round(v, 4) for k, v in clean_weights.items()},
    }
    output_file = Path("entropy_weights.json")
    output_file.write_text(json.dumps(output, indent=2))
    print(f"\nSaved weights to {output_file}")


if __name__ == "__main__":
    main()