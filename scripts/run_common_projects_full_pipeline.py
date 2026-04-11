"""Run full generation + quality pipeline for common Java project contexts.

Pipeline per project context:
1) Generate one batch of design-pattern projects (default: all passing patterns, expected 83)
2) Compute MI + CK metrics for each generated pattern project
3) Compute PIQS when supported (factory-method, strategy, composite, observer, singleton)
4) Write a consolidated JSON report with human-readable project titles

Usage:
    python3 scripts/run_common_projects_full_pipeline.py

Optional environment variables:
    MODEL=qwen3-coder-30b-a3b-instruct
    CONCURRENCY=2
    PATTERNS_LIMIT=83
    POLL_SECONDS=2
    OUTPUT_FILE=generated_common_projects_pipeline_results.json
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from llm.client import OllamaClient
from services.batch_generation_service import BatchGenerationService
from services.batch_metrics_service import BatchMetricsService
from services.file_service import FileService
from services.piqs_service import PIQSService
from services.prompt_service import PromptService

COMMON_PROJECTS_FILE = ROOT_DIR / "common_java_projects.json"
DEFAULT_OUTPUT = ROOT_DIR / "generated_common_projects_pipeline_results.json"

PIQS_SUPPORTED_PATTERNS = {
    "factory-method",
    "strategy",
    "composite",
    "observer",
    "singleton",
}


def slugify(text: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return base or "untitled-project"


def load_common_projects(path: Path) -> list[dict[str, str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("common_java_projects.json must contain a JSON array.")

    projects: list[dict[str, str]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        title = str(row.get("project_title", "")).strip()
        context = str(row.get("project_context", "")).strip()
        if title and context:
            projects.append({"project_title": title, "project_context": context})

    if not projects:
        raise ValueError("No valid project entries found in common_java_projects.json")
    return projects


async def wait_for_job_completion(
    batch_service: BatchGenerationService,
    job_id: str,
    poll_seconds: float,
) -> dict[str, Any]:
    """Poll job status until it reaches a terminal state."""
    terminal_states = {"completed", "failed"}
    while True:
        job = batch_service.get_job(job_id)
        if not job:
            raise RuntimeError(f"Job disappeared from store: {job_id}")

        status = str(job.get("status", "")).lower()
        if status in terminal_states:
            return job

        await asyncio.sleep(max(0.2, poll_seconds))


def compute_piqs_for_job(
    job: dict[str, Any],
    output_root: Path,
    file_service: FileService,
    piqs_service: PIQSService,
) -> dict[str, dict[str, Any]]:
    """Compute PIQS for supported patterns in a completed generation job."""
    results: dict[str, dict[str, Any]] = {}

    for row in job.get("results", []):
        pattern = str(row.get("pattern", "")).strip()
        status = str(row.get("status", "")).strip().lower()
        zip_rel = row.get("output_zip_relative_path")

        if status != "success" or not pattern:
            results[pattern] = {"piqs": None, "piqs_status": "skipped"}
            continue

        if pattern not in PIQS_SUPPORTED_PATTERNS:
            results[pattern] = {"piqs": None, "piqs_status": "unsupported_pattern"}
            continue

        if not zip_rel:
            results[pattern] = {"piqs": None, "piqs_status": "error", "piqs_error": "Missing zip path"}
            continue

        abs_zip = output_root / str(zip_rel)
        if not abs_zip.exists():
            results[pattern] = {
                "piqs": None,
                "piqs_status": "error",
                "piqs_error": f"Zip not found: {abs_zip}",
            }
            continue

        saved_path: str | None = None
        extracted_path: str | None = None
        try:
            saved_path = file_service.save_upload(abs_zip.read_bytes(), abs_zip.name)
            extracted_path = file_service.extract_zip(saved_path)
            java_files = file_service.walk_java_files(extracted_path)
            piqs = piqs_service.evaluate(pattern_name=pattern, java_files=java_files)
            results[pattern] = {"piqs": piqs, "piqs_status": "success"}
        except Exception as exc:
            results[pattern] = {"piqs": None, "piqs_status": "error", "piqs_error": str(exc)}
        finally:
            file_service.cleanup(saved_path, extracted_path)

    return results


def merge_piqs_into_metrics(
    metrics_result: dict[str, Any],
    piqs_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Attach PIQS details to each pattern item in the metrics response."""
    patterns = metrics_result.get("patterns", [])
    for item in patterns:
        pattern = str(item.get("pattern", "")).strip()
        piqs_data = piqs_map.get(pattern, {"piqs": None, "piqs_status": "missing"})
        item["piqs"] = piqs_data.get("piqs")
        item["piqs_status"] = piqs_data.get("piqs_status", "missing")
        if piqs_data.get("piqs_error"):
            item["piqs_error"] = piqs_data["piqs_error"]
    return metrics_result


