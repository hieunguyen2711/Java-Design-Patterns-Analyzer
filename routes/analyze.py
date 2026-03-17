import io
import re
import zipfile
from typing import List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from config import settings
from llm.client import OllamaClient
from models.request_models import (
    BatchGeneratePassProjectsRequest,
    FollowUpRequest,
    GenerateRequest,
    PackageProjectRequest,
)
from models.response_models import (
    AnalysisResponse,
    BatchGeneratePassProjectsStartResponse,
    BatchGeneratePassProjectsStatusResponse,
    BatchMetricsResponse,
    FollowUpResponse,
    GenerateResponse,
)
from services.analysis_service import AnalysisService
from services.batch_generation_service import BatchGenerationService
from services.batch_metrics_service import BatchMetricsService
from services.file_service import FileService
from services.prompt_service import PromptService

router = APIRouter()

file_service = FileService()
ollama_client = OllamaClient()
prompt_service = PromptService()
analysis_service = AnalysisService(file_service=file_service, ollama_client=ollama_client)
batch_generation_service = BatchGenerationService(
    ollama_client=ollama_client,
    prompt_service=prompt_service,
)
batch_metrics_service = BatchMetricsService(
    batch_generation_service=batch_generation_service,
    file_service=file_service,
)


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_zip(file: UploadFile = File(...), model: str = Form(settings.DEFAULT_MODEL)):
    """Analyze a zipped Java project and return design pattern findings."""
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted.")

    if not ollama_client.is_running():
        raise HTTPException(status_code=503, detail="Ollama server is not running.")

    saved_path = None
    extracted_path = None
    try:
        contents = await file.read()
        saved_path = file_service.save_upload(contents, file.filename)
        extracted_path = file_service.extract_zip(saved_path)
        java_files = file_service.walk_java_files(extracted_path)
        return analysis_service.analyze(java_files, model)
    finally:
        file_service.cleanup(saved_path, extracted_path)


@router.post("/analyze-folder", response_model=AnalysisResponse)
async def analyze_folder(files: List[UploadFile] = File(...), model: str = Form(settings.DEFAULT_MODEL)):
    """Analyze a collection of uploaded Java source files."""
    java_files = {}
    for file in files:
        if not file.filename.lower().endswith(".java"):
            continue
        contents = await file.read()
        java_files[file.filename] = contents.decode("utf-8", errors="ignore")

    return analysis_service.analyze(java_files, model)


@router.get("/health")
def health_check():
    """Report API and Ollama service status."""
    return {
        "api": "ok",
        "ollama": ollama_client.is_running(),
        "model": settings.DEFAULT_MODEL,
    }


@router.post("/generate", response_model=GenerateResponse)
def generate_code(request: GenerateRequest):
    """Generate Java code that implements a specified design pattern."""
    if not ollama_client.is_running():
        raise HTTPException(status_code=503, detail="Ollama server is not running.")

    prompt = prompt_service.build_generate_prompt(request.pattern, request.description)
    raw = ollama_client.generate(prompt, request.model)
    parsed = prompt_service.parse_generated_files(raw)

    return GenerateResponse(
        model_used=request.model,
        pattern=request.pattern,
        description=request.description,
        files=[{"filename": f["filename"], "content": f["content"]} for f in parsed],
    )


@router.post(
    "/api/v1/generate-pass-projects",
    response_model=BatchGeneratePassProjectsStartResponse,
    status_code=202,
)
async def generate_pass_projects(request: BatchGeneratePassProjectsRequest):
    """Trigger generation for all passing patterns using one shared project context."""
    if not ollama_client.is_running():
        raise HTTPException(status_code=503, detail="Ollama server is not running.")

    if request.concurrency > settings.BATCH_MAX_CONCURRENCY:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Requested concurrency {request.concurrency} exceeds configured "
                f"maximum {settings.BATCH_MAX_CONCURRENCY}."
            ),
        )

    try:
        started = await batch_generation_service.start_job(
            project_context=request.project_context,
            model=request.model,
            concurrency=request.concurrency,
            patterns_limit=request.patterns_limit,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return BatchGeneratePassProjectsStartResponse(**started)


@router.get(
    "/api/v1/generate-pass-projects/{job_id}",
    response_model=BatchGeneratePassProjectsStatusResponse,
)
def get_generate_pass_projects_status(job_id: str):
    """Return progress and results for a batch generation job."""
    job = batch_generation_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Batch job not found: {job_id}")

    return BatchGeneratePassProjectsStatusResponse(**job)


@router.get("/api/v1/generate-pass-projects/{job_id}/download")
def download_generate_pass_projects(job_id: str):
    """Download the final bundle zip for a completed batch generation job."""
    job = batch_generation_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Batch job not found: {job_id}")

    if job.get("status") != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Batch job {job_id} is not completed yet (status={job.get('status')}).",
        )

    bundle_path = batch_generation_service.get_final_bundle_path(job_id)
    if bundle_path is None or not bundle_path.exists():
        raise HTTPException(status_code=404, detail="Final bundle not found for this job.")

    return FileResponse(
        path=bundle_path,
        media_type="application/zip",
        filename=f"{job_id}_generated_projects.zip",
    )


@router.get(
    "/generate-pass-projects/{job_id}/analyze-metrics",
    response_model=BatchMetricsResponse,
    tags=["batch-generation"],
)
async def analyze_batch_metrics(job_id: str):
    """Run CK + MI metrics on every successfully generated pattern zip in *job_id*.

    - Returns **200** with per-pattern MI and CK summaries when complete.
    - Returns **404** if the job is not found.
    - Returns **409** if the job has not yet reached ``completed`` status.
    """
    try:
        result = await batch_metrics_service.analyze_job_metrics(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return result


@router.post("/followup", response_model=FollowUpResponse)
def followup(request: FollowUpRequest):
    """Ask a follow-up question grounded in a prior design pattern analysis."""
    if not ollama_client.is_running():
        raise HTTPException(status_code=503, detail="Ollama server is not running.")

    prompt = prompt_service.build_followup_prompt(request.analysis, request.question)
    answer = ollama_client.generate(prompt, request.model)

    return FollowUpResponse(
        model_used=request.model,
        question=request.question,
        answer=answer,
    )


@router.post("/package")
def package_project(request: PackageProjectRequest):
    """Package generated Java files into a downloadable Maven project zip."""
    if not request.files:
        raise HTTPException(status_code=400, detail="No files provided to package.")

    # Build project name from description + pattern, sanitized for use as a folder name
    raw_name = f"{request.description}-{request.pattern}"
    project_name = re.sub(r"[^\w\-]+", "-", raw_name).strip("-").lower()

    # Build the zip in memory
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Add each Java file under src/main/java/
        for f in request.files:
            path_in_zip = f"{project_name}/src/main/java/{f.filename}"
            zf.writestr(path_in_zip, f.content)

        # Add a minimal pom.xml so the project opens in any Java IDE
        pom = f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
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
        zf.writestr(f"{project_name}/pom.xml", pom)

    buffer.seek(0)
    filename = f"{project_name}.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

