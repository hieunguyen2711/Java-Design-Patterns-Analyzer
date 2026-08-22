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
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

CONTEXTS_FILE = ROOT_DIR / "data" / "input" / "common_java_projects.json"

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
    import csv

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
    parser.add_argument("stage", choices=("inventory",))
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


if __name__ == "__main__":
    main()
