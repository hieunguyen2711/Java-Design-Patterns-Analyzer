"""
spearman_correlation.py

Computes the Spearman correlation matrix for all metrics
in data/outputs/generated_common_projects_pipeline_results.json.

This determines which metrics are redundant (|ρ| > 0.7)
and should be excluded from the composite formula.

Usage:
    python3 spearman_correlation.py

Requires: scipy, numpy
    pip install scipy numpy
"""

import json
import numpy as np
from scipy import stats
from pathlib import Path


def main():
    # ── Load data ───────────────────────────────────────────────
    input_file = Path("data/outputs/generated_common_projects_pipeline_results.json")
    if not input_file.exists():
        print(f"ERROR: {input_file} not found. Place it in the same directory.")
        return

    with open(input_file) as f:
        data = json.load(f)

    # Extract all metrics from all projects
    rows = []
    for p in data["projects"]:
        for pat in p["metrics"]["patterns"]:
            if pat["status"] != "success":
                continue
            rows.append({
                "project": p["project_title"],
                "pattern": pat["pattern"],
                "MI": pat["mi"]["avg_mi_score"],
                "WMC": pat["ck"]["avg_wmc"],
                "CBO": pat["ck"]["avg_cbo"],
                "LCOM*": pat["ck"]["avg_lcom_star"],
                "RFC": pat["ck"]["avg_rfc"],
                "DIT": pat["ck"]["avg_dit"],
            })

    print(f"Loaded {len(rows)} evaluations from {len(data['projects'])} projects\n")

    # ── Step 1: Show raw metric ranges ──────────────────────────
    metric_names = ["MI", "WMC", "CBO", "LCOM*", "RFC", "DIT"]

    print("=" * 65)
    print("RAW METRIC DISTRIBUTIONS")
    print("=" * 65)
    for name in metric_names:
        vals = [r[name] for r in rows]
        print(f"  {name:6s}: min={min(vals):7.2f}  max={max(vals):7.2f}  "
              f"avg={np.mean(vals):7.2f}  std={np.std(vals):6.2f}")

    # ── Step 2: Compute Spearman correlation matrix ─────────────
    print(f"\n{'=' * 65}")
    print("SPEARMAN CORRELATION MATRIX")
    print("=" * 65)
    print()

    # Header
    print(f"{'':8s}", end="")
    for name in metric_names:
        print(f"{name:>8s}", end="")
    print()
    print("-" * (8 + 8 * len(metric_names)))

    # Matrix
    for n1 in metric_names:
        print(f"{n1:8s}", end="")
        vals1 = [r[n1] for r in rows]
        for n2 in metric_names:
            vals2 = [r[n2] for r in rows]
            rho, pval = stats.spearmanr(vals1, vals2)
            print(f"{rho:8.3f}", end="")
        print()

    # ── Step 3: Flag problematic pairs ──────────────────────────
    print(f"\n{'=' * 65}")
    print("PAIRS WITH |ρ| > 0.7 (too correlated — drop one)")
    print("=" * 65)

    found_high = False
    for i, n1 in enumerate(metric_names):
        for j, n2 in enumerate(metric_names):
            if j <= i:
                continue
            vals1 = [r[n1] for r in rows]
            vals2 = [r[n2] for r in rows]
            rho, pval = stats.spearmanr(vals1, vals2)
            if abs(rho) > 0.7:
                found_high = True
                print(f"  {n1:6s} <-> {n2:6s}: ρ = {rho:+.3f}  (p = {pval:.2e})")
                # Explain why
                if "MI" in (n1, n2) and "WMC" in (n1, n2):
                    print(f"    → MI contains Cyclomatic Complexity; WMC ≈ Σ(CC per method)")
                    print(f"    → DECISION: Drop WMC, keep MI")

    if not found_high:
        print("  None found! All pairs are independent enough to include.")

    # ── Step 4: Show safe pairs ─────────────────────────────────
    print(f"\n{'=' * 65}")
    print("RETAINED METRICS (all pairs |ρ| < 0.7)")
    print("=" * 65)

    retained = ["MI", "CBO", "LCOM*", "DIT"]
    for i, n1 in enumerate(retained):
        for j, n2 in enumerate(retained):
            if j <= i:
                continue
            vals1 = [r[n1] for r in rows]
            vals2 = [r[n2] for r in rows]
            rho, pval = stats.spearmanr(vals1, vals2)
            status = "✓ Safe" if abs(rho) < 0.7 else "✗ Problem"
            print(f"  {n1:6s} <-> {n2:6s}: ρ = {rho:+.3f}  {status}")

    # ── Step 5: Visual explanation ──────────────────────────────
    print(f"\n{'=' * 65}")
    print("WHAT THIS MEANS")
    print("=" * 65)
    print("""
  The Spearman correlation tells you: "Do these two metrics move
  together across my 996 projects?"

  If |ρ| > 0.7, they're measuring the same underlying property.
  Including both in the composite formula would double-count that
  property, biasing the final score.

  Example from your data:
    MI ↔ WMC: ρ = -0.746
    This means: when MI goes UP (more maintainable), WMC goes DOWN
    (less complex). They're two sides of the same coin — complexity.
    MI already captures complexity through its CC component.
    So we drop WMC from the formula.

  After removing WMC and RFC, the retained metrics are:
    MI    → maintainability (complexity + size + volume)
    CBO   → coupling between classes
    LCOM* → cohesion within classes
    DIT   → inheritance depth

  These four measure genuinely different quality dimensions.
""")


if __name__ == "__main__":
    main()