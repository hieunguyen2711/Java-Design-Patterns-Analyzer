"""
Orchestrator that combines CK metrics + Maintainability Index into a
unified analysis result.

Architecture:
    Request → analysis_pipeline
                ├── ck_metrics.run_ck()        (subprocess → JAR → CSV)
                └── mi_calculator.analyze_directory_mi()  (pure Python)
                        └── halstead.compute_halstead()
              ↓
    Merge by file path / class name → AnalyzeResponse dict
"""

import os
import math
import time
import logging
import asyncio
from functools import partial
from typing import Optional

from services.ck_metrics import run_ck, compute_class_quality
from services.mi_calculator import analyze_directory_mi, MIResult

logger = logging.getLogger(__name__)


def _normalise(path: str) -> str:
    return os.path.realpath(path)


def analyze_project(project_dir: str, pattern_name: str = "") -> dict:
    """Run the full CK + MI analysis pipeline on *project_dir*.

    Graceful degradation: if CK is unavailable (no Java, missing JAR),
    the pipeline still returns MI-only results.

    Returns a dict matching the ``AnalyzeResponse`` Pydantic schema.
    """

    t0 = time.time()

    # ------------------------------------------------------------------
    # 1. Try running CK
    # ------------------------------------------------------------------
    ck_classes: list[dict] = []
    ck_methods: list[dict] = []
    ck_available = False

    try:
        ck_result = run_ck(project_dir)
        ck_classes = ck_result.get("classes", [])
        ck_methods = ck_result.get("methods", [])
        ck_available = True
        logger.info("CK analysis succeeded: %d classes, %d methods",
                     len(ck_classes), len(ck_methods))
    except (FileNotFoundError, RuntimeError, TimeoutError) as exc:
        logger.warning("CK unavailable — falling back to MI-only: %s", exc)
    except Exception as exc:
        logger.warning("CK failed unexpectedly — MI-only: %s", exc)

    # ------------------------------------------------------------------
    # 2. Run MI analysis (always available — pure Python)
    # ------------------------------------------------------------------
    mi_results: list[MIResult] = analyze_directory_mi(
        project_dir,
        ck_class_data=ck_classes if ck_available else None,
    )

    # Build lookup: normalised file path → MIResult
    mi_by_file: dict[str, MIResult] = {}
    for mi in mi_results:
        mi_by_file[_normalise(mi.file_path)] = mi

    # ------------------------------------------------------------------
    # 3. Merge CK + MI per class
    # ------------------------------------------------------------------
    class_analyses: list[dict] = []
    seen_files: set[str] = set()

    if ck_available:
        for cls_row in ck_classes:
            norm_file = _normalise(cls_row.get("file", ""))
            seen_files.add(norm_file)

            # Find matching MI result
            mi = mi_by_file.get(norm_file)

            # Build MI sub-dict
            mi_dict = _mi_to_dict(mi) if mi else _empty_mi_dict()

            # CK sub-dict
            ck_dict = {
                "cbo": cls_row.get("cbo", 0),
                "wmc": cls_row.get("wmc", 0),
                "dit": cls_row.get("dit", 0),
                "noc": cls_row.get("noc", 0),
                "rfc": cls_row.get("rfc", 0),
                "lcom": float(cls_row.get("lcom", 0)),
                "lcom_star": float(cls_row.get("lcom*", 0)),
                "tcc": float(cls_row.get("tcc", 0)),
                "lcc": float(cls_row.get("lcc", 0)),
                "loc": cls_row.get("loc", 0),
                "total_methods": cls_row.get("totalMethodsQty", 0),
                "fanin": cls_row.get("fanin", 0),
                "fanout": cls_row.get("fanout", 0),
            }

            quality = compute_class_quality(cls_row, pattern_name)

            class_name = cls_row.get("class", "Unknown")
            # Use only the simple name (after last dot)
            simple_name = class_name.split(".")[-1] if "." in class_name else class_name

            class_analyses.append({
                "class_name": simple_name,
                "file_path": cls_row.get("file", ""),
                "type": cls_row.get("type", "class"),
                "ck": ck_dict,
                "mi": mi_dict,
                "ck_scores": quality["scores"],
                "ck_overall_score": quality["overall_score"],
                "flags": quality["flags"],
                "pattern_notes": quality["pattern_notes"],
            })

    # Add MI-only entries for files not covered by CK
    for mi in mi_results:
        norm = _normalise(mi.file_path)
        if norm in seen_files:
            continue
        class_analyses.append({
            "class_name": mi.class_name,
            "file_path": mi.file_path,
            "type": "class",
            "ck": None,
            "mi": _mi_to_dict(mi),
            "ck_scores": None,
            "ck_overall_score": None,
            "flags": [],
            "pattern_notes": [],
        })

    # ------------------------------------------------------------------
    # 4. Build method list (CK only)
    # ------------------------------------------------------------------
    method_list: list[dict] = []
    if ck_available:
        for m in ck_methods:
            method_name = m.get("method", "unknown")
            class_name = m.get("class", "Unknown")
            simple_name = class_name.split(".")[-1] if "." in class_name else class_name
            method_list.append({
                "class_name": simple_name,
                "method_name": method_name,
                "is_constructor": str(m.get("constructor", "false")).lower() == "true",
                "line": m.get("line", 0),
                "complexity": m.get("wmc", 0),
                "loc": m.get("loc", 0),
                "parameters": m.get("parametersQty", 0),
                "max_nesting": m.get("maxNestedBlocksQty", 0),
            })

    # ------------------------------------------------------------------
    # 5. Summary statistics
    # ------------------------------------------------------------------
    total_classes = len(class_analyses)
    total_methods = len(method_list)
    total_files = len(mi_results)

    # MI aggregates — use unique *file-level* MI values only.
    # CK reports inner/anonymous classes separately but they share the
    # same file.  Averaging over all CK rows would count a file's MI
    # multiple times, dragging down the average.
    file_mi: dict[str, dict] = {}   # norm_path → mi dict (first seen)
    for c in class_analyses:
        mi_d = c.get("mi")
        if not mi_d or mi_d["sloc"] == 0:
            continue
        fp = _normalise(c.get("file_path", ""))
        if fp and fp not in file_mi:
            file_mi[fp] = mi_d

    unique_mi = list(file_mi.values())
    mi_scores = [m["mi_score"] for m in unique_mi]
    avg_mi = _avg(mi_scores)
    min_mi = min(mi_scores) if mi_scores else 0.0
    max_mi = max(mi_scores) if mi_scores else 0.0

    mi_dist = {"green": 0, "yellow": 0, "red": 0}
    for m in unique_mi:
        mi_dist[m["mi_color"]] = mi_dist.get(m["mi_color"], 0) + 1

    # Halstead aggregates (file-level, deduplicated)
    h_volumes = [m["halstead_volume"] for m in unique_mi]
    h_diffs = [m["halstead"]["difficulty"] for m in unique_mi]
    h_bugs = [m["halstead"]["estimated_bugs"] for m in unique_mi]
    slocs = [m["sloc"] for m in unique_mi]

    # CK aggregates (only if available)
    ck_summary: dict = {}
    if ck_available and ck_classes:
        ck_summary = {
            "avg_wmc": _avg([c.get("wmc", 0) for c in ck_classes]),
            "avg_cbo": _avg([c.get("cbo", 0) for c in ck_classes]),
            "avg_lcom_star": _avg([c.get("lcom*", 0) for c in ck_classes]),
            "avg_tcc": _avg([c.get("tcc", 0) for c in ck_classes]),
            "avg_rfc": _avg([c.get("rfc", 0) for c in ck_classes]),
            "avg_dit": _avg([c.get("dit", 0) for c in ck_classes]),
        }
        # Overall CK score = average of per-class overall_scores
        per_class_scores = []
        for cls_row in ck_classes:
            q = compute_class_quality(cls_row, pattern_name)
            per_class_scores.append(q["overall_score"])
        ck_summary["ck_overall_score"] = _avg(per_class_scores)

    summary = {
        "total_classes": total_classes,
        "total_methods": total_methods,
        "total_files": total_files,
        "pattern_name": pattern_name,
        "avg_mi_score": round(avg_mi, 2),
        "min_mi_score": round(min_mi, 2),
        "max_mi_score": round(max_mi, 2),
        "mi_distribution": mi_dist,
        "avg_wmc": ck_summary.get("avg_wmc"),
        "avg_cbo": ck_summary.get("avg_cbo"),
        "avg_lcom_star": ck_summary.get("avg_lcom_star"),
        "avg_tcc": ck_summary.get("avg_tcc"),
        "avg_rfc": ck_summary.get("avg_rfc"),
        "avg_dit": ck_summary.get("avg_dit"),
        "ck_overall_score": ck_summary.get("ck_overall_score"),
        "avg_halstead_volume": round(_avg(h_volumes), 2),
        "avg_halstead_difficulty": round(_avg(h_diffs), 2),
        "total_estimated_bugs": round(sum(h_bugs), 4) if h_bugs else 0.0,
        "avg_sloc": round(_avg(slocs), 2),
    }

    elapsed = time.time() - t0
    logger.info("Full analysis pipeline completed in %.2fs (%d classes, %d methods)",
                elapsed, total_classes, total_methods)

    return {
        "summary": summary,
        "classes": class_analyses,
        "methods": method_list,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _avg(values: list) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _mi_to_dict(mi: MIResult) -> dict:
    """Convert an ``MIResult`` dataclass to a plain dict for JSON serialisation."""
    return {
        "mi_score": mi.mi_score,
        "mi_label": mi.mi_label,
        "mi_color": mi.mi_color,
        "halstead_volume": mi.halstead_volume,
        "cyclomatic_complexity": mi.cyclomatic_complexity,
        "sloc": mi.sloc,
        "halstead": {
            "distinct_operators": mi.halstead.distinct_operators,
            "distinct_operands": mi.halstead.distinct_operands,
            "total_operators": mi.halstead.total_operators,
            "total_operands": mi.halstead.total_operands,
            "vocabulary": mi.halstead.vocabulary,
            "program_length": mi.halstead.program_length,
            "volume": round(mi.halstead.volume, 2),
            "difficulty": round(mi.halstead.difficulty, 2),
            "effort": round(mi.halstead.effort, 2),
            "estimated_bugs": round(mi.halstead.estimated_bugs, 4),
            "estimated_time_seconds": round(mi.halstead.estimated_time, 2),
        },
    }


def _empty_mi_dict() -> dict:
    """Fallback MI dict when no MI result was computed for a class."""
    return {
        "mi_score": 0.0,
        "mi_label": "Difficult to Maintain",
        "mi_color": "red",
        "halstead_volume": 0.0,
        "cyclomatic_complexity": 0,
        "sloc": 0,
        "halstead": {
            "distinct_operators": 0,
            "distinct_operands": 0,
            "total_operators": 0,
            "total_operands": 0,
            "vocabulary": 0,
            "program_length": 0,
            "volume": 0.0,
            "difficulty": 0.0,
            "effort": 0.0,
            "estimated_bugs": 0.0,
            "estimated_time_seconds": 0.0,
        },
    }


# ---------------------------------------------------------------------------
# Async wrapper
# ---------------------------------------------------------------------------

async def analyze_project_async(project_dir: str, pattern_name: str = "") -> dict:
    """Async wrapper — runs the synchronous pipeline in a thread executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        partial(analyze_project, project_dir, pattern_name),
    )
