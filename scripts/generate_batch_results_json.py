"""Generate a consolidated JSON report for generated batch jobs.

The report includes:
- per-job metadata and progress
- per-job timing and duration
- per-job pattern status counts
- full per-pattern generation details
- global summary across all jobs

Usage:
    /path/to/venv/python scripts/generate_batch_results_json.py
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
BATCHES_DIR = ROOT_DIR / "generated_batches"
OUTPUT_FILE = ROOT_DIR / "batch_generation_details.json"


def ts_to_iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def duration_seconds(started_at: float | None, completed_at: float | None, updated_at: float | None) -> float | None:
    if started_at is None:
        return None
    end = completed_at if completed_at is not None else updated_at
    if end is None:
        return None
    return round(max(0.0, end - started_at), 3)


def load_manifest(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def summarize_job(manifest: dict[str, Any]) -> dict[str, Any]:
    results: list[dict[str, Any]] = manifest.get("results", [])
    status_counter = Counter(item.get("status", "unknown") for item in results)

    started_at = manifest.get("started_at")
    updated_at = manifest.get("updated_at")
    completed_at = manifest.get("completed_at")

    return {
        "job_id": manifest.get("job_id"),
        "status": manifest.get("status"),
        "model_used": manifest.get("model_used"),
        "project_title": manifest.get("project_context", ""),
        "Project title": manifest.get("project_context", ""),
        "project_context": manifest.get("project_context"),
        "concurrency": manifest.get("concurrency"),
        "totals": {
            "total_patterns": manifest.get("total_patterns", len(results)),
            "completed_patterns": manifest.get("completed_patterns", 0),
            "successful_patterns": manifest.get("successful_patterns", 0),
            "failed_patterns": manifest.get("failed_patterns", 0),
            "status_breakdown": dict(status_counter),
        },
        "timing": {
            "started_at_epoch": started_at,
            "updated_at_epoch": updated_at,
            "completed_at_epoch": completed_at,
            "started_at_utc": ts_to_iso(started_at),
            "updated_at_utc": ts_to_iso(updated_at),
            "completed_at_utc": ts_to_iso(completed_at),
            "elapsed_seconds": duration_seconds(started_at, completed_at, updated_at),
        },
        "paths": {
            "output_dir": manifest.get("output_dir"),
            "final_bundle_relative_path": manifest.get("final_bundle_relative_path"),
        },
        "results": results,
    }


def build_report() -> dict[str, Any]:
    manifests = sorted(BATCHES_DIR.glob("*/manifest.json"))
    jobs: list[dict[str, Any]] = []

    global_status_counter = Counter()
    total_patterns = 0
    total_completed = 0
    total_successful = 0
    total_failed = 0

    for manifest_path in manifests:
        manifest = load_manifest(manifest_path)
        if manifest is None:
            continue

        job = summarize_job(manifest)
        jobs.append(job)

        totals = job["totals"]
        total_patterns += totals["total_patterns"]
        total_completed += totals["completed_patterns"]
        total_successful += totals["successful_patterns"]
        total_failed += totals["failed_patterns"]
        global_status_counter.update(totals["status_breakdown"])

    return {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "workspace": str(ROOT_DIR),
        "summary": {
            "job_count": len(jobs),
            "total_patterns": total_patterns,
            "completed_patterns": total_completed,
            "successful_patterns": total_successful,
            "failed_patterns": total_failed,
            "status_breakdown": dict(global_status_counter),
        },
        "jobs": jobs,
    }


def main() -> None:
    report = build_report()
    OUTPUT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = report["summary"]
    print(f"Wrote {OUTPUT_FILE}")
    print(
        "Jobs={job_count} Patterns={total_patterns} Completed={completed_patterns} "
        "Success={successful_patterns} Failed={failed_patterns}".format(**summary)
    )


if __name__ == "__main__":
    main()
