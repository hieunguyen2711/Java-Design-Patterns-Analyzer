#!/usr/bin/env python3
"""
compile_check_logprobs.py -- Stage A (sibling of score_piqs_logprobs.py): does
each generated project actually COMPILE? Emits a per-unit CSV keyed by unit_id.

This is a SEPARATE, harder correctness check than PIQS: PIQS is static pattern
analysis of source; this one hands every .java file of a unit to `javac` and
records whether the project builds. It runs over the run_generation_logprobs.py
output layout, exactly like the PIQS scorer:

    <output-dir>/<model-tag>/seed_<seed>/<pattern>/<context>/rep<n>/{*.java, unit.json}

For each unit it compiles ALL of the unit's .java files together in one javac
invocation (so cross-file references within the project resolve regardless of
the flat on-disk layout -- package declarations are fine), into a throwaway
output dir, and records pass/fail + the first javac error. The generated dirs
are never modified (.class files go to a temp dir).

The output CSV is join-ready and consumed by analyze_logprob_separation.py via
--piqs-results, with NO --threshold (the value is already pass/fail):

    python generation/compile_check_logprobs.py \
        --output-dir generated_logprobs_vertex_pro \
        --out compiles_gemini_pro.csv
    python generation/analyze_logprob_separation.py \
        --output-dir generated_logprobs_vertex_pro \
        --piqs-results compiles_gemini_pro.csv

Run ONE per model (logprob scales are not comparable across models/tokenizers).

Only the JDK is required (`javac` on PATH). No third-party Python deps.

Column-name note: the pass/fail column is "passed" (values "pass"/"fail"), which
is what analyze_logprob_separation.py auto-detects. The generation status is kept
as "gen_status" (NOT "status") so it does not hijack the analyzer's value-field
auto-detection, exactly like score_piqs_logprobs.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

# "passed" is the analyzer's value column (pass/fail). "gen_status" is the
# generation status, deliberately NOT named "status" (see module docstring).
FIELDNAMES = ["unit_id", "pattern", "gen_status", "num_files", "passed",
              "javac_returncode", "error_count", "first_error", "error"]


def _javac_error_summary(stderr: str) -> tuple[int, str]:
    """(error_count, first_error_line) parsed from javac stderr. javac prints one
    '...: error: ...' line per error (warnings say 'warning:', the trailing tally
    says 'N errors' without a colon), so counting 'error:' is the error count."""
    lines = stderr.splitlines()
    err_lines = [ln.strip() for ln in lines if "error:" in ln]
    first = err_lines[0][:300] if err_lines else ""
    return len(err_lines), first


def compile_unit(unit_json: Path, release: Optional[str], timeout: int) -> dict:
    """Compile one unit dir. NEVER raises -- problems land in the 'error' column.
    Mirrors score_piqs_logprobs.score_unit's contract so the two CSVs line up."""
    unit_dir = unit_json.parent
    row = {k: "" for k in FIELDNAMES}
    try:
        rec = json.loads(unit_json.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        row["error"] = f"bad unit.json: {exc}"
        return row

    row["unit_id"] = rec.get("unit_id", "")
    row["pattern"] = rec.get("pattern", "")
    row["gen_status"] = rec.get("status", "")

    if rec.get("status") != "ok":
        # failed / parse_failed units have no usable .java -- leave 'passed' blank
        # so the analyzer treats them as "not compared" (same population as PIQS).
        row["error"] = f"skipped: generation status={rec.get('status')!r}"
        return row

    java_files = sorted(unit_dir.glob("*.java"))
    row["num_files"] = len(java_files)
    if not java_files:
        row["error"] = "no .java files in unit dir"
        return row

    with tempfile.TemporaryDirectory(prefix="javac_") as tmp:
        cmd = ["javac", "-d", tmp]
        if release:
            cmd += ["--release", str(release)]
        cmd += [str(p) for p in java_files]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            row["passed"] = "fail"
            row["error"] = f"javac timeout after {timeout}s"
            return row
        except FileNotFoundError:
            row["error"] = "javac not found on PATH"
            return row

    row["javac_returncode"] = proc.returncode
    if proc.returncode == 0:
        row["passed"] = "pass"
    else:
        row["passed"] = "fail"
        n_err, first = _javac_error_summary(proc.stderr)
        row["error_count"] = n_err
        row["first_error"] = first
    return row


def summarize(rows: list, out_path: Path) -> None:
    checked = [r for r in rows if r["passed"] in ("pass", "fail")]
    passed = [r for r in checked if r["passed"] == "pass"]
    errored = [r for r in rows if r["error"] and r["passed"] == ""]
    print(f"\nWrote {out_path}")
    print(f"  units seen        : {len(rows)}")
    print(f"  units compiled    : {len(checked)}")
    if errored:
        print(f"  units skipped     : {len(errored)} (non-ok generation / no source; see 'error')")
    if not checked:
        print("  !! nothing compiled -- check --output-dir points at a generated tree.")
        return

    n, p = len(checked), len(passed)
    print("\nCompile results:")
    print(f"  compiles PASS : {p}")
    print(f"  compiles FAIL : {n - p}")
    print(f"  pass rate     : {100.0 * p / n:.1f}%  ({p}/{n})")

    # Per-pattern breakdown -- where do the failures cluster?
    by_pat: dict = {}
    for r in checked:
        pat = r["pattern"] or "?"
        agg = by_pat.setdefault(pat, [0, 0])
        agg[0] += 1
        agg[1] += 1 if r["passed"] == "pass" else 0
    print("\n  by pattern (pass/total):")
    for pat in sorted(by_pat):
        tot, ok = by_pat[pat]
        print(f"    {pat:<18} {ok:>3}/{tot:<3}")

    print("\nNext (NO --threshold needed; the value is already pass/fail):")
    print("  python generation/analyze_logprob_separation.py "
          f"--output-dir <same dir> --piqs-results {out_path}")


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="javac-compile a logprob-pilot output tree into a unit_id-keyed pass/fail CSV.")
    ap.add_argument("--output-dir", required=True,
                    help="A model's output tree (searched recursively for unit.json). Check ONE model per run.")
    ap.add_argument("--out", default=None,
                    help="Output CSV path. Default: compiles_<output-dir-basename>.csv in the CWD.")
    ap.add_argument("--release", default=None,
                    help="Optional javac --release level (e.g. 17). Default: the JDK's own default.")
    ap.add_argument("--timeout", type=int, default=60, help="Per-unit javac timeout in seconds (default 60).")
    ap.add_argument("--jobs", type=int, default=min(8, (os.cpu_count() or 4)),
                    help="Parallel javac workers (default: min(8, cpu count)). Each unit compiles in its own temp dir.")
    ap.add_argument("--limit", type=int, default=None, help="Compile at most N units (smoke test).")
    args = ap.parse_args(argv)

    if shutil.which("javac") is None:
        raise SystemExit("javac not found on PATH. Install a JDK (e.g. Temurin 17/21) and retry.")

    out_dir = Path(args.output_dir)
    if not out_dir.exists():
        raise SystemExit(f"--output-dir not found: {out_dir}")
    out_path = Path(args.out) if args.out else Path(f"compiles_{out_dir.name}.csv")

    unit_jsons = sorted(out_dir.rglob("unit.json"))
    if args.limit is not None:
        unit_jsons = unit_jsons[:args.limit]
    if not unit_jsons:
        raise SystemExit(f"No unit.json found under {out_dir}.")

    jobs = max(1, args.jobs)
    if jobs == 1:
        rows = [compile_unit(uj, args.release, args.timeout) for uj in unit_jsons]
    else:
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            rows = list(ex.map(lambda uj: compile_unit(uj, args.release, args.timeout), unit_jsons))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    summarize(rows, out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
