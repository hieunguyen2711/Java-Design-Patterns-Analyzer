"""
FastAPI router for the CK + Maintainability Index analysis endpoint.

POST /api/v1/analyze-metrics      — accepts a ZIP upload of Java source files
POST /api/v1/analyze-metrics-dir  — accepts a JSON body with a local directory path
"""

import os

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from models.metrics import AnalyzeMetricsRequest, AnalyzeMetricsResponse
from services.analysis_pipeline import analyze_project_async
from services.file_service import FileService

router = APIRouter(prefix="/api/v1", tags=["metrics"])

file_service = FileService()


@router.post("/analyze-metrics", response_model=AnalyzeMetricsResponse)
async def analyze_metrics_zip(
    file: UploadFile = File(...),
    pattern_name: str = Form(""),
):
    """Upload a ZIP of Java source files and run CK + MI metrics.

    - **MI** is always computed (pure Python, no external deps).
    - **CK** is computed when Java + CK JAR are available; otherwise
      the response contains MI-only data with CK fields set to ``null``.
    """

    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted.")

    saved_path = None
    extracted_path = None
    try:
        contents = await file.read()
        saved_path = file_service.save_upload(contents, file.filename)
        extracted_path = file_service.extract_zip(saved_path)

        # Verify extracted directory contains at least one .java file
        java_files: list[str] = []
        for root, _, files in os.walk(extracted_path):
            java_files.extend(f for f in files if f.endswith(".java"))
        if not java_files:
            raise HTTPException(
                status_code=422,
                detail="No .java files found in the uploaded ZIP",
            )

        result = await analyze_project_async(extracted_path, pattern_name)
        return AnalyzeMetricsResponse(**result)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        file_service.cleanup(saved_path, extracted_path)


@router.post("/analyze-metrics-dir", response_model=AnalyzeMetricsResponse)
async def analyze_metrics_dir(req: AnalyzeMetricsRequest):
    """Run CK + MI metrics on Java source files in an existing local directory."""

    if not os.path.isdir(req.project_dir):
        raise HTTPException(
            status_code=400,
            detail=f"Directory not found: {req.project_dir}",
        )

    java_files: list[str] = []
    for root, _, files in os.walk(req.project_dir):
        java_files.extend(f for f in files if f.endswith(".java"))
    if not java_files:
        raise HTTPException(
            status_code=422,
            detail="No .java files found in project directory",
        )

    try:
        result = await analyze_project_async(req.project_dir, req.pattern_name)
        return AnalyzeMetricsResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
