"""
compress_java_files.py

Iterates every Java project in the datasets/ folder, zips its src/ directory,
and writes all archives into a single output folder (datasets_zipped/).

Usage:
    python scripts/compress_java_files.py

Optional flags:
    --datasets   Path to the datasets folder   (default: datasets/)
    --output     Path to the output folder      (default: datasets_zipped/)
"""

import argparse
import zipfile
from pathlib import Path


def zip_src(project_dir: Path, output_dir: Path) -> Path | None:
    """Zip the src/ folder of a project and return the archive path, or None if no src/."""
    src_dir = project_dir / "src"
    if not src_dir.is_dir():
        return None

    archive_path = output_dir / f"{project_dir.name}.zip"

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in src_dir.rglob("*"):
            if file.is_file():
                # Store path relative to the project root so the zip contains src/...
                zf.write(file, arcname=file.relative_to(project_dir))

    return archive_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Compress src/ folders from dataset projects.")
    parser.add_argument(
        "--datasets",
        type=Path,
        default=Path("datasets"),
        help="Path to the datasets folder (default: datasets/)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("datasets_zipped"),
        help="Path to the output folder for zipped archives (default: datasets_zipped/)",
    )
    args = parser.parse_args()

    datasets_dir: Path = args.datasets.resolve()
    output_dir: Path = args.output.resolve()

    if not datasets_dir.is_dir():
        print(f"[ERROR] Datasets folder not found: {datasets_dir}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    project_dirs = sorted(p for p in datasets_dir.iterdir() if p.is_dir())

    if not project_dirs:
        print("[WARNING] No project folders found inside datasets/.")
        return

    succeeded, skipped = 0, 0

    for project in project_dirs:
        result = zip_src(project, output_dir)
        if result:
            print(f"[OK]      {project.name:40s} -> {result.name}")
            succeeded += 1
        else:
            print(f"[SKIP]    {project.name:40s}  (no src/ folder)")
            skipped += 1

    print(f"\nDone. {succeeded} zipped, {skipped} skipped.")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