async def run_pipeline() -> None:
    model = os.getenv("MODEL", "qwen3-coder-30b-a3b-instruct")
    concurrency = int(os.getenv("CONCURRENCY", "2"))
    patterns_limit_env = os.getenv("PATTERNS_LIMIT", "").strip()
    patterns_limit = int(patterns_limit_env) if patterns_limit_env else None
    poll_seconds = float(os.getenv("POLL_SECONDS", "2"))
    output_file = ROOT_DIR / os.getenv("OUTPUT_FILE", DEFAULT_OUTPUT.name)

    projects = load_common_projects(COMMON_PROJECTS_FILE)

    file_service = FileService()
    ollama_client = OllamaClient()
    prompt_service = PromptService()
    batch_service = BatchGenerationService(ollama_client=ollama_client, prompt_service=prompt_service)
    batch_metrics = BatchMetricsService(batch_generation_service=batch_service, file_service=file_service)
    piqs_service = PIQSService()

    if not ollama_client.is_running():
        raise RuntimeError("LLM server is not reachable. Start LM Studio/Ollama-compatible server first.")

    all_projects: list[dict[str, Any]] = []

    for index, project in enumerate(projects, start=1):
        title = project["project_title"]
        context = project["project_context"]
        project_key = slugify(title)

        print(f"\n[{index}/{len(projects)}] Starting generation for: {title}")
        started_at = time.time()

        started = await batch_service.start_job(
            project_context=context,
            model=model,
            concurrency=concurrency,
            patterns_limit=patterns_limit,
        )
        job_id = str(started["job_id"])
        print(f"- Job created: {job_id}")

        job = await wait_for_job_completion(batch_service, job_id, poll_seconds)
        status = str(job.get("status", "unknown"))
        print(f"- Generation finished with status: {status}")

        project_result: dict[str, Any] = {
            "project_title": title,
            "project_name": project_key,
            "project_context": context,
            "job_id": job_id,
            "generation_status": status,
            "generation_summary": {
                "total_patterns": job.get("total_patterns"),
                "completed_patterns": job.get("completed_patterns"),
                "successful_patterns": job.get("successful_patterns"),
                "failed_patterns": job.get("failed_patterns"),
            },
            "metrics": None,
            "duration_seconds": round(time.time() - started_at, 2),
            "error": None,
        }

        if status == "completed":
            try:
                metrics_result = await batch_metrics.analyze_job_metrics(job_id)
                piqs_map = await asyncio.to_thread(
                    compute_piqs_for_job,
                    job,
                    batch_service.output_root,
                    file_service,
                    piqs_service,
                )
                metrics_result = merge_piqs_into_metrics(metrics_result, piqs_map)
                project_result["metrics"] = metrics_result
            except Exception as exc:
                project_result["error"] = f"Metrics pipeline failed: {exc}"
        else:
            project_result["error"] = "Generation job did not complete successfully."

        all_projects.append(project_result)

    report = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "source_projects_file": COMMON_PROJECTS_FILE.name,
        "model_used": model,
        "concurrency": concurrency,
        "patterns_limit": patterns_limit,
        "project_count": len(all_projects),
        "projects": all_projects,
    }

    output_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved report: {output_file}")


if __name__ == "__main__":
    asyncio.run(run_pipeline())
