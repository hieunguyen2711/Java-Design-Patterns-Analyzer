import asyncio
import copy
import json
import logging
import re
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Dict, List

from config import settings
from llm.client import OllamaClient
from services.prompt_service import PromptService

logger = logging.getLogger(__name__)


class BatchGenerationService:
    """Orchestrate batch project generation for pass patterns with one shared context."""

    def __init__(self, ollama_client: OllamaClient, prompt_service: PromptService) -> None:
        self.ollama_client = ollama_client
        self.prompt_service = prompt_service
        self.root_dir = Path(__file__).resolve().parent.parent
        self.pass_patterns_file = self._resolve_path(settings.PASS_PATTERNS_FILE)
        self.output_root = self._resolve_path(settings.BATCH_OUTPUT_DIR)
        self.output_root.mkdir(parents=True, exist_ok=True)

        self._jobs: Dict[str, dict] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._lock = threading.Lock()

    async def start_job(
        self,
        project_context: str,
        model: str,
        concurrency: int,
        patterns_limit: int | None = None,
    ) -> dict:
        """Create and enqueue a new batch generation job."""
        patterns = self.load_pass_patterns(patterns_limit=patterns_limit)

        job_id = uuid.uuid4().hex
        job_dir = self.output_root / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        started_at = time.time()
        results = [
            {
                "pattern": pattern,
                "status": "queued",
                "files_count": 0,
                "duration_ms": 0,
                "output_zip_relative_path": None,
                "error": None,
            }
            for pattern in patterns
        ]

        job = {
            "job_id": job_id,
            "status": "queued",
            "model_used": model,
            "project_context": project_context,
            "concurrency": concurrency,
            "total_patterns": len(patterns),
            "completed_patterns": 0,
            "successful_patterns": 0,
            "failed_patterns": 0,
            "started_at": started_at,
            "updated_at": started_at,
            "completed_at": None,
            "output_dir": str(job_dir),
            "final_bundle_relative_path": None,
            "results": results,
        }

        with self._lock:
            self._jobs[job_id] = job

        self._write_manifest(job)

        task = asyncio.create_task(
            self._run_job(
                job_id=job_id,
                project_context=project_context,
                model=model,
                concurrency=concurrency,
            )
        )
        with self._lock:
            self._tasks[job_id] = task

        return {
            "job_id": job_id,
            "status": "queued",
            "total_patterns": len(patterns),
            "output_dir": job_dir.relative_to(self.root_dir).as_posix(),
        }

    def get_job(self, job_id: str) -> dict | None:
        """Return the current job snapshot by ID."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                return copy.deepcopy(job)

        manifest_path = self.output_root / job_id / "manifest.json"
        if not manifest_path.exists():
            return None

        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

        return loaded if isinstance(loaded, dict) else None

    def get_final_bundle_path(self, job_id: str) -> Path | None:
        """Resolve final bundle zip path for a completed job."""
        job = self.get_job(job_id)
        if not job:
            return None

        relative_path = job.get("final_bundle_relative_path")
        if not relative_path:
            return None

        return self.output_root / relative_path

    def load_pass_patterns(self, patterns_limit: int | None = None) -> List[str]:
        """Load pass patterns from the configured JSON file."""
        if not self.pass_patterns_file.exists():
            raise FileNotFoundError(f"Pass patterns file not found: {self.pass_patterns_file}")

        try:
            data = json.loads(self.pass_patterns_file.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ValueError(f"Invalid JSON in pass patterns file: {self.pass_patterns_file}") from exc

        if not isinstance(data, list):
            raise ValueError("Pass patterns file must contain a JSON array.")

        ordered_patterns: List[str] = []
        seen: set[str] = set()
        for row in data:
            if not isinstance(row, dict):
                continue
            if str(row.get("Status", "")).strip().lower() != "pass":
                continue
            pattern = str(row.get("pattern", "")).strip()
            if not pattern or pattern in seen:
                continue
            seen.add(pattern)
            ordered_patterns.append(pattern)

        if not ordered_patterns:
            raise ValueError("No passing patterns found in pass patterns file.")

        expected = settings.EXPECTED_PASS_PATTERN_COUNT
        if patterns_limit is None and expected > 0 and len(ordered_patterns) != expected:
            raise ValueError(
                f"Expected {expected} passing patterns, found {len(ordered_patterns)}. "
                f"Check {self.pass_patterns_file.name}."
            )

        if patterns_limit is not None:
            return ordered_patterns[:patterns_limit]

        return ordered_patterns

    async def _run_job(self, job_id: str, project_context: str, model: str, concurrency: int) -> None:
        """Run all pattern generation tasks and update job progress."""
        job = self.get_job(job_id)
        if not job:
            return

        try:
            self._set_job_status(job_id, "running")

            patterns = [result["pattern"] for result in job["results"]]
            max_concurrency = max(1, settings.BATCH_MAX_CONCURRENCY)
            effective_concurrency = min(max(1, concurrency), max_concurrency)
            semaphore = asyncio.Semaphore(effective_concurrency)

            async def worker(index: int, pattern: str):
                async with semaphore:
                    result = await asyncio.to_thread(
                        self._generate_pattern_with_retries,
                        job_id,
                        pattern,
                        project_context,
                        model,
                    )
                    return index, result

            tasks = [
                asyncio.create_task(worker(index, pattern))
                for index, pattern in enumerate(patterns)
            ]

            for task in asyncio.as_completed(tasks):
                index, result = await task
                self._record_pattern_result(job_id, index, result)

            current_job = self.get_job(job_id)
            if current_job:
                self._write_results(current_job)

            final_bundle_relative_path = await asyncio.to_thread(self._create_final_bundle, job_id)
            self._finalize_job(job_id, final_bundle_relative_path)
        except Exception as exc:
            logger.exception("Batch generation job failed: job_id=%s", job_id)
            self._fail_job(job_id, str(exc))
        finally:
            with self._lock:
                self._tasks.pop(job_id, None)

    def _generate_pattern_with_retries(
        self,
        job_id: str,
        pattern: str,
        project_context: str,
        model: str,
    ) -> dict:
        """Generate one pattern with retry policy."""
        max_attempts = max(1, settings.BATCH_RETRY_COUNT + 1)
        retry_delay = max(0.0, settings.BATCH_RETRY_DELAY_SECONDS)

        started = time.time()
        last_error: str | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                return self._generate_single_pattern(job_id, pattern, project_context, model)
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "Pattern generation failed: job_id=%s pattern=%s attempt=%d/%d error=%s",
                    job_id,
                    pattern,
                    attempt,
                    max_attempts,
                    exc,
                )
                if attempt < max_attempts and retry_delay > 0:
                    time.sleep(retry_delay)

        duration_ms = int((time.time() - started) * 1000)
        return {
            "pattern": pattern,
            "status": "failed",
            "files_count": 0,
            "duration_ms": duration_ms,
            "output_zip_relative_path": None,
            "error": last_error or "Unknown error",
        }

    def _generate_single_pattern(
        self,
        job_id: str,
        pattern: str,
        project_context: str,
        model: str,
    ) -> dict:
        """Generate and package one project for a single design pattern."""
        started = time.time()

        pattern_slug = self._sanitize_name(pattern)
        job_dir = self.output_root / job_id
        pattern_dir = job_dir / pattern_slug
        pattern_dir.mkdir(parents=True, exist_ok=True)

        prompt = self.prompt_service.build_batch_generate_prompt(pattern, project_context)
        raw = self.ollama_client.generate(prompt, model)
        generated_files = self.prompt_service.parse_generated_files(raw)

        (pattern_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
        (pattern_dir / "raw_response.txt").write_text(raw, encoding="utf-8")

        project_name = f"{pattern_slug}-project"
        project_zip_path = pattern_dir / f"{pattern_slug}.zip"
        self._package_project_zip(project_zip_path, project_name, generated_files)

        duration_ms = int((time.time() - started) * 1000)
        return {
            "pattern": pattern,
            "status": "success",
            "files_count": len(generated_files),
            "duration_ms": duration_ms,
            "output_zip_relative_path": project_zip_path.relative_to(self.output_root).as_posix(),
            "error": None,
        }

    def _record_pattern_result(self, job_id: str, index: int, result: dict) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return

            job["results"][index] = result
            job["completed_patterns"] += 1
            if result.get("status") == "success":
                job["successful_patterns"] += 1
            else:
                job["failed_patterns"] += 1
            job["updated_at"] = time.time()
            snapshot = copy.deepcopy(job)

        self._write_manifest(snapshot)

    def _set_job_status(self, job_id: str, status: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job["status"] = status
            job["updated_at"] = time.time()
            snapshot = copy.deepcopy(job)

        self._write_manifest(snapshot)

    def _finalize_job(self, job_id: str, final_bundle_relative_path: str) -> None:
        completed_at = time.time()
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return

            job["status"] = "completed"
            job["completed_at"] = completed_at
            job["updated_at"] = completed_at
            job["final_bundle_relative_path"] = final_bundle_relative_path
            snapshot = copy.deepcopy(job)

        self._write_results(snapshot)
        self._write_manifest(snapshot)

    def _fail_job(self, job_id: str, error: str) -> None:
        completed_at = time.time()
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return

            for result in job["results"]:
                if result.get("status") == "queued":
                    result["status"] = "failed"
                    result["error"] = "Job terminated before pattern execution"

            job["status"] = "failed"
            job["completed_at"] = completed_at
            job["updated_at"] = completed_at
            snapshot = copy.deepcopy(job)

        (Path(snapshot["output_dir"]) / "error.txt").write_text(error, encoding="utf-8")
        self._write_results(snapshot)
        self._write_manifest(snapshot)

    def _create_final_bundle(self, job_id: str) -> str:
        """Create one zip artifact containing all successful generated projects and results."""
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        job_dir = Path(job["output_dir"])
        bundle_path = job_dir / "generated_projects_bundle.zip"

        with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for result in job.get("results", []):
                relative_zip = result.get("output_zip_relative_path")
                if not relative_zip:
                    continue
                abs_zip = self.output_root / relative_zip
                if not abs_zip.exists():
                    continue

                pattern_name = self._sanitize_name(result.get("pattern", abs_zip.stem))
                bundle.write(abs_zip, arcname=f"projects/{pattern_name}.zip")

            results_path = job_dir / "results.json"
            if results_path.exists():
                bundle.write(results_path, arcname="results.json")

            manifest_path = job_dir / "manifest.json"
            if manifest_path.exists():
                bundle.write(manifest_path, arcname="manifest.json")

        return bundle_path.relative_to(self.output_root).as_posix()

    def _write_manifest(self, job: dict) -> None:
        """Persist job metadata for tracking and recovery."""
        manifest_path = Path(job["output_dir"]) / "manifest.json"
        manifest_path.write_text(json.dumps(job, indent=2, ensure_ascii=False), encoding="utf-8")

    def _write_results(self, job: dict) -> None:
        """Persist per-pattern result list for easy inspection."""
        results_path = Path(job["output_dir"]) / "results.json"
        results_path.write_text(
            json.dumps(job.get("results", []), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _package_project_zip(
        self,
        zip_path: Path,
        project_name: str,
        files: List[dict],
    ) -> None:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for generated in files:
                filename = Path(str(generated.get("filename", "GeneratedCode.java"))).name
                if not filename.endswith(".java"):
                    filename = f"{filename}.java"
                content = str(generated.get("content", ""))
                path_in_zip = f"{project_name}/src/main/java/{filename}"
                archive.writestr(path_in_zip, content)

            pom = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<project xmlns=\"http://maven.apache.org/POM/4.0.0\"
         xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\"
         xsi:schemaLocation=\"http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd\">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>{project_name}</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.source>17</maven.compiler.source>
        <maven.compiler.target>17</maven.compiler.target>
    </properties>
</project>
"""
            archive.writestr(f"{project_name}/pom.xml", pom)

    def _resolve_path(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return self.root_dir / path

    @staticmethod
    def _sanitize_name(value: str) -> str:
        lowered = value.lower().strip()
        sanitized = re.sub(r"[^a-z0-9\-]+", "-", lowered).strip("-")
        return sanitized or "generated-project"
