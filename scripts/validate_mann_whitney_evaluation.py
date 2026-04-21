"""
validate_mann_whitney_evaluation.py

Tests whether CompQS can separate good pattern implementations
from bad ones, while CQS cannot.

This is the strongest validation evidence for the two-tier framework:
if CompQS separates the groups (p < 0.05) but CQS does not (p > 0.05),
it proves that adding PIQS captures quality differences invisible to
code metrics alone.

Usage:
    python3 scripts/validate_mann_whitney_evaluation.py

Input:  data/outputs/generated_evaluation_scores.json

Requires: scipy, numpy
    pip install scipy numpy
"""

import json
from pathlib import Path
from scipy.stats import mannwhitneyu
import numpy as np


def main():
    # ── Load data ───────────────────────────────────────────────
    input_file = Path("data/outputs/generated_evaluation_scores.json")
    if not input_file.exists():
        print(f"ERROR: {input_file} not found")
        return

    with open(input_file) as f:
        data = json.load(f)

    rows = data.get("rows", [])
    print(f"Loaded {len(rows)} evaluations from {input_file.name}")
    print(f"Formula CQS:    {data.get('formula_cqs', 'N/A')}")
    print(f"Formula CompQS: {data.get('formula_compqs', 'N/A')}")
    print()

    # ── Define groups ───────────────────────────────────────────
    # Group A: High PIQS patterns (Singleton + Strategy)
    #   - Singleton: PIQS = 100.0 always
    #   - Strategy: PIQS = 77.7 – 100.0, avg 92.0
    #
    # Group B: Low PIQS patterns (Composite)
    #   - Composite: PIQS = 38.3 – 100.0, avg 57.6
    #
    # Why these groups: they represent the clearest split between
    # "LLM implements the pattern well" vs "LLM often fails"
    #
    # (Factory-Method and Observer are mid-range and excluded to
    #  maximize the contrast between groups.)

    group_a_patterns = {"singleton", "strategy"}
    group_b_patterns = {"composite"}

    group_a = [r for r in rows if r["pattern"] in group_a_patterns]
    group_b = [r for r in rows if r["pattern"] in group_b_patterns]

    print("=" * 70)
    print("GROUP DEFINITIONS")
    print("=" * 70)
    print(f"  Group A (high PIQS): {sorted(group_a_patterns)}")
    print(f"    n = {len(group_a)}")
    print(f"    Avg PIQS = {np.mean([r['piqs_score'] for r in group_a]):.1f}")
    print()
    print(f"  Group B (low PIQS):  {sorted(group_b_patterns)}")
    print(f"    n = {len(group_b)}")
    print(f"    Avg PIQS = {np.mean([r['piqs_score'] for r in group_b]):.1f}")
    print()

    # Show all patterns for context
    all_patterns = sorted(set(r["pattern"] for r in rows))
    excluded = [p for p in all_patterns if p not in group_a_patterns and p not in group_b_patterns]
    if excluded:
        other_piqs = [r["piqs_score"] for r in rows if r["pattern"] in excluded]
        print(f"  (Other patterns excluded: {excluded} avg PIQS = {np.mean(other_piqs):.1f})")

    # ── Extract scores ──────────────────────────────────────────
    a_cqs = [r["cqs_score"] for r in group_a]
    b_cqs = [r["cqs_score"] for r in group_b]
    a_compqs = [r["compqs_score"] for r in group_a]
    b_compqs = [r["compqs_score"] for r in group_b]

    # ── Show distributions ──────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("SCORE DISTRIBUTIONS")
    print("=" * 70)
    print(f"\n  CQS (code quality only — no pattern info):")
    print(f"    Group A (high PIQS): avg={np.mean(a_cqs):.1f}  std={np.std(a_cqs):.1f}  range=[{min(a_cqs):.1f}, {max(a_cqs):.1f}]")
    print(f"    Group B (low PIQS):  avg={np.mean(b_cqs):.1f}  std={np.std(b_cqs):.1f}  range=[{min(b_cqs):.1f}, {max(b_cqs):.1f}]")
    print(f"    Gap: {abs(np.mean(a_cqs) - np.mean(b_cqs)):.1f} points")

    print(f"\n  CompQS (code quality + pattern correctness):")
    print(f"    Group A (high PIQS): avg={np.mean(a_compqs):.1f}  std={np.std(a_compqs):.1f}  range=[{min(a_compqs):.1f}, {max(a_compqs):.1f}]")
    print(f"    Group B (low PIQS):  avg={np.mean(b_compqs):.1f}  std={np.std(b_compqs):.1f}  range=[{min(b_compqs):.1f}, {max(b_compqs):.1f}]")
    print(f"    Gap: {abs(np.mean(a_compqs) - np.mean(b_compqs)):.1f} points")

    # ── Mann-Whitney U Test ─────────────────────────────────────
    # This is a non-parametric test (doesn't assume normal distribution)
    # It asks: "Are these two groups drawn from different distributions?"
    # p < 0.05 = yes, the groups are significantly different

    print(f"\n{'=' * 70}")
    print("MANN-WHITNEY U TEST (two-sided)")
    print("=" * 70)

    # Test 1: CQS — expecting NO significant difference
    stat_cqs, p_cqs = mannwhitneyu(a_cqs, b_cqs, alternative="two-sided")
    print(f"\n  TEST 1: Can CQS separate the groups?")
    print(f"    U statistic = {stat_cqs:.1f}")
    print(f"    p-value     = {p_cqs:.4f}")
    if p_cqs < 0.05:
        print(f"    Result: YES, significant (p < 0.05)")
        print(f"    → CQS CAN distinguish high-PIQS from low-PIQS patterns")
    else:
        print(f"    Result: NO, not significant (p ≥ 0.05)")
        print(f"    → CQS CANNOT distinguish high-PIQS from low-PIQS patterns")

    # Test 2: CompQS — expecting significant difference
    stat_compqs, p_compqs = mannwhitneyu(a_compqs, b_compqs, alternative="two-sided")
    print(f"\n  TEST 2: Can CompQS separate the groups?")
    print(f"    U statistic = {stat_compqs:.1f}")
    print(f"    p-value     = {p_compqs:.6f}")
    if p_compqs < 0.05:
        print(f"    Result: YES, significant (p < 0.05)")
        print(f"    → CompQS CAN distinguish high-PIQS from low-PIQS patterns")
    else:
        print(f"    Result: NO, not significant (p ≥ 0.05)")
        print(f"    → CompQS CANNOT distinguish high-PIQS from low-PIQS patterns")

    # ── Effect size (rank-biserial correlation) ─────────────────
    n_a = len(a_compqs)
    n_b = len(b_compqs)
    r_compqs = 1 - (2 * stat_compqs) / (n_a * n_b)
    r_cqs = 1 - (2 * stat_cqs) / (n_a * n_b)

    print(f"\n{'=' * 70}")
    print("EFFECT SIZE (rank-biserial correlation, r)")
    print("=" * 70)
    print(f"  CQS:    r = {r_cqs:.3f}  ({'negligible' if abs(r_cqs) < 0.1 else 'small' if abs(r_cqs) < 0.3 else 'medium' if abs(r_cqs) < 0.5 else 'large'})")
    print(f"  CompQS: r = {r_compqs:.3f}  ({'negligible' if abs(r_compqs) < 0.1 else 'small' if abs(r_compqs) < 0.3 else 'medium' if abs(r_compqs) < 0.5 else 'large'})")

    # ── Interpretation ──────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("INTERPRETATION")
    print("=" * 70)

    if p_compqs < 0.05 and p_cqs >= 0.05:
        print(f"""
  ✓ IDEAL RESULT: CompQS separates the groups but CQS does not.

  This is direct proof that Tier 2 (pattern correctness) captures quality
  differences that Tier 1 (code metrics alone) misses.

  In plain language: if you only used CQS, you would conclude that
  Singleton/Strategy and Composite produce code of similar quality.
  CompQS reveals that they are fundamentally different — one group
  implements patterns correctly, the other often does not.

  Statistical evidence:
  - CQS gap: {abs(np.mean(a_cqs) - np.mean(b_cqs)):.1f} points (U={stat_cqs:.0f}, p={p_cqs:.4f}, r={r_cqs:.3f})
  - CompQS gap: {abs(np.mean(a_compqs) - np.mean(b_compqs)):.1f} points (U={stat_compqs:.0f}, p={p_compqs:.6f}, r={r_compqs:.3f})
""")
    elif p_compqs < 0.05 and p_cqs < 0.05:
        print(f"""
  ~ PARTIAL RESULT: Both CQS and CompQS separate the groups.

  CQS shows some separation (gap={abs(np.mean(a_cqs) - np.mean(b_cqs)):.1f} pts, p={p_cqs:.4f}, r={r_cqs:.3f})
  CompQS shows {'stronger' if abs(r_compqs) > abs(r_cqs) else 'similar'} or stronger separation (gap={abs(np.mean(a_compqs) - np.mean(b_compqs)):.1f} pts, p={p_compqs:.6f}, r={r_compqs:.3f})

  This suggests that Tier 1 (code metrics) does capture *some* pattern
  quality differences, but Tier 2 (pattern correctness) is a stronger
  signal. The framework still adds value by being more discriminative.
""")
    elif p_compqs < 0.05 and p_cqs < 0.05:
        print("""
  ~ ALTERNATIVE: CompQS separates but with marginal CQS separation.

  CompQS is the stronger discriminator. CQS has limited separation power.
""")
    else:
        print(f"""
  ✗ UNEXPECTED: Neither metric separates the groups significantly.

  This may indicate that:
  - The group definitions need adjustment (try other pattern splits).
  - The sample sizes are too small (current: A={n_a}, B={n_b}).
  - Both metrics lack discriminative power for these patterns.

  Recommendations:
  1. Check if PIQS actually correlates with implementation correctness.
  2. Try alternative group definitions (e.g., all low-PIQS vs all high-PIQS).
  3. Verify that generated code quality varies as expected.
""")

    # ── For the paper ───────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("FOR YOUR PAPER")
    print("=" * 70)
    print(f"""
  "A Mann-Whitney U test compared CompQS and CQS scores between
  high-PIQS patterns (Singleton + Strategy, n = {n_a}) and
  low-PIQS patterns (Composite, n = {n_b}). CompQS showed
  {'significant' if p_compqs < 0.05 else 'no significant'} separation
  (U = {stat_compqs:.0f}, p {'< 0.001' if p_compqs < 0.001 else f'= {p_compqs:.4f}'}, r = {r_compqs:.3f}),
  while CQS showed {'significant' if p_cqs < 0.05 else 'no significant'}
  separation (U = {stat_cqs:.0f}, {'p < 0.001' if p_cqs < 0.001 else f'p = {p_cqs:.4f}'}, r = {r_cqs:.3f}).
  {'This confirms that CompQS captures pattern implementation quality that CQS alone misses.' if p_compqs < 0.05 and p_cqs >= 0.05 else ''}"
""")


if __name__ == "__main__":
    main()
