"""
validate_sensitivity_evaluation.py

Monte Carlo sensitivity analysis for CompQS weights.

Perturbs CompQS top-level weights (PIQS/MI/CK) by ±25% across 1,000 trials
and checks whether the pattern ranking remains stable.

Usage:
    python3 scripts/validate_sensitivity_evaluation.py

Input:
    data/outputs/generated_evaluation_scores.json

Output:
    data/reports/sensitivity_validation_results.json

Requires:
    numpy
    pip install numpy
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np


def compute_compqs(
    piqs: float,
    mi: float,
    ck_q: float,
    w_piqs: float,
    w_mi: float,
    w_ck: float,
) -> float:
    """Compute CompQS with the provided top-level weights."""
    d_piqs = max(0.001, piqs / 100.0)
    d_mi = max(0.001, mi / 100.0)
    d_ck = max(0.001, ck_q / 100.0)
    return (d_piqs ** w_piqs) * (d_mi ** w_mi) * (d_ck ** w_ck) * 100.0


def get_pattern_ranking(
    rows: List[dict],
    w_piqs: float,
    w_mi: float,
    w_ck: float,
) -> Tuple[List[str], Dict[str, float]]:
    """Recompute CompQS for each row, then average and rank by pattern."""
    pattern_scores: Dict[str, List[float]] = defaultdict(list)

    for row in rows:
        pattern = row["pattern"]
        score = compute_compqs(
            piqs=row["piqs_score"],
            mi=row["avg_mi_score"],
            ck_q=row["ck_q_score"],
            w_piqs=w_piqs,
            w_mi=w_mi,
            w_ck=w_ck,
        )
        pattern_scores[pattern].append(score)

    pattern_averages = {pattern: float(np.mean(scores)) for pattern, scores in pattern_scores.items()}
    ranking = sorted(pattern_averages.keys(), key=lambda p: -pattern_averages[p])
    return ranking, pattern_averages


def compute_rank_distribution(rank_counts: Dict[str, List[int]], n_trials: int) -> Dict[str, Dict[str, float]]:
    """Convert rank counts to percentages for each pattern and rank position."""
    distribution: Dict[str, Dict[str, float]] = {}
    for pattern, counts in rank_counts.items():
        distribution[pattern] = {
            f"rank_{idx + 1}": round((count / n_trials) * 100.0, 2)
            for idx, count in enumerate(counts)
        }
    return distribution


def verdict_for_stability(full_stability_pct: float) -> Tuple[str, str]:
    """Map full-ranking stability percentage to a robustness verdict."""
    if full_stability_pct >= 95.0:
        return (
            "VERY ROBUST",
            "Rankings are highly stable under ±25% weight perturbation.",
        )
    if full_stability_pct >= 80.0:
        return (
            "MOSTLY ROBUST",
            "Rankings are generally stable with occasional swaps.",
        )
    return (
        "FRAGILE",
        "Rankings are sensitive to weight choices and may not be reliable.",
    )


def main() -> None:
    input_file = Path("data/outputs/generated_evaluation_scores.json")
    output_file = Path("data/reports/sensitivity_validation_results.json")

    if not input_file.exists():
        print(f"ERROR: Input file not found: {input_file}")
        return

    with input_file.open("r", encoding="utf-8") as f:
        data = json.load(f)

    rows = data.get("rows", [])
    if not rows:
        print("ERROR: No rows found in input file.")
        return

    # Base configuration
    base_weights = np.array([0.50, 0.25, 0.25], dtype=float)  # [PIQS, MI, CK_q]
    n_trials = 1000
    perturbation = 0.25
    random_seed = 42

    # Base ranking with original weights
    base_ranking, base_pattern_avgs = get_pattern_ranking(rows, *base_weights)

    # Monte Carlo simulation setup
    rng = np.random.default_rng(random_seed)
    rank_counts: Dict[str, List[int]] = {p: [0] * len(base_ranking) for p in base_ranking}

    full_ranking_stable = 0
    top3_stable = 0
    swapped_trials: Dict[str, int] = defaultdict(int)

    for _ in range(n_trials):
        noise = 1.0 + rng.uniform(-perturbation, perturbation, 3)
        perturbed = base_weights * noise

        # Keep reasonable minimum contribution then renormalize
        perturbed = np.clip(perturbed, 0.05, 0.90)
        perturbed = perturbed / perturbed.sum()

        trial_ranking, _ = get_pattern_ranking(rows, *perturbed)

        if trial_ranking == base_ranking:
            full_ranking_stable += 1
        if trial_ranking[:3] == base_ranking[:3]:
            top3_stable += 1

        for rank_idx, pattern in enumerate(trial_ranking):
            rank_counts[pattern][rank_idx] += 1

        # Track adjacent swaps compared to base ranking
        if trial_ranking != base_ranking:
            for i in range(len(base_ranking) - 1):
                a = base_ranking[i]
                b = base_ranking[i + 1]
                if trial_ranking.index(a) > trial_ranking.index(b):
                    swapped_trials[f"{a}<->{b}"] += 1

    full_stability_pct = (full_ranking_stable / n_trials) * 100.0
    top3_stability_pct = (top3_stable / n_trials) * 100.0
    verdict, verdict_explanation = verdict_for_stability(full_stability_pct)

    rank_distribution = compute_rank_distribution(rank_counts, n_trials)

    # Most common rank for each pattern
    most_common_rank = {
        pattern: int(np.argmax(counts) + 1) for pattern, counts in rank_counts.items()
    }

    output = {
        "metadata": {
            "analysis": "Monte Carlo sensitivity analysis for CompQS weights",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "input_file": str(input_file),
            "source_file": data.get("source_file"),
            "formula_compqs": "CompQS = d_PIQS^w_piqs * d_MI^w_mi * CK_q^w_ck * 100",
            "trials": n_trials,
            "perturbation_range": "±25%",
            "random_seed": random_seed,
            "total_evaluations": len(rows),
            "patterns": sorted({r["pattern"] for r in rows}),
        },
        "base_case": {
            "weights": {
                "piqs": float(base_weights[0]),
                "mi": float(base_weights[1]),
                "ck_q": float(base_weights[2]),
            },
            "ranking": base_ranking,
            "pattern_average_compqs": {p: round(base_pattern_avgs[p], 2) for p in base_ranking},
        },
        "stability": {
            "full_ranking_stable_trials": full_ranking_stable,
            "full_ranking_stability_pct": round(full_stability_pct, 2),
            "top3_stable_trials": top3_stable,
            "top3_stability_pct": round(top3_stability_pct, 2),
            "verdict": verdict,
            "verdict_explanation": verdict_explanation,
        },
        "rank_distribution_pct": rank_distribution,
        "most_common_rank": most_common_rank,
        "instability_analysis": {
            "unstable_trials": n_trials - full_ranking_stable,
            "unstable_pct": round(100.0 - full_stability_pct, 2),
            "adjacent_swaps": dict(sorted(swapped_trials.items(), key=lambda kv: -kv[1])),
        },
        "paper_ready_summary": (
            f"Monte Carlo sensitivity analysis with {n_trials} trials of ±{int(perturbation * 100)}% "
            f"CompQS weight perturbation shows the full 5-pattern ranking remains stable in "
            f"{full_stability_pct:.1f}% of simulations (top-3 stable: {top3_stability_pct:.1f}%), "
            f"indicating {verdict.lower()} ranking robustness."
        ),
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print("=" * 70)
    print("SENSITIVITY ANALYSIS RESULTS")
    print("=" * 70)
    print(f"Input file: {input_file}")
    print(f"Output file: {output_file}")
    print(f"Base ranking: {' > '.join(base_ranking)}")
    print(f"Full ranking stability: {full_ranking_stable}/{n_trials} ({full_stability_pct:.1f}%)")
    print(f"Top-3 stability: {top3_stable}/{n_trials} ({top3_stability_pct:.1f}%)")
    print(f"Verdict: {verdict}")


if __name__ == "__main__":
    main()
