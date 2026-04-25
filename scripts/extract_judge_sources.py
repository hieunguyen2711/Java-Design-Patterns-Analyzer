"""
extract_judge_sources.py

Reads judge pairs, extracts Java sources for each side, and builds judge prompts.

Input:
  - data/reports/judge_pairs.json (preferred)
  - judge_pairs.json (fallback)

Output:
  - judge_prompts.json

Usage:
  python3 scripts/extract_judge_sources.py
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from random import Random
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from zipfile import ZipFile

RANDOM_SEED = 42
OUTPUT_FILE = Path("data/reports/judge_prompts.json")

INPUT_CANDIDATES = [
    Path("data/reports/judge_pairs.json"),
    Path("judge_pairs.json"),
]

SOURCE_LAYOUTS = [
    "data/generated_batches/{batch_name}/patterns/{pattern}/src/",
    "data/generated_batches/{batch_name}/{pattern}/src/",
    "generated_batches/{batch_name}/patterns/{pattern}/",
    "outputs/generated_batches/{batch_name}/{pattern}/src/",
]


@dataclass
class SourceBundle:
    text: str
    file_count: int
    total_chars: int


def pick_input_file() -> Path:
    for candidate in INPUT_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "Could not find judge pairs file. Tried: "
        + ", ".join(str(c) for c in INPUT_CANDIDATES)
    )


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_batch_to_job_id_map() -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    eval_file = Path("data/outputs/generated_evaluation_scores.json")
    if not eval_file.exists():
        return mapping

    data = load_json(eval_file)
    for row in data.get("rows", []):
        batch_name = row.get("batch_name")
        job_id = row.get("job_id")
        if isinstance(batch_name, str) and isinstance(job_id, str) and batch_name not in mapping:
            mapping[batch_name] = job_id

    return mapping


def project_key(project: dict) -> str:
    return f"{project.get('batch_name', '')}::{project.get('pattern', '')}"


def diagnostic_tree(path: Path, depth: int = 2, max_entries: int = 8) -> List[str]:
    lines: List[str] = []
    if not path.exists():
        return [f"- {path} [missing]"]

    lines.append(f"- {path}")

    def walk(base: Path, level: int) -> None:
        if level > depth:
            return
        try:
            entries = sorted(base.iterdir(), key=lambda p: p.name)[:max_entries]
        except Exception:
            lines.append(f"  {'  ' * level}[unreadable]")
            return

        for entry in entries:
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"  {'  ' * level}{entry.name}{suffix}")
            if entry.is_dir() and level < depth:
                walk(entry, level + 1)

    walk(path, 0)
    return lines


def verify_base_layout(pairs: Sequence[dict], batch_to_job: Dict[str, str]) -> Tuple[bool, List[str]]:
    projects: List[dict] = []
    seen = set()
    for pair in pairs:
        for side in ("project_a", "project_b"):
            proj = pair.get(side, {})
            key = project_key(proj)
            if key and key not in seen:
                projects.append(proj)
                seen.add(key)
        if len(projects) >= 6:
            break

    # Check at least one known structure resolves for at least one sample project.
    for project in projects:
        if candidate_locations(project, batch_to_job):
            return True, []

    details: List[str] = [
        "No supported source layout matched your data for sampled projects.",
        "Checked layouts:",
    ]
    details.extend([f"  - {layout}" for layout in SOURCE_LAYOUTS])
    details.append("Detected top-level structure:")
    details.extend(diagnostic_tree(Path("generated_batches"), depth=1, max_entries=12))
    details.append("Detected data/ structure:")
    details.extend(diagnostic_tree(Path("data"), depth=2, max_entries=8))

    return False, details


def candidate_locations(project: dict, batch_to_job: Dict[str, str]) -> List[Path]:
    batch_name = str(project.get("batch_name", "")).strip()
    pattern = str(project.get("pattern", "")).strip()

    cands = [
        Path(f"data/generated_batches/{batch_name}/patterns/{pattern}/src"),
        Path(f"data/generated_batches/{batch_name}/{pattern}/src"),
        Path(f"generated_batches/{batch_name}/patterns/{pattern}"),
        Path(f"outputs/generated_batches/{batch_name}/{pattern}/src"),
    ]

    # Additional compatibility for this repo: job_id-keyed generated batch directories.
    job_id = batch_to_job.get(batch_name)
    if job_id:
        cands.extend(
            [
                Path(f"generated_batches/{job_id}/{pattern}"),
                Path(f"generated_batches/{job_id}/{pattern}/{pattern}-project/src"),
                Path(f"generated_batches/{job_id}/{pattern}/src"),
            ]
        )

    return [p for p in cands if p.exists()]


def strip_package_declarations(source: str) -> str:
    return re.sub(r"^\s*package\s+[\w\.]+\s*;\s*$", "", source, flags=re.MULTILINE)


def strip_pattern_name_comments(source: str, pattern_name: str) -> str:
    pattern_name = pattern_name.lower().strip()
    pattern_variants = {pattern_name, pattern_name.replace("-", " ")}

    # Keep this conservative: only remove comment lines that explicitly contain pattern name.
    out_lines: List[str] = []
    for line in source.splitlines():
        lowered = line.lower()
        has_comment_marker = ("//" in line) or ("/*" in line) or line.strip().startswith("*")
        has_pattern_name = any(v in lowered for v in pattern_variants if v)

        if has_comment_marker and has_pattern_name:
            continue
        out_lines.append(line)

    return "\n".join(out_lines)


def read_java_from_zip(zip_path: Path, redact_pattern_comments: bool, pattern_name: str) -> SourceBundle:
    snippets: List[Tuple[str, str]] = []

    with ZipFile(zip_path, "r") as zf:
        java_members = [n for n in zf.namelist() if n.endswith(".java")]
        java_members.sort()

        for member in java_members:
            data = zf.read(member).decode("utf-8", errors="ignore")
            data = strip_package_declarations(data)
            if redact_pattern_comments:
                data = strip_pattern_name_comments(data, pattern_name)
            header = f"// === {Path(member).name} ==="
            snippets.append((member, f"{header}\n{data.strip()}\n"))

    combined = "\n".join(text for _, text in snippets).strip()
    return SourceBundle(text=combined, file_count=len(snippets), total_chars=len(combined))


def read_java_from_dir(src_dir: Path, redact_pattern_comments: bool, pattern_name: str) -> Optional[SourceBundle]:
    files = sorted([p for p in src_dir.rglob("*.java") if p.is_file()], key=lambda p: p.name.lower())
    if not files:
        return None

    snippets: List[str] = []
    for file_path in files:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        content = strip_package_declarations(content)
        if redact_pattern_comments:
            content = strip_pattern_name_comments(content, pattern_name)
        header = f"// === {file_path.name} ==="
        snippets.append(f"{header}\n{content.strip()}\n")

    combined = "\n".join(snippets).strip()
    return SourceBundle(text=combined, file_count=len(files), total_chars=len(combined))


def extract_project_source(project: dict, category: str, batch_to_job: Dict[str, str]) -> Optional[SourceBundle]:
    pattern_name = str(project.get("pattern", ""))
    redact = category == "cqs_validation"

    for location in candidate_locations(project, batch_to_job):
        if location.is_file() and location.suffix.lower() == ".zip":
            bundle = read_java_from_zip(location, redact_pattern_comments=redact, pattern_name=pattern_name)
            if bundle.file_count > 0:
                return bundle
            continue

        if location.is_dir():
            # Prefer direct Java extraction from directory tree.
            bundle = read_java_from_dir(location, redact_pattern_comments=redact, pattern_name=pattern_name)
            if bundle and bundle.file_count > 0:
                return bundle

            # Fallback to any zip in that directory.
            zip_files = sorted(location.glob("*.zip"))
            for zf in zip_files:
                zbundle = read_java_from_zip(zf, redact_pattern_comments=redact, pattern_name=pattern_name)
                if zbundle.file_count > 0:
                    return zbundle

    return None


def cqs_prompt(source_a: str, source_b: str) -> str:
    return (
        "You are a senior Java developer evaluating code quality.\n\n"
        "Below are two Java projects labeled A and B. Based SOLELY on code quality - "
        "maintainability, readability, class cohesion, coupling between classes, naming conventions, "
        "and structural soundness - which project has better code quality?\n\n"
        "Do NOT consider what the code is supposed to do or what design pattern it implements. "
        "Only evaluate how well the code is written.\n\n"
        "Respond with ONLY a single JSON object, no other text:\n"
        "{\"winner\": \"A\" or \"B\", \"confidence\": \"high\" or \"medium\" or \"low\", "
        "\"reason\": \"one sentence explaining why\"}\n\n"
        "=== PROJECT A ===\n"
        f"{source_a}\n\n"
        "=== PROJECT B ===\n"
        f"{source_b}"
    )


def compqs_prompt(pattern_a: str, pattern_b: str, source_a: str, source_b: str) -> str:
    return (
        "You are a senior Java developer evaluating design pattern implementations.\n\n"
        f"Project A is intended to implement the {pattern_a} design pattern.\n"
        f"Project B is intended to implement the {pattern_b} design pattern.\n\n"
        "Evaluate both projects on:\n"
        "1. Code quality (maintainability, readability, cohesion, coupling)\n"
        "2. Pattern correctness (does each project properly implement its intended design pattern's structural properties?)\n\n"
        "Which project is the better overall implementation considering BOTH code quality and pattern correctness?\n\n"
        "Respond with ONLY a single JSON object, no other text:\n"
        "{\"winner\": \"A\" or \"B\", \"confidence\": \"high\" or \"medium\" or \"low\", "
        "\"reason\": \"one sentence explaining why\"}\n\n"
        f"=== PROJECT A ({pattern_a}) ===\n"
        f"{source_a}\n\n"
        f"=== PROJECT B ({pattern_b}) ===\n"
        f"{source_b}"
    )


def domain_prompt(pattern_name: str, source_a: str, source_b: str) -> str:
    return (
        "You are a senior Java developer evaluating design pattern implementations.\n\n"
        f"Both projects below are intended to implement the {pattern_name} design pattern, but in different application domains.\n\n"
        "Evaluate both on:\n"
        "1. Code quality (maintainability, readability, cohesion, coupling)\n"
        f"2. Pattern correctness (does it properly implement the {pattern_name} pattern's structural properties?)\n\n"
        f"Which project is the better {pattern_name} implementation overall?\n\n"
        "Respond with ONLY a single JSON object, no other text:\n"
        "{\"winner\": \"A\" or \"B\", \"confidence\": \"high\" or \"medium\" or \"low\", "
        "\"reason\": \"one sentence explaining why\"}\n\n"
        "=== PROJECT A ===\n"
        f"{source_a}\n\n"
        "=== PROJECT B ===\n"
        f"{source_b}"
    )


def choose_presentation(pair: dict, rng: Random) -> Tuple[dict, dict]:
    pa = dict(pair.get("project_a", {}))
    pb = dict(pair.get("project_b", {}))

    # If explicit presentation_order exists, respect saved A/B assignment.
    if pair.get("presentation_order") is not None:
        return pa, pb

    return (pa, pb) if rng.random() < 0.5 else (pb, pa)


def expected_winner_from_scores(project_a: dict, project_b: dict, metric_used: str) -> str:
    a_score = float(project_a.get(metric_used, 0.0))
    b_score = float(project_b.get(metric_used, 0.0))
    return "A" if a_score >= b_score else "B"


def pair_output_record(
    pair: dict,
    project_a: dict,
    project_b: dict,
    prompt: str,
    src_a: SourceBundle,
    src_b: SourceBundle,
) -> dict:
    metric_used = pair.get("metric_used", "compqs_score")
    metric_gap = abs(float(project_a.get(metric_used, 0.0)) - float(project_b.get(metric_used, 0.0)))

    return {
        "pair_id": pair.get("pair_id"),
        "category": pair.get("category"),
        "prompt": prompt,
        "project_a_identity": {
            "pattern": project_a.get("pattern"),
            "project_context": project_a.get("project_context"),
            "batch_name": project_a.get("batch_name"),
            "cqs_score": project_a.get("cqs_score"),
            "compqs_score": project_a.get("compqs_score"),
        },
        "project_b_identity": {
            "pattern": project_b.get("pattern"),
            "project_context": project_b.get("project_context"),
            "batch_name": project_b.get("batch_name"),
            "cqs_score": project_b.get("cqs_score"),
            "compqs_score": project_b.get("compqs_score"),
        },
        "expected_winner": expected_winner_from_scores(project_a, project_b, metric_used),
        "metric_used": metric_used,
        "metric_gap": round(metric_gap, 2),
        "files_found_a": src_a.file_count,
        "files_found_b": src_b.file_count,
        "total_chars_a": src_a.total_chars,
        "total_chars_b": src_b.total_chars,
    }


def main() -> None:
    input_file = pick_input_file()
    data = load_json(input_file)
    pairs = data.get("pairs", [])

    if not pairs:
        print("ERROR: No pairs found in input judge_pairs file.")
        return

    batch_to_job = build_batch_to_job_id_map()

    ok_layout, details = verify_base_layout(pairs, batch_to_job)
    if not ok_layout:
        print("ERROR: Could not verify expected source layout.")
        for line in details:
            print(line)
        print("Please correct source paths and rerun.")
        return

    rng = Random(RANDOM_SEED)
    out_pairs: List[dict] = []
    skipped: List[dict] = []

    for pair in pairs:
        category = str(pair.get("category", "")).strip()
        if category not in {"cqs_validation", "compqs_validation", "domain_sensitivity"}:
            skipped.append(
                {
                    "pair_id": pair.get("pair_id"),
                    "reason": f"Unsupported category: {category}",
                }
            )
            continue

        project_a, project_b = choose_presentation(pair, rng)

        src_a = extract_project_source(project_a, category, batch_to_job)
        src_b = extract_project_source(project_b, category, batch_to_job)

        if src_a is None or src_b is None or src_a.file_count == 0 or src_b.file_count == 0:
            skipped.append(
                {
                    "pair_id": pair.get("pair_id"),
                    "reason": "Missing source directory or no .java files found for one or both projects.",
                    "project_a": {
                        "batch_name": project_a.get("batch_name"),
                        "pattern": project_a.get("pattern"),
                    },
                    "project_b": {
                        "batch_name": project_b.get("batch_name"),
                        "pattern": project_b.get("pattern"),
                    },
                }
            )
            print(
                "WARNING: Skipping pair"
                f" {pair.get('pair_id')} due to missing Java sources "
                f"({project_a.get('batch_name')}::{project_a.get('pattern')} vs "
                f"{project_b.get('batch_name')}::{project_b.get('pattern')})"
            )
            continue

        if category == "cqs_validation":
            prompt = cqs_prompt(src_a.text, src_b.text)
        elif category == "compqs_validation":
            prompt = compqs_prompt(
                str(project_a.get("pattern", "")),
                str(project_b.get("pattern", "")),
                src_a.text,
                src_b.text,
            )
        else:
            # domain_sensitivity
            pattern_name = str(project_a.get("pattern", ""))
            prompt = domain_prompt(pattern_name, src_a.text, src_b.text)

        out_pairs.append(pair_output_record(pair, project_a, project_b, prompt, src_a, src_b))

    avg_chars = 0.0
    if out_pairs:
        avg_chars = sum(p["total_chars_a"] + p["total_chars_b"] for p in out_pairs) / len(out_pairs)

    output = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_pairs": len(out_pairs),
            "source_base_path": "data/generated_batches/",
            "input_pairs_file": str(input_file),
            "random_seed": RANDOM_SEED,
            "skipped_pairs": len(skipped),
            "average_total_chars_per_pair": round(avg_chars, 2),
        },
        "pairs": out_pairs,
        "skipped": skipped,
    }

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print("=" * 70)
    print("JUDGE PROMPT EXTRACTION SUMMARY")
    print("=" * 70)
    print(f"Input pairs file: {input_file}")
    print(f"Output file: {OUTPUT_FILE}")
    print(f"Pairs requested: {len(pairs)}")
    print(f"Pairs generated: {len(out_pairs)}")
    print(f"Pairs skipped: {len(skipped)}")
    print(f"Average chars per generated pair: {avg_chars:.1f}")


if __name__ == "__main__":
    main()
