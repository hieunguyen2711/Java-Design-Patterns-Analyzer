"""
BatchMetricsService

Iterates over every successfully generated pattern zip in a completed batch
generation job, runs the full CK + MI analysis pipeline on each one, and
returns a consolidated metrics summary.
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

from app.core import settings
from app.services.analysis_pipeline import analyze_project_async
from app.services.batch_generation_service import BatchGenerationService
from app.services.file_service import FileService

logger = logging.getLogger(__name__)


class BatchMetricsService:
    """Analyze metrics for all generated patterns in a completed batch job."""

    def __init__(
        self,
        batch_generation_service: BatchGenerationService,
        file_service: FileService,
    ) -> None:
        self.batch_svc = batch_generation_service
        self.file_service = file_service
        self._semaphore = asyncio.Semaphore(settings.BATCH_MAX_CONCURRENCY)

    async def analyze_job_metrics(self, job_id: str) -> dict:
        """Run CK + MI analysis on every successful pattern zip in *job_id*.

        Returns:
            A dict matching the ``BatchMetricsResponse`` Pydantic schema.

        Raises:
            KeyError:  job_id not found.
            ValueError: job has not reached ``completed`` status yet.
        """
        job = self.batch_svc.get_job(job_id)
        if not job:
            raise KeyError(f"Job not found: {job_id}")
        if job.get("status") != "completed":
            raise ValueError(
                f"Job '{job_id}' is not completed yet (status: {job['status']}). "
                "Wait for the generation job to finish before requesting metrics."
            )

        results: list[dict] = job.get("results", [])
        project_context: str = job.get("project_context", "")
        model_used: str = job.get("model_used", "")

        # Dispatch all per-pattern tasks concurrently (bounded by semaphore)
        tasks = [
            self._analyze_pattern(result)
            for result in results
        ]
        pattern_summaries: list[dict] = list(await asyncio.gather(*tasks))

        analyzed = sum(1 for p in pattern_summaries if p["status"] == "success")
        skipped = len(pattern_summaries) - analyzed

        title = (
            f"Batch Metrics — {project_context} ({analyzed} / {len(results)} patterns analysed)"
        )

        return {
            "title": title,
            "project_context": project_context,
            "job_id": job_id,
            "model_used": model_used,
            "total_patterns": len(results),
            "analyzed_patterns": analyzed,
            "skipped_patterns": skipped,
            "patterns": pattern_summaries,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _analyze_pattern(self, result: dict) -> dict:
        """Run the analysis pipeline for a single pattern result entry."""
        pattern_name: str = result.get("pattern", "unknown")
        zip_rel: Optional[str] = result.get("output_zip_relative_path")
        gen_status: str = result.get("status", "failed")

        if gen_status != "success" or not zip_rel:
            return {
                "pattern": pattern_name,
                "status": "skipped",
                "mi": None,
                "ck": None,
                "error": result.get("error") or "Pattern generation did not produce a zip",
            }

        abs_zip = self.batch_svc.output_root / zip_rel
        if not abs_zip.exists():
            return {
                "pattern": pattern_name,
                "status": "skipped",
                "mi": None,
                "ck": None,
                "error": f"Zip file not found on disk: {abs_zip}",
            }

        async with self._semaphore:
            return await asyncio.to_thread(self._analyze_pattern_sync, pattern_name, abs_zip)

    def _analyze_pattern_sync(self, pattern_name: str, abs_zip: Path) -> dict:
        """Synchronous extraction + analysis (runs in thread executor)."""
        saved_path: Optional[str] = None
        extracted_path: Optional[str] = None
        try:
            zip_bytes = abs_zip.read_bytes()
            saved_path = self.file_service.save_upload(zip_bytes, abs_zip.name)
            extracted_path = self.file_service.extract_zip(saved_path)

            # analyze_project is synchronous; we're already in a thread
            from app.services.analysis_pipeline import analyze_project  # local import avoids circular
            analysis = analyze_project(extracted_path, pattern_name=pattern_name)
            summary: dict = analysis.get("summary", {})

            mi_summary = {
                "avg_mi_score": summary.get("avg_mi_score", 0.0),
                "min_mi_score": summary.get("min_mi_score", 0.0),
                "max_mi_score": summary.get("max_mi_score", 0.0),
                "mi_distribution": summary.get("mi_distribution", {}),
            }

            ck_overall = summary.get("ck_overall_score")
            ck_summary = None
            if ck_overall is not None:
                ck_summary = {
                    "ck_overall_score": ck_overall,
                    "ck_q_score": summary.get("ck_q_score"),
                    "avg_wmc": summary.get("avg_wmc"),
                    "avg_cbo": summary.get("avg_cbo"),
                    "avg_lcom_star": summary.get("avg_lcom_star"),
                    "avg_rfc": summary.get("avg_rfc"),
                    "avg_dit": summary.get("avg_dit"),
                    "avg_tcc": summary.get("avg_tcc"),
                }

            return {
                "pattern": pattern_name,
                "status": "success",
                "mi": mi_summary,
                "ck": ck_summary,
                "cqs_score": summary.get("cqs_score"),
                "error": None,
            }

        except Exception as exc:
            logger.warning("Metrics analysis failed for pattern '%s': %s", pattern_name, exc)
            return {
                "pattern": pattern_name,
                "status": "error",
                "mi": None,
                "ck": None,
                "error": str(exc),
            }
        finally:
            self.file_service.cleanup(saved_path, extracted_path)
