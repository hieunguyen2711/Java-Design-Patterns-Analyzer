"""Score three already-generated model corpora on the paper's 5 patterns.

Minimal update to the two-tier study: no new generation, no re-derived entropy
weights, no change to the instrument. The corpora come from
``data/outputs/generated_logprobs.zip``, which must be unzipped to a scratch
directory *outside* the repository first; the extracted files are never
committed.

Stages:

    inventory   Build and print the work list (3 models x 5 patterns x 12
                contexts = 180 units) and verify the context-slug bridge.

    score       Run MI + CK on every unit in the work list and write
                data/outputs/three_models_minimal_metrics.csv.

Usage:
    python3 scripts/three_models_minimal.py inventory --extract-root <dir>
    python3 scripts/three_models_minimal.py score     --extract-root <dir>

where <dir> is the extracted ``generated_logprobs/`` directory.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

CONTEXTS_FILE = ROOT_DIR / "data" / "input" / "common_java_projects.json"
METRICS_CSV = ROOT_DIR / "data" / "outputs" / "three_models_minimal_metrics.csv"

SEED_DIR = "seed_40"

# Directory name under generated_logprobs/ -> the model_slug used in the
# unit_id column of data/outputs/piqs_<model>.csv. Each of those CSVs contains
# exactly one distinct unit_id prefix; verify_unit_ids() checks this mapping
# against the CSVs rather than trusting it.
MODELS: dict[str, dict[str, str]] = {
    "qwen25_7b": {
        "slug": "qwen-qwen2-5-7b-instruct",
        "piqs_csv": "piqs_qwen25_7b.csv",
    },
    "llama31_8b": {
        "slug": "meta-llama-llama-3-1-8b-instruct",
        "piqs_csv": "piqs_llama31_8b.csv",
    },
    "qwen25_14b": {
        "slug": "qwen-qwen2-5-14b-instruct",
        "piqs_csv": "piqs_qwen25_14b.csv",
    },
}

# The five patterns the paper reports. Builder, Decorator and Template Method
# exist in the corpora but are not in the paper, and are ignored entirely.
# Left column: directory name in the zip and `pattern` in the PIQS CSVs.
# Right column: `pattern` in data/outputs/generated_evaluation_scores.json.
PAPER_PATTERNS: dict[str, str] = {
    "Singleton": "singleton",
    "Strategy": "strategy",
    "Factory Method": "factory-method",
    "Observer": "observer",
    "Composite": "composite",
}


# --------------------------------------------------------------------------- #
# Context bridge                                                              #
# --------------------------------------------------------------------------- #

def slugify(value: str) -> str:
    """Byte-identical to ``generation/run_generation.py:99``.

    Reimplemented rather than imported because run_generation.py does not
    import on `main` (line 55 `from _future_ import annotations`, line 905
    `if _name_ == "_main_":` — single underscores).
    """
    import re

    lowered = str(value).lower().strip()
    sanitized = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return sanitized or "x"


def load_context_bridge() -> dict[str, str]:
    """Map the zip's context-slug -> the paper's `project_context` sentence.

    The zip directory name is slugify(project_title); the paper's 70 scored
    rows key on project_context. data/input/common_java_projects.json carries
    both fields, so it bridges them.
    """
    entries = json.loads(CONTEXTS_FILE.read_text(encoding="utf-8"))
    bridge: dict[str, str] = {}
    for entry in entries:
        slug = slugify(entry["project_title"])
        if slug in bridge:
            raise SystemExit(f"ERROR: duplicate context slug {slug!r} in {CONTEXTS_FILE}")
        bridge[slug] = entry["project_context"]
    return bridge


# --------------------------------------------------------------------------- #
# Work list                                                                   #
# --------------------------------------------------------------------------- #

def build_work_list(extract_root: Path, bridge: dict[str, str]) -> list[dict]:
    """One entry per (model, paper pattern, context) unit directory.

    Layout: <extract_root>/<model_dir>/seed_40/<Pattern Name>/<context-slug>/rep0/
    """
    units: list[dict] = []

    for model_dir, meta in MODELS.items():
        seed_root = extract_root / model_dir / SEED_DIR
        if not seed_root.is_dir():
            raise SystemExit(f"ERROR: not a directory: {seed_root}")

        for pattern_dir in sorted(PAPER_PATTERNS):
            pattern_root = seed_root / pattern_dir
            if not pattern_root.is_dir():
                raise SystemExit(f"ERROR: missing pattern directory: {pattern_root}")

            for context_root in sorted(c for c in pattern_root.iterdir() if c.is_dir()):
                if context_root.name.startswith("."):
                    continue
                for rep_root in sorted(r for r in context_root.iterdir() if r.is_dir()):
                    if rep_root.name.startswith("."):
                        continue

                    java_files = sorted(rep_root.rglob("*.java"))
                    units.append(
                        {
                            "unit_id": (
                                f"{meta['slug']}__{pattern_dir}__"
                                f"{context_root.name}__{rep_root.name}"
                            ),
                            "model": model_dir,
                            "pattern": pattern_dir,
                            "paper_pattern": PAPER_PATTERNS[pattern_dir],
                            "context_slug": context_root.name,
                            "project_context": bridge.get(context_root.name),
                            "dir": rep_root,
                            "n_files": len(java_files),
                        }
                    )
    return units


def verify_context_slugs(units: list[dict], bridge: dict[str, str]) -> None:
    """Assert every context slug seen in the tree maps to a project_context."""
    seen = {u["context_slug"] for u in units}
    unmapped = sorted(s for s in seen if s not in bridge)
    if unmapped:
        raise SystemExit(
            f"ERROR: {len(unmapped)} context slug(s) do not map to a project_context "
            f"via {CONTEXTS_FILE}: {unmapped}"
        )
    print(f"context bridge OK: all {len(seen)} slugs map to a project_context "
          f"({len(bridge)} available)")


def verify_unit_ids(units: list[dict]) -> None:
    """Assert every generated unit_id appears in the matching PIQS CSV.

    This is what makes the Task 4 join exact rather than approximate.
    """
    ok = True
    for model_dir, meta in MODELS.items():
        csv_path = ROOT_DIR / "data" / "outputs" / meta["piqs_csv"]
        with csv_path.open(encoding="utf-8") as fh:
            piqs_ids = {row["unit_id"] for row in csv.DictReader(fh)}

        ours = {u["unit_id"] for u in units if u["model"] == model_dir}
        missing = sorted(ours - piqs_ids)
        if missing:
            ok = False
            print(f"  {model_dir}: {len(missing)} unit_id(s) NOT in {meta['piqs_csv']}")
            for m in missing[:5]:
                print(f"    {m}")
        else:
            print(f"  {model_dir}: all {len(ours)} unit_ids present in {meta['piqs_csv']} "
                  f"({len(piqs_ids)} rows total, 5-pattern subset used)")

    if not ok:
        raise SystemExit("ERROR: unit_id join keys do not match the PIQS CSVs")


# --------------------------------------------------------------------------- #
# Reporting                                                                   #
# --------------------------------------------------------------------------- #

def print_inventory(units: list[dict]) -> None:
    header = ("model", "patterns", "contexts", "units", "units with >=1 .java file")
    rows = []
    for model_dir in MODELS:
        mine = [u for u in units if u["model"] == model_dir]
        rows.append(
            (
                model_dir,
                len({u["pattern"] for u in mine}),
                len({u["context_slug"] for u in mine}),
                len(mine),
                sum(1 for u in mine if u["n_files"] > 0),
            )
        )

    widths = [max(len(str(r[i])) for r in [header, *rows]) for i in range(len(header))]

    def fmt(cells):
        return "| " + " | ".join(str(c).ljust(w) for c, w in zip(cells, widths)) + " |"

    print(fmt(header))
    print("|" + "|".join("-" * (w + 2) for w in widths) + "|")
    for r in rows:
        print(fmt(r))

    print(
        f"\nTOTAL units: {len(units)}   "
        f"with >=1 .java file: {sum(1 for u in units if u['n_files'] > 0)}   "
        f"total .java files: {sum(u['n_files'] for u in units)}"
    )


# --------------------------------------------------------------------------- #
# Stages                                                                      #
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Scoring                                                                     #
# --------------------------------------------------------------------------- #

CSV_COLUMNS = [
    "unit_id",
    "model",
    "pattern",
    "context_slug",
    "project_context",
    "n_files",
    "avg_mi_score",
    "avg_cbo",
    "avg_lcom_star",
    "avg_rfc",
    "avg_dit",
    "ck_overall_score",
    "ck_status",
]

# CK summary keys that analyze_project leaves as None when run_ck failed.
# `analysis_pipeline.py:243-250` fills them from ck_summary.get(...), which is
# an empty dict on the MI-only fallback path.
CK_KEYS = ("avg_cbo", "avg_lcom_star", "avg_rfc", "avg_dit", "ck_overall_score")


def score_unit(unit: dict) -> dict:
    """Run MI + CK on one unit directory and flatten it into a CSV row.

    Never raises and never drops a unit: a failure is recorded in ck_status
    with the metric columns left empty.
    """
    from app.services.analysis_pipeline import analyze_project

    row = {
        "unit_id": unit["unit_id"],
        "model": unit["model"],
        "pattern": unit["pattern"],
        "context_slug": unit["context_slug"],
        "project_context": unit["project_context"],
        "n_files": unit["n_files"],
        "avg_mi_score": "",
        "avg_cbo": "",
        "avg_lcom_star": "",
        "avg_rfc": "",
        "avg_dit": "",
        "ck_overall_score": "",
        "ck_status": "",
    }

    if unit["n_files"] == 0:
        row["ck_status"] = "no_java_files"
        return row

    try:
        result = analyze_project(str(unit["dir"]), pattern_name=unit["pattern"])
    except Exception as exc:  # noqa: BLE001 - record it, never drop the row
        row["ck_status"] = f"error: {type(exc).__name__}: {exc}"
        return row

    summary = result.get("summary", {})
    row["avg_mi_score"] = summary.get("avg_mi_score", "")

    missing = [k for k in CK_KEYS if summary.get(k) is None]
    if missing:
        # MI ran, CK did not. analyze_project swallows the cause, so record
        # which columns came back empty rather than implying a clean run.
        row["ck_status"] = "ck_unavailable: " + ",".join(missing)
        for k in CK_KEYS:
            if summary.get(k) is not None:
                row[k] = summary[k]
        return row

    for k in CK_KEYS:
        row[k] = summary[k]
    row["ck_status"] = "ok"
    return row


def stage_score(extract_root: Path) -> None:
    bridge = load_context_bridge()
    units = build_work_list(extract_root, bridge)
    verify_context_slugs(units, bridge)

    print(f"\nscoring {len(units)} units (MI + CK)...")
    t0 = time.time()
    rows: list[dict] = []

    for i, unit in enumerate(units, 1):
        row = score_unit(unit)
        rows.append(row)
        if i % 20 == 0 or i == len(units):
            print(f"  {i:3d}/{len(units)}  ({time.time() - t0:6.1f}s elapsed)")
        if not row["ck_status"].startswith("ok"):
            print(f"  !! {row['unit_id']}: {row['ck_status']}")

    METRICS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with METRICS_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nwrote {len(rows)} rows to {METRICS_CSV.relative_to(ROOT_DIR)} "
          f"in {time.time() - t0:.1f}s")


def stage_inventory(extract_root: Path) -> list[dict]:
    bridge = load_context_bridge()
    units = build_work_list(extract_root, bridge)

    verify_context_slugs(units, bridge)
    print()
    print("unit_id join check against the PIQS CSVs:")
    verify_unit_ids(units)
    print()
    print_inventory(units)

    return units


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=("inventory", "score"))
    parser.add_argument(
        "--extract-root",
        required=True,
        type=Path,
        help="Path to the extracted generated_logprobs/ directory (outside the repo)",
    )
    args = parser.parse_args()

    if not args.extract_root.is_dir():
        raise SystemExit(f"ERROR: not a directory: {args.extract_root}")

    if args.stage == "inventory":
        stage_inventory(args.extract_root)
    elif args.stage == "score":
        stage_score(args.extract_root)


if __name__ == "__main__":
    main()
