#!/usr/bin/env python3
"""
analyze_logprob_separation.py -- post-hoc pass/fail confidence separation report.

Run this AFTER run_generation_logprobs.py has produced a pilot output dir AND
after you have scored those units with YOUR existing PIQS scorer. This script
does NOT generate anything and does NOT import or run PIQS -- scoring stays a
separate step you own, so the two concerns stay decoupled.

What it does
------------
* Reads each unit.json in the pilot --output-dir for its summary confidence
  numbers (mean_logprob, min_logprob, min_logprob_critical).
* Maps each unit_id to a PIQS pass/fail using a --piqs-results file YOU provide.
* Splits the generations into the PIQS-pass pile and the PIQS-fail pile.
* For each of the three numbers, prints n / mean / median in each pile and the
  pass-minus-fail difference, so you can eyeball whether the fail pile is less
  confident than the pass pile.
* Prints the pass/fail COUNTS first and warns LOUDLY if either pile is empty
  (then the separation check is meaningless and you need more/harder cells).

This is the "is this worth researching?" check -- nothing more.

--piqs-results formats (auto-detected)
--------------------------------------
  JSON dict :  {"<unit_id>": "pass" | "fail" | true | false | <score>, ...}
  JSON list :  [{"unit_id": "...", "status": "pass"}, ...]
               (value field may be status / passed / pass / result / piqs / score / label)
  CSV       :  header row with a unit_id column and a status/score column.

If the mapped value is a numeric SCORE, pass --threshold T; then pass := score >= T.

Stdlib only (json, csv, statistics, argparse) -- no new dependencies.

    python analyze_logprob_separation.py \
        --output-dir generated_logprobs_qwen25_7b \
        --piqs-results piqs_results.csv
    # numeric PIQS scores instead of pass/fail labels:
    python analyze_logprob_separation.py \
        --output-dir generated_logprobs_qwen25_7b \
        --piqs-results piqs_scores.json --threshold 0.8
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

METRICS = ("mean_logprob", "min_logprob", "min_logprob_critical")

# Field names we will accept for the unit id and the pass/fail (or score) value.
_ID_FIELDS = ("unit_id", "id", "unit", "uid")
_VALUE_FIELDS = ("status", "passed", "pass", "result", "piqs", "score", "label", "verdict")

_TRUE_WORDS = {"pass", "passed", "true", "yes", "y", "ok", "1", "correct"}
_FALSE_WORDS = {"fail", "failed", "false", "no", "n", "0", "incorrect"}


# --------------------------------------------------------------------------- #
# PIQS results -> {unit_id: is_pass}                                           #
# --------------------------------------------------------------------------- #
def as_pass(value, threshold: Optional[float], warnings: list) -> Optional[bool]:
    """Interpret one PIQS result value as pass (True) / fail (False) / unknown.

    bool -> itself. Recognized word -> that. Numeric -> compared to --threshold
    (>= is pass); with no threshold, 1/0 (and other nonzero/zero) fall back to
    truthiness and a warning is recorded so the ambiguity is visible."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if threshold is not None:
            return float(value) >= threshold
        if value in (0, 1):
            return bool(value)
        warnings.append(f"numeric PIQS value {value!r} seen but no --threshold given; "
                        f"treated as {'pass' if value else 'fail'} by truthiness")
        return bool(value)
    s = str(value).strip().lower()
    if s in _TRUE_WORDS:
        return True
    if s in _FALSE_WORDS:
        return False
    try:
        num = float(s)
    except ValueError:
        warnings.append(f"unrecognized PIQS value {value!r} (skipped)")
        return None
    if threshold is not None:
        return num >= threshold
    warnings.append(f"numeric PIQS value {value!r} seen but no --threshold given; "
                    f"treated as {'pass' if num else 'fail'} by truthiness")
    return bool(num)


def _pick(row: dict, fields) -> Optional[str]:
    for f in fields:
        if f in row and str(row[f]).strip() != "":
            return f
    return None


