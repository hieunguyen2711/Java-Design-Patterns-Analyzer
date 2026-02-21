from fastapi import HTTPException

from config import settings


def validate_files(java_files: dict) -> None:
    """Validate provided Java files before analysis."""
    if not java_files:
        raise HTTPException(status_code=400, detail="No Java files were provided.")
    if len(java_files) > settings.MAX_JAVA_FILES:
        raise HTTPException(
            status_code=400,
            detail="Too many files. Please upload only the src/ folder of your project.",
        )
