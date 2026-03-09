"""
obfuscate.py

Obfuscates every Java project zip in datasets_zipped/ by:
  1. Renaming each Java class file to a generic name (Class1.java, Class2.java, ...)
  2. Replacing the revealing package path (e.g. com.iluwatar.abstractfactory) with com.example.project
  3. Updating all class name references inside every file to match the new names
  4. Writing the obfuscated zips to datasets_obfuscated/

Usage:
    python3 scripts/obfuscate.py
"""

import re
import zipfile
import io
from pathlib import Path, PurePosixPath

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_DIR = ROOT_DIR / "datasets_zipped"
OUTPUT_DIR = ROOT_DIR / "datasets_obfuscated"
OBFUSCATED_PACKAGE = "com/example/project"
OBFUSCATED_PACKAGE_DOT = "com.example.project"


def build_name_map(java_paths: list[str]) -> dict[str, str]:
    """Map each unique class stem to a generic name like Class1, Class2, ...
    Keyed by stem so the same logical class referenced across files gets the same obfuscated name.
    When two different files share a stem (rare), the second gets a unique suffix."""
    name_map: dict[str, str] = {}  # stem -> obfuscated name
    seen_obfuscated: set[str] = set()
    counter = 1
    for path in java_paths:
        stem = PurePosixPath(path).stem
        if stem not in name_map:
            candidate = f"Class{counter}"
            # Guard against unlikely collisions
            while candidate in seen_obfuscated:
                counter += 1
                candidate = f"Class{counter}"
            name_map[stem] = candidate
            seen_obfuscated.add(candidate)
            counter += 1
    return name_map


def obfuscate_content(content: str, name_map: dict[str, str], original_package: str) -> str:
    """Replace class names and package declarations inside a Java source file."""
    # Replace package declaration: e.g. "package com.iluwatar.abstractfactory;" -> "package com.example.project;"
    content = re.sub(
        r"^(package\s+)" + re.escape(original_package) + r"(\s*;)",
        rf"\g<1>{OBFUSCATED_PACKAGE_DOT}\2",
        content,
        flags=re.MULTILINE,
    )

    # Replace import statements referencing the original package
    content = re.sub(
        r"(import\s+)" + re.escape(original_package) + r"\.",
        rf"\g<1>{OBFUSCATED_PACKAGE_DOT}.",
        content,
    )

    # Replace class/interface names — longest names first to avoid partial replacements
    for original, obfuscated in sorted(name_map.items(), key=lambda x: -len(x[0])):
        # Match whole words only so e.g. "ElfKing" doesn't replace inside "ElfKingdomFactory"
        content = re.sub(rf"\b{re.escape(original)}\b", obfuscated, content)

    return content


def obfuscate_zip(zip_path: Path, output_dir: Path) -> int:
    """Obfuscate a single zip and write the result. Returns number of files processed."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        all_names = zf.namelist()

    java_files = [n for n in all_names if n.endswith(".java")]
    if not java_files:
        return 0

    # Detect the original dot-package from the first java file path
    original_package = ""
    for path in java_files:
        parts = PurePosixPath(path).parts
        if "java" in parts:
            idx = parts.index("java")
            package_parts = parts[idx + 1: -1]
            if package_parts:
                original_package = ".".join(package_parts)
                break

    name_map = build_name_map(java_files)

    buffer = io.BytesIO()
    used_paths: set[str] = set()  # track output paths to avoid duplicates

    with zipfile.ZipFile(zip_path, "r") as zf_in, \
         zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf_out:

        for entry in all_names:
            if not entry.endswith(".java"):
                continue

            original_stem = PurePosixPath(entry).stem
            obfuscated_stem = name_map.get(original_stem, original_stem)

            parts = PurePosixPath(entry).parts
            if "java" in parts:
                idx = parts.index("java")
                prefix = "/".join(parts[:idx + 1])  # e.g. src/main/java or src/test/java
                new_path = f"{prefix}/{OBFUSCATED_PACKAGE}/{obfuscated_stem}.java"
            else:
                new_path = entry

            # If this output path is already used, skip the duplicate
            if new_path in used_paths:
                continue
            used_paths.add(new_path)

            raw = zf_in.read(entry)
            try:
                content = raw.decode("utf-8", errors="ignore")
                content = obfuscate_content(content, name_map, original_package)
                zf_out.writestr(new_path, content)
            except Exception:
                zf_out.writestr(new_path, raw)

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / zip_path.name
    out_path.write_bytes(buffer.getvalue())
    return len(used_paths)


def main() -> None:
    zip_files = sorted(INPUT_DIR.glob("*.zip"))
    if not zip_files:
        print(f"No zip files found in {INPUT_DIR}")
        return

    total_files = 0
    for idx, zip_path in enumerate(zip_files, start=1):
        count = obfuscate_zip(zip_path, OUTPUT_DIR)
        print(f"[{idx}/{len(zip_files)}] {zip_path.name:50s} -> {count} files obfuscated")
        total_files += count

    print(f"\nDone. {len(zip_files)} projects obfuscated ({total_files} Java files total).")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
