"""
generate_judge_pairs.py

Builds LLM-judge pairwise comparison sets from generated evaluation scores.

Input:
    data/outputs/generated_evaluation_scores.json

Output:
    data/reports/judge_pairs.json

Usage:
    python3 scripts/generate_judge_pairs.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from random import Random
from typing import Dict, Iterable, List, Sequence, Tuple

INPUT_FILE = Path("data/outputs/generated_evaluation_scores.json")
OUTPUT_FILE = Path("data/reports/judge_pairs.json")
RANDOM_SEED = 42

CATEGORY_SPECS = {
    "cqs_validation": 10,
    "compqs_validation": 10,
    "domain_sensitivity": 5,
}


@dataclass(frozen=True)
class Project:
    idx: int
    project_id: str
    pattern: str
    project_context: str
    batch_name: str
    piqs_score: float
    cqs_score: float
    compqs_score: float


@dataclass(frozen=True)
class CandidatePair:
    category: str
    metric_used: str
    gap: float
    winner_id: str
    loser_id: str
    p1: Project
    p2: Project


def load_projects(path: Path) -> List[Project]:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    rows = data.get("rows", [])
    projects: List[Project] = []

    for idx, row in enumerate(rows):
        project_id = f"{idx}:{row['batch_name']}::{row['pattern']}"
        projects.append(
            Project(
                idx=idx,
                project_id=project_id,
                pattern=row["pattern"],
                project_context=row["project_context"],
                batch_name=row["batch_name"],
                piqs_score=float(row["piqs_score"]),
                cqs_score=float(row["cqs_score"]),
                compqs_score=float(row["compqs_score"]),
            )
        )

    if not projects:
        raise ValueError("No rows found in input JSON.")

    return projects


def pair_key(a: Project, b: Project) -> Tuple[str, str]:
    return tuple(sorted((a.project_id, b.project_id)))


def candidate_pairs_cqs(projects: Sequence[Project]) -> List[CandidatePair]:
    out: List[CandidatePair] = []
    for a, b in combinations(projects, 2):
        if a.pattern == b.pattern:
            continue

        gap = abs(a.cqs_score - b.cqs_score)
        if gap < 10.0:
            continue

        if a.cqs_score == b.cqs_score:
            continue

        winner, loser = (a, b) if a.cqs_score > b.cqs_score else (b, a)
        out.append(
            CandidatePair(
                category="cqs_validation",
                metric_used="cqs_score",
                gap=gap,
                winner_id=winner.project_id,
                loser_id=loser.project_id,
                p1=a,
                p2=b,
            )
        )

    out.sort(key=lambda x: x.gap, reverse=True)
    return out


def candidate_pairs_compqs(projects: Sequence[Project]) -> List[CandidatePair]:
    out: List[CandidatePair] = []
    for a, b in combinations(projects, 2):
        if a.pattern == b.pattern:
            continue

        cqs_gap = abs(a.cqs_score - b.cqs_score)
        compqs_gap = abs(a.compqs_score - b.compqs_score)

        if cqs_gap >= 10.0:
            continue
        if compqs_gap < 15.0:
            continue
        if a.compqs_score == b.compqs_score:
            continue

        winner, loser = (a, b) if a.compqs_score > b.compqs_score else (b, a)
        out.append(
            CandidatePair(
                category="compqs_validation",
                metric_used="compqs_score",
                gap=compqs_gap,
                winner_id=winner.project_id,
                loser_id=loser.project_id,
                p1=a,
                p2=b,
            )
        )

    out.sort(key=lambda x: x.gap, reverse=True)
    return out


def candidate_pairs_domain(projects: Sequence[Project]) -> List[CandidatePair]:
    target_patterns = {"composite", "observer"}
    out: List[CandidatePair] = []

    for a, b in combinations(projects, 2):
        if a.pattern != b.pattern:
            continue
        if a.pattern not in target_patterns:
            continue

        compqs_gap = abs(a.compqs_score - b.compqs_score)
        if compqs_gap < 15.0:
            continue
        if a.compqs_score == b.compqs_score:
            continue

        winner, loser = (a, b) if a.compqs_score > b.compqs_score else (b, a)
        out.append(
            CandidatePair(
                category="domain_sensitivity",
                metric_used="compqs_score",
                gap=compqs_gap,
                winner_id=winner.project_id,
                loser_id=loser.project_id,
                p1=a,
                p2=b,
            )
        )

    out.sort(key=lambda x: x.gap, reverse=True)
    return out


def pick_top_unique(
    candidates: Iterable[CandidatePair],
    n_needed: int,
    used_pairs: set[Tuple[str, str]],
) -> List[CandidatePair]:
    selected: List[CandidatePair] = []

    for c in candidates:
        pk = pair_key(c.p1, c.p2)
        if pk in used_pairs:
            continue

        used_pairs.add(pk)
        selected.append(c)

        if len(selected) == n_needed:
            break

    if len(selected) < n_needed:
        raise ValueError(
            f"Not enough eligible unique pairs. Needed={n_needed}, found={len(selected)}"
        )

    return selected


def project_payload(p: Project) -> Dict[str, object]:
    return {
        "pattern": p.pattern,
        "project_context": p.project_context,
        "batch_name": p.batch_name,
        "piqs_score": round(p.piqs_score, 2),
        "cqs_score": round(p.cqs_score, 2),
        "compqs_score": round(p.compqs_score, 2),
    }


def build_output_pairs(
    picked_by_category: Dict[str, List[CandidatePair]],
    seed: int,
) -> List[Dict[str, object]]:
    rng = Random(seed)
    pairs_out: List[Dict[str, object]] = []
    pair_id = 1

    category_order = ["cqs_validation", "compqs_validation", "domain_sensitivity"]

    for category in category_order:
        # Already sorted by descending gap during candidate generation and greedy picking.
        for cand in picked_by_category[category]:
            show_a_first = rng.random() < 0.5
            a_proj, b_proj = (cand.p1, cand.p2) if show_a_first else (cand.p2, cand.p1)

            if cand.winner_id == a_proj.project_id:
                expected_winner = "A"
                winner_score = a_proj.cqs_score if cand.metric_used == "cqs_score" else a_proj.compqs_score
                loser_score = b_proj.cqs_score if cand.metric_used == "cqs_score" else b_proj.compqs_score
            else:
                expected_winner = "B"
                winner_score = b_proj.cqs_score if cand.metric_used == "cqs_score" else b_proj.compqs_score
                loser_score = a_proj.cqs_score if cand.metric_used == "cqs_score" else a_proj.compqs_score

            pairs_out.append(
                {
                    "pair_id": pair_id,
                    "category": category,
                    "project_a": project_payload(a_proj),
                    "project_b": project_payload(b_proj),
                    "expected_winner": expected_winner,
                    "metric_used": cand.metric_used,
                    "metric_gap": round(cand.gap, 2),
                    "winner_score": round(winner_score, 2),
                    "loser_score": round(loser_score, 2),
                    "presentation_order": "randomized_seed_42",
                }
            )
            pair_id += 1

    return pairs_out


def main() -> None:
    projects = load_projects(INPUT_FILE)

    candidates = {
        "cqs_validation": candidate_pairs_cqs(projects),
        "compqs_validation": candidate_pairs_compqs(projects),
        "domain_sensitivity": candidate_pairs_domain(projects),
    }

    used_pairs: set[Tuple[str, str]] = set()
    picked_by_category = {
        category: pick_top_unique(candidates[category], n_needed, used_pairs)
        for category, n_needed in CATEGORY_SPECS.items()
    }

    pairs = build_output_pairs(picked_by_category, RANDOM_SEED)

    output = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_pairs": len(pairs),
            "categories": CATEGORY_SPECS,
            "random_seed": RANDOM_SEED,
            "input_file": str(INPUT_FILE),
        },
        "pairs": pairs,
    }

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print("Generated judge pair set")
    print(f"  Input:  {INPUT_FILE}")
    print(f"  Output: {OUTPUT_FILE}")
    for cat in ("cqs_validation", "compqs_validation", "domain_sensitivity"):
        print(f"  {cat}: {len(picked_by_category[cat])} pairs")


if __name__ == "__main__":
    main()
