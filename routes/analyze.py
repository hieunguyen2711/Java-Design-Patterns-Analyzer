from typing import List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from config import settings
from llm.client import OllamaClient
from models.request_models import GenerateRequest
from models.response_models import AnalysisResponse, GenerateResponse
from services.analysis_service import AnalysisService
from services.file_service import FileService
from services.prompt_service import PromptService

router = APIRouter()

file_service = FileService()
ollama_client = OllamaClient()
prompt_service = PromptService()
analysis_service = AnalysisService(file_service=file_service, ollama_client=ollama_client)


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
    generated_code = ollama_client.generate(prompt, request.model)

    return GenerateResponse(
        model_used=request.model,
        pattern=request.pattern,
        description=request.description,
        generated_code=generated_code,
    )