def load_piqs_results(path: Path, threshold: Optional[float], warnings: list) -> dict:
    """Return {unit_id: is_pass}. Accepts JSON dict, JSON list, or CSV."""
    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()
    is_json = path.suffix.lower() == ".json" or (
        path.suffix.lower() != ".csv" and stripped[:1] in "{["
    )
    out: dict = {}
    if is_json:
        data = json.loads(text)
        if isinstance(data, dict):
            for uid, val in data.items():
                p = as_pass(val, threshold, warnings)
                if p is not None:
                    out[str(uid)] = p
        elif isinstance(data, list):
            for row in data:
                if not isinstance(row, dict):
                    continue
                id_field = _pick(row, _ID_FIELDS)
                val_field = _pick(row, _VALUE_FIELDS)
                if not id_field or not val_field:
                    continue
                p = as_pass(row[val_field], threshold, warnings)
                if p is not None:
                    out[str(row[id_field]).strip()] = p
        else:
            raise SystemExit(f"--piqs-results JSON must be an object or array: {path}")
    else:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise SystemExit(f"--piqs-results CSV has no header row: {path}")
        id_field = _pick({k: k for k in reader.fieldnames}, _ID_FIELDS)
        val_field = _pick({k: k for k in reader.fieldnames}, _VALUE_FIELDS)
        if not id_field or not val_field:
            raise SystemExit(
                f"--piqs-results CSV needs a unit-id column ({'/'.join(_ID_FIELDS)}) and a "
                f"value column ({'/'.join(_VALUE_FIELDS)}); got {reader.fieldnames}")
        for row in reader:
            uid = str(row.get(id_field, "")).strip()
            if not uid:
                continue
            p = as_pass(row.get(val_field, ""), threshold, warnings)
            if p is not None:
                out[uid] = p
    return out


