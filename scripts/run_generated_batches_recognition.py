"""Run recognition endpoint against completed generated batches.

Usage:
    /path/to/venv/python scripts/run_generated_batches_recognition.py
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests

API_URL = "http://127.0.0.1:8000/analyze"
MODEL = "qwen3-coder-30b-a3b-instruct"
ROOT_DIR = Path(__file__).resolve().parent.parent
BATCHES_DIR = ROOT_DIR / "generated_batches"
OUTPUT_FILE = ROOT_DIR / "data" / "outputs" / "generated_batches_recognition_results.json"

PATTERN_ALIASES: dict[str, list[str]] = {
    "abstract-factory": ["abstract factory"],
    "builder": ["builder"],
    "factory": ["factory method", "factory"],
    "factory-method": ["factory method"],
    "factory-kit": ["factory kit", "factory"],
    "prototype": ["prototype"],
    "singleton": ["singleton"],
    "multiton": ["multiton"],
    "object-pool": ["object pool"],
    "monostate": ["monostate"],
    "adapter": ["adapter"],
    "bridge": ["bridge"],
    "composite": ["composite"],
    "decorator": ["decorator"],
    "dynamic-proxy": ["dynamic proxy", "proxy"],
    "facade": ["facade"],
    "flyweight": ["flyweight"],
    "marker-interface": ["marker interface"],
    "private-class-data": ["private class data"],
    "proxy": ["proxy"],
    "twin": ["twin"],
    "virtual-proxy": ["virtual proxy", "proxy"],
    "acyclic-visitor": ["acyclic visitor", "visitor"],
    "chain-of-responsibility": ["chain of responsibility"],
    "command": ["command"],
    "interpreter": ["interpreter"],
    "iterator": ["iterator"],
    "mediator": ["mediator"],
    "memento": ["memento"],
    "null-object": ["null object"],
    "observer": ["observer"],
    "specification": ["specification"],
    "state": ["state"],
    "strategy": ["strategy"],
    "template-method": ["template method"],
    "active-object": ["active object"],
    "actor-model": ["actor model", "actor"],
    "balking": ["balking"],
    "double-checked-locking": ["double-checked locking", "double checked locking"],
    "double-buffer": ["double buffer"],
    "guarded-suspension": ["guarded suspension"],
    "monitor": ["monitor"],
    "promise": ["promise"],
    "reactor": ["reactor"],
    "thread-pool-executor": ["thread pool", "executor"],
    "data-access-object": ["data access object", "dao"],
    "data-mapper": ["data mapper"],
    "data-transfer-object": ["data transfer object", "dto"],
    "dependency-injection": ["dependency injection"],
    "event-sourcing": ["event sourcing"],
    "identity-map": ["identity map"],
    "model-view-controller": ["model view controller", "mvc"],
    "model-view-presenter": ["model view presenter", "mvp"],
    "page-controller": ["page controller"],
    "repository": ["repository"],
    "resource-acquisition-is-initialization": ["resource acquisition is initialization", "raii"],
    "service-layer": ["service layer"],
    "service-locator": ["service locator"],
    "service-stub": ["service stub"],
    "single-table-inheritance": ["single table inheritance"],
    "table-inheritance": ["table inheritance"],
    "table-module": ["table module"],
    "transaction-script": ["transaction script"],
    "unit-of-work": ["unit of work"],
    "monad": ["monad"],
    "view-helper": ["view helper"],
    "ambassador": ["ambassador"],
    "business-delegate": ["business delegate"],
    "collection-pipeline": ["collection pipeline"],
    "combinator": ["combinator"],
    "converter": ["converter"],
    "curiously-recurring-template-pattern": ["curiously recurring template", "crtp"],
    "dirty-flag": ["dirty flag"],
    "execute-around": ["execute around"],
    "fluent-interface": ["fluent interface"],
    "function-composition": ["function composition"],
    "page-object": ["page object"],
    "role-object": ["role object"],
    "servant": ["servant"],
    "special-case": ["special case"],
    "trampoline": ["trampoline"],
    "update-method": ["update method"],
    "value-object": ["value object"],
}


def is_match(pattern: str, llm_answer: str) -> bool:
    answer = llm_answer.lower()
    aliases = PATTERN_ALIASES.get(pattern)
    if aliases:
        return any(alias in answer for alias in aliases)
    return re.sub(r"[-_]", " ", pattern).lower() in answer


def format_raw_response(raw_analysis: str) -> str:
    match = re.search(
        r"\*{0,2}Pattern(?:\s+Identified)?\*{0,2}[:：]\s*\*{0,2}(.+?)\*{0,2}$",
        raw_analysis,
        re.IGNORECASE | re.MULTILINE,
    )
    if match:
        return match.group(1).strip()

    for line in raw_analysis.splitlines():
        stripped = line.strip("*# ").strip()
        if stripped:
            return stripped

    return raw_analysis.strip()


def get_completed_jobs() -> list[tuple[str, dict]]:
    jobs: list[tuple[str, dict]] = []
    for manifest in sorted(BATCHES_DIR.glob("*/manifest.json")):
        try:
            info = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            continue
        if info.get("status") == "completed":
            jobs.append((manifest.parent.name, info))
    return jobs


def run() -> None:
    jobs = get_completed_jobs()
    if not jobs:
        print("No completed generated batches found.")
        return

    all_results = []
    for job_id, manifest in jobs:
        batch_dir = BATCHES_DIR / job_id
        zips = sorted(batch_dir.glob("*/*.zip"))
        zips = [z for z in zips if z.name != "generated_projects_bundle.zip"]

        print(f"\nBatch {job_id}: {len(zips)} patterns")
        batch_rows = []
        passed = 0

        for i, zip_path in enumerate(zips, start=1):
            pattern = zip_path.parent.name
            print(f"[{i}/{len(zips)}] {pattern} ...", end=" ", flush=True)
            try:
                with open(zip_path, "rb") as file_obj:
                    response = requests.post(
                        API_URL,
                        files={"file": (zip_path.name, file_obj, "application/zip")},
                        data={"model": MODEL},
                        timeout=420,
                    )

                if not response.ok:
                    print(f"HTTP {response.status_code}")
                    row = {
                        "pattern": pattern,
                        "llm_answer": f"ERROR: HTTP {response.status_code}",
                        "Status": "Not Pass",
                    }
                else:
                    raw = response.json().get("raw_analysis", "")
                    answer = format_raw_response(raw)
                    matched = is_match(pattern, answer)
                    row = {
                        "pattern": pattern,
                        "llm_answer": answer,
                        "Status": "Pass" if matched else "Not Pass",
                    }
                    if matched:
                        passed += 1
                    print(row["Status"])
            except requests.exceptions.Timeout:
                print("TIMEOUT")
                row = {
                    "pattern": pattern,
                    "llm_answer": "ERROR: Timeout",
                    "Status": "Not Pass",
                }
            except Exception as exc:
                print(f"ERROR: {exc}")
                row = {
                    "pattern": pattern,
                    "llm_answer": f"ERROR: {exc}",
                    "Status": "Not Pass",
                }

            batch_rows.append(row)
            time.sleep(0.3)

        total = len(zips)
        accuracy = (passed / total * 100.0) if total else 0.0
        print(f"Batch summary {job_id}: {passed}/{total} passed ({accuracy:.2f}%)")

        all_results.append(
            {
                "job_id": job_id,
                "project_title": manifest.get("project_context", ""),
                "Project title": manifest.get("project_context", ""),
                "model": manifest.get("model_used", MODEL),
                "total": total,
                "passed": passed,
                "accuracy_percent": round(accuracy, 2),
                "results": batch_rows,
            }
        )

    OUTPUT_FILE.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")

    total_all = sum(item["total"] for item in all_results)
    passed_all = sum(item["passed"] for item in all_results)
    overall = (passed_all / total_all * 100.0) if total_all else 0.0

    print(f"\nOverall: {passed_all}/{total_all} passed ({overall:.2f}%)")
    print(f"Saved: {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
