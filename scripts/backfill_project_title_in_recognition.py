import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

manifest_by_job = {}
for manifest_path in (ROOT / "generated_batches").glob("*/manifest.json"):
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        continue
    job_id = manifest.get("job_id")
    if job_id:
        manifest_by_job[job_id] = manifest


def backfill(path: Path) -> None:
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    for batch in data:
        job = manifest_by_job.get(batch.get("job_id"), {})
        title = job.get("project_context", "")
        batch["project_title"] = title
        batch["Project title"] = title
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


backfill(ROOT / "generated_batches_recognition_results.json")
backfill(ROOT / "recognizer_correctness_only.json")
print("Backfilled project_title in recognition JSON files.")