# --------------------------------------------------------------------------- #
# Output dir -> {unit_id: summary}                                             #
# --------------------------------------------------------------------------- #
def load_unit_summaries(output_dir: Path) -> dict:
    """Walk output_dir for unit.json files and return {unit_id: summary dict}."""
    summaries: dict = {}
    for uj in sorted(output_dir.rglob("unit.json")):
        try:
            rec = json.loads(uj.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        uid = rec.get("unit_id")
        if not uid:
            continue
        summaries[str(uid)] = {
            "status": rec.get("status"),
            "mean_logprob": rec.get("mean_logprob"),
            "min_logprob": rec.get("min_logprob"),
            "min_logprob_critical": rec.get("min_logprob_critical"),
        }
    return summaries


# --------------------------------------------------------------------------- #
# Reporting                                                                    #
# --------------------------------------------------------------------------- #
def _stats(pile: list, key: str):
    """(n, mean, median) over the non-null values of `key` in `pile`."""
    vals = [s[key] for s in pile if s.get(key) is not None]
    if not vals:
        return 0, None, None
    return len(vals), statistics.mean(vals), statistics.median(vals)


def _fmt(x) -> str:
    return "   n/a" if x is None else f"{x:8.4f}"


def build_report_data(pass_pile: list, fail_pile: list, warnings: list,
                      n_unscored: int, missing_ids: list, meta: dict) -> dict:
    """Assemble the full report as a plain dict (printed AND, optionally, saved)."""
    n_pass, n_fail = len(pass_pile), len(fail_pile)
    empty = n_pass == 0 or n_fail == 0
    metrics: dict = {}
    if not empty:
        for key in METRICS:
            pn, pmean, pmed = _stats(pass_pile, key)
            fn, fmean, fmed = _stats(fail_pile, key)
            dmean = (pmean - fmean) if (pmean is not None and fmean is not None) else None
            dmed = (pmed - fmed) if (pmed is not None and fmed is not None) else None
            metrics[key] = {
                "pass": {"n": pn, "mean": pmean, "median": pmed},
                "fail": {"n": fn, "mean": fmean, "median": fmed},
                "diff": {"mean": dmean, "median": dmed},
            }
    return {
        "meta": meta,
        "counts": {
            "pass": n_pass,
            "fail": n_fail,
            "unscored": n_unscored,
            "missing_from_output_dir": len(missing_ids),
            "missing_ids_example": missing_ids[0] if missing_ids else None,
        },
        "warnings": list(warnings),
        "empty_pile": empty,
        "metrics": metrics,
    }


def print_report(data: dict) -> None:
    print("=" * 72)
    print("PIQS pass/fail  x  generation confidence  (logprob separation pilot)")
    print("=" * 72)

    for w in data["warnings"]:
        print(f"  [warn] {w}")
    if data["warnings"]:
        print()

    c = data["counts"]
    print("PILE COUNTS  (units matched to a PIQS pass/fail AND present in the output dir)")
    print(f"  PIQS PASS : {c['pass']}")
    print(f"  PIQS FAIL : {c['fail']}")
    if c["unscored"]:
        print(f"  (note: {c['unscored']} unit.json summaries had no PIQS entry -- not compared)")
    if c["missing_from_output_dir"]:
        print(f"  (note: {c['missing_from_output_dir']} PIQS ids had no unit.json in the output dir, "
              f"e.g. {c['missing_ids_example']})")
    print()

    if data["empty_pile"]:
        print("!" * 72)
        print("!! WARNING: one pile is EMPTY -- the separation check is MEANINGLESS.")
        print("!! You need more (or harder) cells so PIQS produces both passes and fails.")
        print("!" * 72)
        return

    header = f"{'metric':<22} {'pass n':>6} {'pass mean':>10} {'pass med':>10}   " \
             f"{'fail n':>6} {'fail mean':>10} {'fail med':>10}   {'d(mean)':>9} {'d(med)':>9}"
    print(header)
    print("-" * len(header))
    for key in METRICS:
        m = data["metrics"][key]
        print(f"{key:<22} {m['pass']['n']:>6} {_fmt(m['pass']['mean'])} {_fmt(m['pass']['median'])}   "
              f"{m['fail']['n']:>6} {_fmt(m['fail']['mean'])} {_fmt(m['fail']['median'])}   "
              f"{_fmt(m['diff']['mean'])} {_fmt(m['diff']['median'])}")
    print()
    print("Reading it: logprobs are <= 0; LESS confident = MORE negative. A POSITIVE")
    print("d(mean)/d(med) means the PASS pile is more confident than the FAIL pile,")
    print("i.e. the number separates pass from fail in the expected direction.")


def write_report(data: dict, path: Path) -> None:
    """Persist the report. .csv -> the per-metric table; anything else -> JSON
    (the full structured report incl. meta, counts, warnings)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".csv":
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["metric", "pass_n", "pass_mean", "pass_median",
                        "fail_n", "fail_mean", "fail_median", "d_mean", "d_median"])
            for key in METRICS:
                m = data["metrics"].get(key)
                if not m:  # empty pile -> no per-metric stats
                    w.writerow([key, data["counts"]["pass"], "", "",
                                data["counts"]["fail"], "", "", "", ""])
                    continue
                w.writerow([key, m["pass"]["n"], m["pass"]["mean"], m["pass"]["median"],
                            m["fail"]["n"], m["fail"]["mean"], m["fail"]["median"],
                            m["diff"]["mean"], m["diff"]["median"]])
    else:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="Pass/fail confidence separation report for the logprob pilot.")
    ap.add_argument("--output-dir", required=True,
                    help="The pilot --output-dir (searched recursively for unit.json).")
    ap.add_argument("--piqs-results", required=True,
                    help="CSV or JSON mapping unit_id -> pass/fail (or -> score with --threshold).")
    ap.add_argument("--threshold", type=float, default=None,
                    help="If PIQS values are numeric scores, pass := score >= THRESHOLD.")
    ap.add_argument("--out", default=None,
                    help="Also save the report to this path. .json -> full structured report "
                         "(meta + counts + per-metric stats); .csv -> the per-metric table.")
    args = ap.parse_args(argv)

    out_dir = Path(args.output_dir)
    if not out_dir.exists():
        raise SystemExit(f"--output-dir not found: {out_dir}")
    piqs_path = Path(args.piqs_results)
    if not piqs_path.exists():
        raise SystemExit(f"--piqs-results not found: {piqs_path}")

    warnings: list = []
    piqs_map = load_piqs_results(piqs_path, args.threshold, warnings)
    summaries = load_unit_summaries(out_dir)

    if not piqs_map:
        raise SystemExit(f"No usable pass/fail rows parsed from {piqs_path}.")
    if not summaries:
        raise SystemExit(f"No unit.json summaries found under {out_dir}.")

    pass_pile: list = []
    fail_pile: list = []
    missing_ids: list = []
    for uid, is_pass in piqs_map.items():
        summ = summaries.get(uid)
        if summ is None:
            missing_ids.append(uid)
            continue
        (pass_pile if is_pass else fail_pile).append(summ)

    n_unscored = sum(1 for uid in summaries if uid not in piqs_map)

    meta = {
        "output_dir": str(out_dir),
        "piqs_results": str(piqs_path),
        "threshold": args.threshold,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    data = build_report_data(pass_pile, fail_pile, warnings, n_unscored, missing_ids, meta)
    print_report(data)
    if args.out:
        out_path = Path(args.out)
        write_report(data, out_path)
        print(f"\n[saved report -> {out_path}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
