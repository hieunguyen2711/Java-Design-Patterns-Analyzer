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

    reconstruct Verify the reconstructed CQS/CompQS formulas against the 60
                already-scored Qwen3-Coder rows. Gate for the `table` stage.

    table       Join everything into 3 models x 3 seeds x 5 patterns x 12
                contexts plus 60 stored Qwen3 rows = 600 rows, then print the
                per-model and summary tables.

Usage:
    python3 scripts/three_models_minimal.py inventory   --extract-root <dir>
    python3 scripts/three_models_minimal.py score       --extract-root <dir>
    python3 scripts/three_models_minimal.py reconstruct
    python3 scripts/three_models_minimal.py table

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
TABLE_CSV = ROOT_DIR / "data" / "outputs" / "four_models_pattern_summary.csv"

SEEDS = (40, 41, 42)

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

    Layout: <extract_root>/<model_dir>/seed_<seed>/<Pattern Name>/<context-slug>/rep0/
    """
    units: list[dict] = []

    for model_dir, meta in MODELS.items():
        for seed in SEEDS:
            seed_root = extract_root / model_dir / f"seed_{seed}"
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
                                "seed": seed,
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
            piqs_ids = {(row["unit_id"], int(row["seed"])) for row in csv.DictReader(fh)}

        ours = {(u["unit_id"], u["seed"]) for u in units if u["model"] == model_dir}
        missing = sorted(ours - piqs_ids)
        if missing:
            ok = False
            print(f"  {model_dir}: {len(missing)} unit_id(s) NOT in {meta['piqs_csv']}")
            for m in missing[:5]:
                print(f"    {m}")
        else:
            print(f"  {model_dir}: all {len(ours)} (unit_id, seed) keys present in {meta['piqs_csv']} "
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
    "seed",
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
        "seed": unit["seed"],
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


# --------------------------------------------------------------------------- #
# Formula reconstruction                                                      #
# --------------------------------------------------------------------------- #

PAPER_SCORES_FILE = ROOT_DIR / "data" / "outputs" / "generated_evaluation_scores.json"


def compute_compqs(piqs: float, mi: float, ck_q: float) -> float:
    """CompQS = d_PIQS^0.5 * d_MI^0.25 * CK_q^0.25 * 100.

    The string is recorded as `formula_compqs` in generated_evaluation_scores.json.
    The script that produced that file is not in the repository, so the clamping
    convention is taken from `_compute_cqs` (analysis_pipeline.py:32), the one
    committed implementation of the CQS half.
    """
    d_piqs = max(0.0, min(1.0, piqs / 100.0))
    d_mi = max(0.0, min(1.0, mi / 100.0))
    d_ck_q = max(0.0, min(1.0, ck_q / 100.0))
    return round((d_piqs ** 0.5) * (d_mi ** 0.25) * (d_ck_q ** 0.25) * 100.0, 2)


def load_paper_rows() -> tuple[list[dict], dict]:
    """Return (all 70 rows, the file's metadata) from the paper's score file."""
    data = json.loads(PAPER_SCORES_FILE.read_text(encoding="utf-8"))
    return data["rows"], data


def filter_paper_rows_to_shared_contexts(rows: list[dict], bridge: dict[str, str]) -> list[dict]:
    """Keep only rows whose project_context is one of the 12 shared contexts."""
    shared = set(bridge.values())
    return [r for r in rows if r["project_context"] in shared]


# Half-unit in the last place of a value written to 2 decimals. The paper's
# score file stores avg_mi_score / ck_q_score / piqs_score rounded to 2dp, but
# computed cqs_score / compqs_score from the *unrounded* values. Recomputing
# from the rounded columns therefore carries an unavoidable error; a row counts
# as reproduced if the stored score falls inside the interval the rounded
# inputs could have come from. Both formulas are monotonically increasing in
# every input, so the interval endpoints are just the perturbed endpoints.
ROUND_HALF_ULP = 0.005


def check_formula(name, rows, inputs, recompute, stored_key) -> dict:
    """Compare a recomputed score against the stored one on every row."""
    exact, within, outside = [], [], []

    for r in rows:
        args = inputs(r)
        got = recompute(*args)
        stored = r[stored_key]
        lo = recompute(*(a - ROUND_HALF_ULP for a in args))
        hi = recompute(*(a + ROUND_HALF_ULP for a in args))

        if got == stored:
            exact.append(r)
        elif lo <= stored <= hi:
            within.append((r, stored, got, lo, hi))
        else:
            outside.append((r, stored, got, lo, hi))

    print(f"\n{name} reconstruction vs stored {stored_key}")
    print(f"  rows checked                     : {len(rows)}")
    print(f"  exact to the stored 2dp          : {len(exact)}")
    print(f"  within the inputs' own rounding  : {len(within)}")
    print(f"  OUTSIDE (real disagreement)      : {len(outside)}")
    for r, stored, got, lo, hi in within[:10]:
        print(f"    ~ {r['pattern']:15s} stored={stored} got={got} "
              f"reachable=[{lo}, {hi}]")
    for r, stored, got, lo, hi in outside[:10]:
        print(f"    X {r['pattern']:15s} stored={stored} got={got} "
              f"reachable=[{lo}, {hi}]  {r['batch_name']}")

    return {"exact": exact, "within": within, "outside": outside}


def stage_reconstruct() -> None:
    """Verify the reconstructed formulas against the paper's own stored scores.

    If CQS cannot be reproduced from the stored avg_mi_score and ck_q_score,
    the reconstruction is wrong and the new models must not be scored with it.
    """
    from app.services.analysis_pipeline import _compute_cqs

    bridge = load_context_bridge()
    all_rows, meta = load_paper_rows()

    print(f"{PAPER_SCORES_FILE.relative_to(ROOT_DIR)}")
    print(f"  generated_at_utc : {meta.get('generated_at_utc')}")
    print(f"  formula_cqs      : {meta.get('formula_cqs')}")
    print(f"  formula_compqs   : {meta.get('formula_compqs')}")
    print(f"  rows             : {len(all_rows)}")
    print(f"  models           : {sorted({r['model_used'] for r in all_rows})}")
    print()

    rows = filter_paper_rows_to_shared_contexts(all_rows, bridge)
    dropped = sorted({r["project_context"] for r in all_rows} - {r["project_context"] for r in rows})
    print(f"filtered to the {len(bridge)} shared contexts: {len(rows)} rows "
          f"(dropped {len(all_rows) - len(rows)})")
    for d in dropped:
        print(f"  dropped context: {d!r}")

    if len(rows) != 60:
        raise SystemExit(f"ERROR: expected 60 rows after filtering, got {len(rows)}")

    cqs_res = check_formula(
        "CQS",
        rows,
        inputs=lambda r: (r["avg_mi_score"], r["ck_q_score"]),
        recompute=_compute_cqs,
        stored_key="cqs_score",
    )
    # CompQS is not required by the task, but Task 4 reports it for the new
    # models, so it goes through the same gate.
    comp_res = check_formula(
        "CompQS",
        rows,
        inputs=lambda r: (r["piqs_score"], r["avg_mi_score"], r["ck_q_score"]),
        recompute=compute_compqs,
        stored_key="compqs_score",
    )

    print()
    if cqs_res["outside"]:
        raise SystemExit(
            f"STOP: CQS reconstruction failed on {len(cqs_res['outside'])}/{len(rows)} rows "
            "by more than the stored inputs' own rounding. Do not score the new models."
        )
    print(f"PASS: all {len(rows)} rows reproduce CQS and CompQS within rounding.")
    if comp_res["outside"]:
        print(f"WARNING: CompQS did not reproduce on {len(comp_res['outside'])} rows.")


# --------------------------------------------------------------------------- #
# Task 4 — the joined table                                                   #
# --------------------------------------------------------------------------- #

PAPER_MODEL = "qwen3-coder-30b-a3b-instruct"

# Order the models appear in the report: the three new ones, then the paper's.
REPORT_MODELS = ["qwen25_7b", "llama31_8b", "qwen25_14b", PAPER_MODEL]

# Pattern display order, using the paper's label form.
PATTERN_ORDER = ["singleton", "factory-method", "strategy", "observer", "composite"]


def load_piqs(model_dir: str) -> dict[str, dict]:
    """unit_id -> PIQS row, for one model."""
    path = ROOT_DIR / "data" / "outputs" / MODELS[model_dir]["piqs_csv"]
    with path.open(encoding="utf-8") as fh:
        return {(row["unit_id"], int(row["seed"])): row for row in csv.DictReader(fh)}


def build_joined_rows() -> list[dict]:
    """One row per (model, pattern, context) across all four models.

    The three new models join `three_models_minimal_metrics.csv` to the PIQS
    CSVs on unit_id. The fourth model's rows are already scored and are taken
    from generated_evaluation_scores.json as-is, filtered to the 12 shared
    contexts.
    """
    from app.services.analysis_pipeline import _compute_cqs

    bridge = load_context_bridge()
    joined: list[dict] = []

    # ---- the three new models ------------------------------------------
    with METRICS_CSV.open(encoding="utf-8") as fh:
        metric_rows = list(csv.DictReader(fh))

    piqs_by_model = {m: load_piqs(m) for m in MODELS}

    for r in metric_rows:
        if r["ck_status"] != "ok":
            raise SystemExit(
                f"ERROR: {r['unit_id']} has ck_status={r['ck_status']!r}; "
                "scoring it would produce a misleading average"
            )

        piqs_row = piqs_by_model[r["model"]].get((r["unit_id"], int(r["seed"])))
        if piqs_row is None:
            raise SystemExit(f"ERROR: no PIQS row for unit_id {r['unit_id']!r}")

        mi = float(r["avg_mi_score"])
        ck_q = float(r["ck_overall_score"])
        piqs = float(piqs_row["piqs"])

        joined.append(
            {
                "model": r["model"],
                "seed": r["seed"],
                "pattern": PAPER_PATTERNS[r["pattern"]],
                "project_context": r["project_context"],
                "mi": mi,
                "ck_q": ck_q,
                "piqs": piqs,
                "cqs": _compute_cqs(mi, ck_q),
                "compqs": compute_compqs(piqs, mi, ck_q),
                "source": "recomputed",
            }
        )

    # ---- the paper's model ---------------------------------------------
    # Its scores are used as stored rather than recomputed: they were computed
    # from unrounded inputs, whereas the file's own mi/ck_q columns are rounded
    # to 2dp (see the Task 3 reconstruction check).
    paper_rows, _ = load_paper_rows()
    for r in filter_paper_rows_to_shared_contexts(paper_rows, bridge):
        joined.append(
            {
                "model": r["model_used"],
                "seed": 40,
                "pattern": r["pattern"],
                "project_context": r["project_context"],
                "mi": r["avg_mi_score"],
                "ck_q": r["ck_q_score"],
                "piqs": r["piqs_score"],
                "cqs": r["cqs_score"],
                "compqs": r["compqs_score"],
                "source": "stored",
            }
        )

    return joined


def _mean(values) -> float:
    return sum(values) / len(values)


def _ranks(by_pattern: dict[str, float]) -> dict[str, int]:
    """Rank 1 = highest score. Ties take the same (lower) rank number."""
    ordered = sorted(by_pattern.items(), key=lambda kv: -kv[1])
    ranks, prev_val, prev_rank = {}, None, 0
    for i, (pattern, val) in enumerate(ordered, 1):
        rank = prev_rank if val == prev_val else i
        ranks[pattern] = rank
        prev_val, prev_rank = val, rank
    return ranks


def per_model_table(rows: list[dict]) -> list[dict]:
    """avg CQS / PIQS / CompQS, delta and both ranks, per pattern."""
    by_pattern = {}
    for p in PATTERN_ORDER:
        sub = [r for r in rows if r["pattern"] == p]
        if not sub:
            continue
        by_pattern[p] = {
            "n": len(sub),
            "cqs": _mean([r["cqs"] for r in sub]),
            "piqs": _mean([r["piqs"] for r in sub]),
            "compqs": _mean([r["compqs"] for r in sub]),
        }

    cqs_rank = _ranks({p: v["cqs"] for p, v in by_pattern.items()})
    comp_rank = _ranks({p: v["compqs"] for p, v in by_pattern.items()})

    out = []
    for p in PATTERN_ORDER:
        if p not in by_pattern:
            continue
        v = by_pattern[p]
        out.append(
            {
                "pattern": p,
                "n": v["n"],
                "avg_cqs": v["cqs"],
                "avg_piqs": v["piqs"],
                "avg_compqs": v["compqs"],
                # delta = how far CompQS moves the pattern away from CQS
                "delta": v["compqs"] - v["cqs"],
                "cqs_rank": cqs_rank[p],
                "compqs_rank": comp_rank[p],
            }
        )
    return out


def _print_table(headers, rows) -> None:
    cells = [headers] + [[str(c) for c in r] for r in rows]
    widths = [max(len(c[i]) for c in cells) for i in range(len(headers))]
    print("| " + " | ".join(h.ljust(w) for h, w in zip(headers, widths)) + " |")
    print("|" + "|".join("-" * (w + 2) for w in widths) + "|")
    for r in cells[1:]:
        print("| " + " | ".join(c.ljust(w) for c, w in zip(r, widths)) + " |")


def stage_table() -> None:
    joined = build_joined_rows()

    print(f"joined rows: {len(joined)}")
    for m in REPORT_MODELS:
        sub = [r for r in joined if r["model"] == m]
        print(f"  {m:30s} {len(sub):3d} rows, "
              f"{len({r['pattern'] for r in sub})} patterns, "
              f"{len({r['project_context'] for r in sub})} contexts")

    if len(joined) != 600:
        raise SystemExit(f"ERROR: expected 600 rows (3 models x 3 seeds x 5 patterns x 12 "
                         "contexts + 60 stored Qwen3 rows), "
                         f"got {len(joined)}")
    print("\nassert 600 rows: OK")

    summary_rows = []
    for m in REPORT_MODELS:
        rows = [r for r in joined if r["model"] == m]
        table = per_model_table(rows)

        print(f"\n{'=' * 78}")
        print(f"{m}   (n={len(rows)}, {len(table)} patterns x 12 contexts)")
        print("=" * 78)
        _print_table(
            ["pattern", "avg CQS", "avg PIQS", "avg CompQS", "delta", "CQS rank", "CompQS rank"],
            [
                [
                    t["pattern"],
                    f"{t['avg_cqs']:.2f}",
                    f"{t['avg_piqs']:.2f}",
                    f"{t['avg_compqs']:.2f}",
                    f"{t['delta']:+.2f}",
                    t["cqs_rank"],
                    t["compqs_rank"],
                ]
                for t in table
            ],
        )

        cqs_vals = [t["avg_cqs"] for t in table]
        piqs_vals = [t["avg_piqs"] for t in table]
        cqs_range = max(cqs_vals) - min(cqs_vals)
        piqs_range = max(piqs_vals) - min(piqs_vals)

        single = next(t for t in table if t["pattern"] == "singleton")
        comp = next(t for t in table if t["pattern"] == "composite")

        print(f"\n  CQS  across 5 patterns: {min(cqs_vals):.2f} - {max(cqs_vals):.2f}  "
              f"(range {cqs_range:.2f})")
        print(f"  PIQS across 5 patterns: {min(piqs_vals):.2f} - {max(piqs_vals):.2f}  "
              f"(range {piqs_range:.2f})")
        print(f"  mean CQS {_mean([r['cqs'] for r in rows]):.2f}   "
              f"mean PIQS {_mean([r['piqs'] for r in rows]):.2f}   "
              f"mean CompQS {_mean([r['compqs'] for r in rows]):.2f}")

        summary_rows.append(
            {
                "model": m,
                "cqs_range": f"{min(cqs_vals):.2f}-{max(cqs_vals):.2f} ({cqs_range:.2f})",
                "piqs_range": f"{min(piqs_vals):.2f}-{max(piqs_vals):.2f} ({piqs_range:.2f})",
                # "rises" = CompQS gives it a better (numerically lower) rank
                "singleton": _movement(single, "rises"),
                "composite": _movement(comp, "falls"),
                "_mean_cqs": _mean([r["cqs"] for r in rows]),
                "_mean_piqs": _mean([r["piqs"] for r in rows]),
            }
        )

    table_rows = []
    for m in REPORT_MODELS:
        rows = [r for r in joined if r["model"] == m]
        mean_cqs = _mean([r["cqs"] for r in rows])
        mean_piqs = _mean([r["piqs"] for r in rows])
        mean_compqs = _mean([r["compqs"] for r in rows])
        table_rows.extend(
            {
                "model": m,
                "mean_cqs": mean_cqs,
                "mean_piqs": mean_piqs,
                "mean_compqs": mean_compqs,
                **row,
            }
            for row in per_model_table(rows)
        )

    TABLE_CSV.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "model", "mean_cqs", "mean_piqs", "mean_compqs", "pattern", "n",
                "avg_cqs", "avg_piqs", "avg_compqs", "delta", "cqs_rank",
                "compqs_rank",
            ],
        )
        writer.writeheader()
        writer.writerows(
            {
                **row,
                "mean_cqs": f"{row['mean_cqs']:.2f}",
                "mean_piqs": f"{row['mean_piqs']:.2f}",
                "mean_compqs": f"{row['mean_compqs']:.2f}",
                "avg_cqs": f"{row['avg_cqs']:.2f}",
                "avg_piqs": f"{row['avg_piqs']:.2f}",
                "avg_compqs": f"{row['avg_compqs']:.2f}",
                "delta": f"{row['delta']:+.2f}",
            }
            for row in table_rows
        )
    print(f"\nwrote unified pattern summary to {TABLE_CSV.relative_to(ROOT_DIR)} "
          f"({len(table_rows)} rows)")

    print(f"\n{'=' * 78}")
    print("SUMMARY — the table for the paper")
    print("=" * 78)
    _print_table(
        ["model", "CQS range across 5 patterns", "PIQS range across 5 patterns",
         "Singleton rises?", "Composite falls?"],
        [[s["model"], s["cqs_range"], s["piqs_range"], s["singleton"], s["composite"]]
         for s in summary_rows],
    )

    mean_cqs = [s["_mean_cqs"] for s in summary_rows]
    mean_piqs = [s["_mean_piqs"] for s in summary_rows]
    print(f"\nacross the four models:")
    print(f"  mean CQS  spans {min(mean_cqs):.2f} - {max(mean_cqs):.2f}  "
          f"(spread {max(mean_cqs) - min(mean_cqs):.2f})")
    print(f"  mean PIQS spans {min(mean_piqs):.2f} - {max(mean_piqs):.2f}  "
          f"(spread {max(mean_piqs) - min(mean_piqs):.2f})")


def _movement(t: dict, expect: str) -> str:
    """Answer 'does this pattern rise/fall in rank when CQS becomes CompQS?'

    Rank 1 is best, so a *rise* is a decrease in the rank number.
    """
    a, b = t["cqs_rank"], t["compqs_rank"]
    if a == b:
        return f"no, unchanged ({a})"
    moved = "rises" if b < a else "falls"
    answer = "yes" if moved == expect else "no"
    return f"{answer}, {moved} ({a} -> {b})"


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
    parser.add_argument("stage", choices=("inventory", "score", "reconstruct", "table"))
    parser.add_argument(
        "--extract-root",
        type=Path,
        help="Path to the extracted generated_logprobs/ directory (outside the repo). "
             "Required for the inventory and score stages.",
    )
    args = parser.parse_args()

    if args.stage == "reconstruct":
        stage_reconstruct()
        return
    if args.stage == "table":
        stage_table()
        return

    if args.extract_root is None:
        parser.error(f"--extract-root is required for the {args.stage} stage")
    if not args.extract_root.is_dir():
        raise SystemExit(f"ERROR: not a directory: {args.extract_root}")

    if args.stage == "inventory":
        stage_inventory(args.extract_root)
    elif args.stage == "score":
        stage_score(args.extract_root)


if __name__ == "__main__":
    main()
