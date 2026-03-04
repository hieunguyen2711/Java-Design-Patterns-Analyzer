"""
successful_files.py

Reads results.json, filters all entries with Status "Pass",
and writes them to pass.json.
"""

import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
RESULTS_FILE = ROOT_DIR / "results.json"
OUTPUT_FILE = ROOT_DIR / "pass.json"


def main() -> None:
    if not RESULTS_FILE.exists():
        print(f"results.json not found at {RESULTS_FILE}")
        return

    results = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))

    passing = [entry for entry in results if entry.get("Status") == "Pass"]

    OUTPUT_FILE.write_text(json.dumps(passing, indent=2, ensure_ascii=False))

    print(f"{len(passing)}/{len(results)} patterns passed.")
    print(f"Written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
