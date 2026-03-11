"""
Feed every ZIP in datasets_obfuscated/ to the /api/v1/analyze-metrics
endpoint and save the collected scores to a JSON file.

Run with:
    python3 scripts/test_obfuscated_metrics.py

Requires the FastAPI server to be running (uvicorn main:app --reload).
"""

import json
import time
from pathlib import Path

import requests

API_URL = "http://localhost:8000/api/v1/analyze-metrics"
ROOT_DIR = Path(__file__).resolve().parent.parent
ZIPPED_DIR = ROOT_DIR / "datasets_obfuscated"
OUTPUT_FILE = ROOT_DIR / "obfuscated_metrics_results.json"


def main():
    zip_files = sorted(ZIPPED_DIR.glob("*.zip"))
    if not zip_files:
        print("No zip files found in", ZIPPED_DIR)
        return

    results = []
    for idx, zip_path in enumerate(zip_files, start=1):
        stem = zip_path.stem
        print(f"[{idx}/{len(zip_files)}] {stem} ...", end=" ", flush=True)

        try:
            with open(zip_path, "rb") as f:
                response = requests.post(
                    API_URL,
                    files={"file": (zip_path.name, f, "application/zip")},
                    data={"pattern_name": stem},
                    timeout=120,
                )

            if not response.ok:
                print(f"HTTP {response.status_code}")
                results.append({
                    "pattern": stem,
                    "status": f"ERROR: HTTP {response.status_code}",
                    "avg_mi_score": None,
                    "mi_distribution": None,
                    "ck_overall_score": None,
                })
                continue

            data = response.json()
            summary = data.get("summary", {})

            avg_mi = summary.get("avg_mi_score")
            mi_dist = summary.get("mi_distribution", {})
            ck_score = summary.get("ck_overall_score")

            print(f"MI={avg_mi}  CK={ck_score:.1f}" if ck_score else f"MI={avg_mi}  CK=N/A")

            results.append({
                "pattern": stem,
                "status": "OK",
                "total_files": summary.get("total_files"),
                "total_classes": summary.get("total_classes"),
                "avg_mi_score": avg_mi,
                "min_mi_score": summary.get("min_mi_score"),
                "max_mi_score": summary.get("max_mi_score"),
                "mi_distribution": mi_dist,
                "ck_overall_score": round(ck_score, 2) if ck_score is not None else None,
                "avg_wmc": summary.get("avg_wmc"),
                "avg_cbo": summary.get("avg_cbo"),
                "avg_lcom_star": summary.get("avg_lcom_star"),
                "avg_rfc": summary.get("avg_rfc"),
                "avg_dit": summary.get("avg_dit"),
                "avg_halstead_volume": summary.get("avg_halstead_volume"),
                "avg_sloc": summary.get("avg_sloc"),
                "total_estimated_bugs": summary.get("total_estimated_bugs"),
            })

        except requests.exceptions.Timeout:
            print("TIMEOUT")
            results.append({
                "pattern": stem,
                "status": "ERROR: Timeout",
                "avg_mi_score": None,
                "mi_distribution": None,
                "ck_overall_score": None,
            })
        except Exception as e:
            print(f"Error: {e}")
            results.append({
                "pattern": stem,
                "status": f"ERROR: {e}",
                "avg_mi_score": None,
                "mi_distribution": None,
                "ck_overall_score": None,
            })

        time.sleep(0.5)

    # Write results
    OUTPUT_FILE.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    # Print summary
    ok = [r for r in results if r["status"] == "OK"]
    mi_scores = [r["avg_mi_score"] for r in ok if r["avg_mi_score"] is not None]
    ck_scores = [r["ck_overall_score"] for r in ok if r["ck_overall_score"] is not None]

    print(f"\n{'='*60}")
    print(f"Done. {len(ok)}/{len(results)} succeeded.")
    if mi_scores:
        print(f"MI  — avg: {sum(mi_scores)/len(mi_scores):.1f}, "
              f"min: {min(mi_scores):.1f}, max: {max(mi_scores):.1f}")
    if ck_scores:
        print(f"CK  — avg: {sum(ck_scores)/len(ck_scores):.1f}, "
              f"min: {min(ck_scores):.1f}, max: {max(ck_scores):.1f}")
    print(f"Results saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
