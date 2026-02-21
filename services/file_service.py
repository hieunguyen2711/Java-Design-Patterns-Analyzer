import os
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Dict

from fastapi import HTTPException

from config import settings


class FileService:
    """Handle file upload, extraction, traversal, and cleanup operations."""

    def save_upload(self, file_bytes: bytes, filename: str) -> str:
        """Save an uploaded file to the configured upload directory with a unique name."""
        upload_dir = Path(settings.UPLOAD_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)
        unique_name = f"{uuid.uuid4().hex}_{filename}"
        file_path = upload_dir / unique_name
        file_path.write_bytes(file_bytes)
        return str(file_path)

    def extract_zip(self, zip_path: str) -> str:
        """Extract a zip archive to a dedicated folder and return its path."""
        if not zipfile.is_zipfile(zip_path):
            raise HTTPException(status_code=400, detail="Uploaded file is not a valid zip archive.")

        extract_path = f"{zip_path}_extracted"
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_path)
        return extract_path

    def walk_java_files(self, root_dir: str) -> Dict[str, str]:
        """Recursively read Java files, skipping configured directories, and return their contents."""
        java_files: Dict[str, str] = {}
        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in dirnames if d not in settings.SKIP_DIRS]
            for filename in filenames:
                if not filename.endswith(".java"):
                    continue
                full_path = os.path.join(dirpath, filename)
                relative_path = Path(os.path.relpath(full_path, start=root_dir)).as_posix()
                with open(full_path, "r", encoding="utf-8", errors="ignore") as file:
                    content = file.read()
                cleaned_content = self._compress_blank_lines(content)
                java_files[relative_path] = cleaned_content
        return java_files

    def build_folder_tree(self, java_files: Dict[str, str]) -> dict:
        """Convert flat Java file paths into a nested folder tree representation."""
        tree: dict = {}
        for path in java_files.keys():
            parts = path.split("/")
            current = tree
            for part in parts[:-1]:
                current = current.setdefault(part, {})
            current[parts[-1]] = None
        return tree

    def cleanup(self, *paths: str) -> None:
        """Delete files or directories, ignoring missing paths."""
        for path in paths:
            if not path:
                continue
            if os.path.isfile(path):
                try:
                    os.remove(path)
                except OSError:
                    continue
            elif os.path.isdir(path):
                try:
                    shutil.rmtree(path)
                except OSError:
                    continue

    @staticmethod
    def _compress_blank_lines(content: str) -> str:
        """Reduce consecutive blank lines to a maximum of two."""
        lines = content.splitlines()
        compressed: list[str] = []
        blank_count = 0
        for line in lines:
            if line.strip() == "":
                blank_count += 1
                if blank_count > 2:
                    continue
            else:
                blank_count = 0
            compressed.append(line)
        return "\n".join(compressed)
