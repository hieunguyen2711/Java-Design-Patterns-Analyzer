"""Generate a consolidated MI + CK + PIQS report for completed generated batches.

This script reads every completed batch under generated_batches/, analyzes each
successful generated project zip, and writes one JSON file with:
- per-pattern MI summary
- per-pattern CK summary
- per-pattern PIQS result (for supported patterns)

Usage:
    python3 scripts/run_generated_batches_quality.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.analysis_pipeline import analyze_project
from services.file_service import FileService
from services.piqs_service import PIQSService

BATCHES_DIR = ROOT_DIR / "generated_batches"
GENERATED_PIQS_DIR = ROOT_DIR / "generated_batches_piqs"
OUTPUT_FILE = ROOT_DIR / "generated_batches_quality_results.json"

PIQS_SUPPORTED_PATTERNS = {
    "factory-method",
    "strategy",
    "composite",
    "observer",
    "singleton",
}


def load_completed_jobs() -> list[tuple[str, dict[str, Any]]]:
    jobs: list[tuple[str, dict[str, Any]]] = []
    for manifest_path in sorted(BATCHES_DIR.glob("*/manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if manifest.get("status") == "completed":
            jobs.append((manifest_path.parent.name, manifest))
    return jobs


def summarize_overall(items: list[dict[str, Any]]) -> dict[str, Any]:
    analyzed = [row for row in items if row.get("status") == "success"]
    with_piqs = [row for row in analyzed if row.get("piqs") is not None]

    mi_values = [
        row["metrics"]["summary"].get("avg_mi_score")
        for row in analyzed
        if row.get("metrics") and row["metrics"].get("summary", {}).get("avg_mi_score") is not None
    ]
    ck_values = [
        row["metrics"]["summary"].get("ck_overall_score")
        for row in analyzed
        if row.get("metrics") and row["metrics"].get("summary", {}).get("ck_overall_score") is not None
    ]
    piqs_values = [
        row["piqs"].get("final_quality_result_piqs", {}).get("result_percent")
        for row in with_piqs
        if row.get("piqs")
        and row["piqs"].get("final_quality_result_piqs", {}).get("result_percent") is not None
    ]

    status_counts = Counter(row.get("status", "unknown") for row in items)
    piqs_status_counts = Counter(row.get("piqs_status", "unknown") for row in analyzed)

    return {
        "total_patterns": len(items),
        "analyzed_patterns": len(analyzed),
        "status_breakdown": dict(status_counts),
        "piqs_status_breakdown": dict(piqs_status_counts),
        "avg_mi_score": round(sum(mi_values) / len(mi_values), 2) if mi_values else None,
        "avg_ck_overall_score": round(sum(ck_values) / len(ck_values), 2) if ck_values else None,
        "avg_piqs_score": round(sum(piqs_values) / len(piqs_values), 2) if piqs_values else None,
    }


def is_hex_job_id(name: str) -> bool:
    return len(name) == 32 and all(ch in "0123456789abcdef" for ch in name.lower())


def load_custom_piqs_projects() -> list[tuple[str, str, list[tuple[str, Path]]]]:
    """Load custom project groups from generated_batches_piqs/<project>/<pattern>/.

    Excludes UUID-like folders that mirror generated batch job IDs.
    """
    groups: list[tuple[str, str, list[tuple[str, Path]]]] = []
    if not GENERATED_PIQS_DIR.exists():
        return groups

    for project_dir in sorted(GENERATED_PIQS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        if project_dir.name.startswith("."):
            continue
        if is_hex_job_id(project_dir.name):
            continue

        patterns: list[tuple[str, Path]] = []
        for pattern_dir in sorted(project_dir.iterdir()):
            if not pattern_dir.is_dir() or pattern_dir.name.startswith("."):
                continue
            patterns.append((pattern_dir.name, pattern_dir))

        if patterns:
            groups.append((project_dir.name, project_dir.name, patterns))

    return groups


def has_java_files(path: Path) -> bool:
    return any(path.rglob("*.java"))


def make_batch_name(project_context: str, fallback_job_id: str) -> str:
    """Create a readable and stable batch label from project context."""
    text = (project_context or "").strip().lower()
    if not text:
        return f"batch-{fallback_job_id[:8]}"
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or f"batch-{fallback_job_id[:8]}"


def run() -> None:
    file_service = FileService()
    piqs_service = PIQSService()

    jobs = load_completed_jobs()
    if not jobs:
        print("No completed generated batches found.")
        return

    all_job_results: list[dict[str, Any]] = []
    all_pattern_rows: list[dict[str, Any]] = []

    for job_id, manifest in jobs:
        project_context = manifest.get("project_context", "")
        batch_name = make_batch_name(project_context, job_id)
        print(f"\nBatch {batch_name} ({job_id})")

        rows: list[dict[str, Any]] = []
        results = manifest.get("results", [])

        for result in results:
            pattern = str(result.get("pattern", "unknown"))
            gen_status = result.get("status")
            zip_rel = result.get("output_zip_relative_path")

            if gen_status != "success" or not zip_rel:
                row = {
                    "pattern": pattern,
                    "status": "skipped",
                    "error": result.get("error") or "Generation did not produce a zip",
                    "metrics": None,
                    "piqs": None,
                    "piqs_status": "not_applicable",
                }
                rows.append(row)
                all_pattern_rows.append(row)
                continue

            abs_zip = BATCHES_DIR / zip_rel
            if not abs_zip.exists():
                row = {
                    "pattern": pattern,
                    "status": "error",
                    "error": f"Zip not found: {abs_zip}",
                    "metrics": None,
                    "piqs": None,
                    "piqs_status": "error",
                }
                rows.append(row)
                all_pattern_rows.append(row)
                continue

            saved_path: str | None = None
            extracted_path: str | None = None
            try:
                zip_bytes = abs_zip.read_bytes()
                saved_path = file_service.save_upload(zip_bytes, abs_zip.name)
                extracted_path = file_service.extract_zip(saved_path)

                metrics = analyze_project(extracted_path, pattern_name=pattern)
                java_files = file_service.walk_java_files(extracted_path)

                piqs_status = "unsupported_pattern"
                piqs = None
                if pattern in PIQS_SUPPORTED_PATTERNS:
                    piqs = piqs_service.evaluate(pattern_name=pattern, java_files=java_files)
                    piqs_status = "success"

                row = {
                    "pattern": pattern,
                    "status": "success",
                    "error": None,
                    "metrics": {
                        "summary": metrics.get("summary", {}),
                    },
                    "piqs": piqs,
                    "piqs_status": piqs_status,
                }
            except Exception as exc:
                row = {
                    "pattern": pattern,
                    "status": "error",
                    "error": str(exc),
                    "metrics": None,
                    "piqs": None,
                    "piqs_status": "error",
                }
            finally:
                file_service.cleanup(saved_path, extracted_path)

            rows.append(row)
            all_pattern_rows.append(row)
            print(f"- {pattern}: {row['status']} (PIQS: {row['piqs_status']})")

        job_summary = summarize_overall(rows)
        all_job_results.append(
            {
                "source_type": "generated_batch",
                "batch_name": batch_name,
                "job_id": job_id,
                "project_context": project_context,
                "model_used": manifest.get("model_used", ""),
                "summary": job_summary,
                "results": rows,
            }
        )

    custom_groups = load_custom_piqs_projects()
    for group_id, project_context, patterns in custom_groups:
        print(f"\nCustom project {group_id}")
        rows: list[dict[str, Any]] = []

        for pattern, project_path in patterns:
            if not has_java_files(project_path):
                row = {
                    "pattern": pattern,
                    "status": "skipped",
                    "error": f"No Java files found under {project_path}",
                    "metrics": None,
                    "piqs": None,
                    "piqs_status": "not_applicable",
                }
                rows.append(row)
                all_pattern_rows.append(row)
                print(f"- {pattern}: skipped (no Java files)")
                continue

            try:
                metrics = analyze_project(str(project_path), pattern_name=pattern)
                java_files = file_service.walk_java_files(str(project_path))

                piqs_status = "unsupported_pattern"
                piqs = None
                if pattern in PIQS_SUPPORTED_PATTERNS:
                    piqs = piqs_service.evaluate(pattern_name=pattern, java_files=java_files)
                    piqs_status = "success"

                row = {
                    "pattern": pattern,
                    "status": "success",
                    "error": None,
                    "metrics": {"summary": metrics.get("summary", {})},
                    "piqs": piqs,
                    "piqs_status": piqs_status,
                }
            except Exception as exc:
                row = {
                    "pattern": pattern,
                    "status": "error",
                    "error": str(exc),
                    "metrics": None,
                    "piqs": None,
                    "piqs_status": "error",
                }

            rows.append(row)
            all_pattern_rows.append(row)
            print(f"- {pattern}: {row['status']} (PIQS: {row['piqs_status']})")

        all_job_results.append(
            {
                "source_type": "custom_project",
                "batch_name": make_batch_name(project_context, group_id),
                "job_id": group_id,
                "project_context": project_context,
                "model_used": "",
                "summary": summarize_overall(rows),
                "results": rows,
            }
        )

    report = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "workspace": str(ROOT_DIR),
        "overall_summary": summarize_overall(all_pattern_rows),
        "jobs": all_job_results,
    }

    OUTPUT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
