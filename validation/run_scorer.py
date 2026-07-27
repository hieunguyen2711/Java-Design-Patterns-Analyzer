"""Run the PIQS scorer (app.services.piqs_service.PIQSService, UNMODIFIED) on Kim's
refactored programs and record, per (case study, LLM, pattern):
  - per-property satisfied/not verdicts
  - PSR, CPC, PIQS
  - base/derived predicates (for disagreement analysis)
Also record javac compilation per program.

Writes validation/kim_replication_raw.json. Read-only on Kim's code and on the scorer.
"""

import json
import os
import subprocess
import sys
import tempfile

PROJECT = "/Users/hieunguyen/Documents/Coding Projects/DP Recognition Backend"
sys.path.insert(0, PROJECT)

from app.services.piqs_service import PIQSService, _PATTERN_WEIGHTS  # noqa: E402

MANIFEST = os.path.join(PROJECT, "validation/kim_file_manifest.json")
OUT = os.path.join(PROJECT, "validation/kim_replication_raw.json")


def load_files(program_root, rel_files):
    """basename -> content for every .java file in the program."""
    out = {}
    for rel in rel_files:
        full = os.path.join(program_root, rel)
        with open(full, "r", encoding="utf-8", errors="ignore") as fh:
            out[os.path.basename(rel)] = fh.read()
    return out


def compile_program(program_root, rel_files):
    """javac all program sources together into a temp dir. Returns (ok, returncode, stderr)."""
    java_paths = [os.path.join(program_root, rel) for rel in rel_files]
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            ["javac", "-d", tmp, *java_paths],
            capture_output=True,
            text=True,
        )
        return proc.returncode == 0, proc.returncode, proc.stderr.strip()


def main():
    with open(MANIFEST) as fh:
        manifest = json.load(fh)

    svc = PIQSService()
    prog_by_name = {p["program"]: p for p in manifest["programs"]}

    programs_out = {}
    results = []

    # Compile every program (originals + refactored) for the record.
    for prog in manifest["programs"]:
        name = prog["program"]
        root = prog["extracted_root"]
        ok, rc, stderr = compile_program(root, prog["java_files"])
        programs_out[name] = {
            "case_study": prog["case_study"],
            "llm": prog["llm"],
            "role": prog["role"],
            "num_java_files": prog["num_java_files"],
            "java_files": prog["java_files"],
            "compiles": ok,
            "javac_returncode": rc,
            "javac_stderr": stderr,
        }

    # Score each (case study, LLM, pattern) unit on the refactored programs.
    for unit in manifest["scoring_units"]:
        prog = prog_by_name[unit["program"]]
        files = load_files(prog["extracted_root"], prog["java_files"])
        res = svc.evaluate(pattern_name=unit["pattern"], java_files=files)

        props = {
            row["property_id"]: {
                "weight": row["weight"],
                "satisfaction": row["satisfaction"],
                "satisfied": bool(row["satisfaction"]),
                "justification": row["justification"],
            }
            for row in res["logical_assessment"]
        }
        results.append(
            {
                "case_study": unit["case_study"],
                "llm": unit["llm"],
                "pattern": unit["pattern"],
                "program": unit["program"],
                "properties": props,
                "psr": res["breadth_calculation_psr"]["result_percent"],
                "cpc": res["depth_calculation_cpc"]["result_percent"],
                "piqs": res["final_quality_result_piqs"]["result_percent"],
                "psr_formula": res["breadth_calculation_psr"]["formula"],
                "cpc_formula": res["depth_calculation_cpc"]["formula"],
                "piqs_formula": res["final_quality_result_piqs"]["formula"],
                "base_predicates": res["base_predicates"],
                "derived_predicates": res["derived_predicates"],
                "grade": res["grade"],
            }
        )

    out = {
        "generated_by": "validation/run_scorer.py",
        "scorer": "app.services.piqs_service.PIQSService (unmodified)",
        "python": sys.version.split()[0],
        "weights": _PATTERN_WEIGHTS,
        "programs": programs_out,
        "results": results,
    }
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=2)

    print(f"Wrote {OUT}")
    print(f"  programs compiled/checked: {len(programs_out)}")
    print(f"  scoring units evaluated: {len(results)}")
    print("\nCompilation summary:")
    for name, p in programs_out.items():
        if p["role"] == "refactored":
            print(f"  {'OK ' if p['compiles'] else 'FAIL'}  {p['case_study']:4} {p['llm']:8} {name}")


if __name__ == "__main__":
    main()
