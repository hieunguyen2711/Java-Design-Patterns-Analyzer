"""Build kim_file_manifest.json mapping every .java file to (case study, LLM) and
recording, per program, which design patterns Kim evaluated for that case study.

Read-only on Kim's code. Reads from the scratchpad extraction of Kim's ZIPs; also
records each program's original ZIP source path for reproducibility.
"""

import json
import os

KIM_DIR = "/Users/hieunguyen/Documents/Coding Projects/Design-Pattern-Applications"
EXTRACT_ROOT = (
    "/private/tmp/claude-501/-Users-hieunguyen-Documents-Coding-Projects-"
    "DP-Recognition-Backend/b2027f2a-5c76-45e6-9d65-d2cce82eb528/scratchpad/kim_extracted"
)
OUT = "/Users/hieunguyen/Documents/Coding Projects/DP Recognition Backend/validation/kim_file_manifest.json"

# program folder -> (case_study, llm, role)
PROGRAMS = {
    "POS": ("POSS", None, "original_base"),
    "RefactoredPOSChatGPT": ("POSS", "ChatGPT", "refactored"),
    "RefactoredPOSClaude": ("POSS", "Claude", "refactored"),
    "RefactoredPOSCopilot": ("POSS", "Copilot", "refactored"),
    "RefactoredPOSGemini": ("POSS", "Gemini", "refactored"),
    "RefactoredPOSMeta": ("POSS", "Meta", "refactored"),
    "SmartWallet": ("SWS", None, "original_base"),
    "RefactoredSWSChatGPT": ("SWS", "ChatGPT", "refactored"),
    "RefactoredSWSClaude": ("SWS", "Claude", "refactored"),
    "RefactoredSWSCopilot": ("SWS", "Copilot", "refactored"),
    "RefactoredSWSGemini": ("SWS", "Gemini", "refactored"),
    "RefactoredSWSMeta": ("SWS", "Meta", "refactored"),
}

# Patterns Kim evaluated per case study (Kim Tables 13 & 16).
PATTERNS_BY_CASE = {
    "POSS": ["factory-method", "strategy", "composite", "observer"],
    "SWS": ["factory-method", "strategy", "singleton", "observer"],
}

ZIP_BY_PROGRAM = {
    "POS": "POS.zip",
    "RefactoredPOSChatGPT": "RefactoredPOSChatGPT.zip",
    "RefactoredPOSClaude": "RefactoredPOSClaude.zip",
    "RefactoredPOSCopilot": "RefactoredPOSCopilot.zip",
    "RefactoredPOSGemini": "RefactoredPOSGemini.zip",
    "RefactoredPOSMeta": "RefactoredPOSMeta.zip",
    "SmartWallet": "SmartWallet.zip",
    "RefactoredSWSChatGPT": "RefactoredSWSChatGPT.zip",
    "RefactoredSWSClaude": "RefactoredSWSClaude.zip",
    "RefactoredSWSCopilot": "RefactoredSWSCopilot.zip",
    "RefactoredSWSGemini": "RefactoredSWSGemini.zip",
    "RefactoredSWSMeta": "RefactoredSWSMeta.zip",
}


def collect_java(program_root):
    files = []
    for root, _, names in os.walk(program_root):
        if "__MACOSX" in root:
            continue
        for n in sorted(names):
            if n.endswith(".java"):
                full = os.path.join(root, n)
                files.append(full)
    return sorted(files)


def main():
    programs = []
    files_index = []
    for prog, (case, llm, role) in PROGRAMS.items():
        prog_dir = os.path.join(EXTRACT_ROOT, prog)
        java_files = collect_java(prog_dir)
        rel_files = []
        for f in java_files:
            rel = os.path.relpath(f, prog_dir)
            rel_files.append(rel)
            files_index.append(
                {
                    "file": os.path.basename(f),
                    "relative_path": rel,
                    "program": prog,
                    "case_study": case,
                    "llm": llm,
                    "role": role,
                }
            )
        programs.append(
            {
                "program": prog,
                "case_study": case,
                "llm": llm,
                "role": role,
                "source_zip": os.path.join(KIM_DIR, ZIP_BY_PROGRAM[prog]),
                "extracted_root": prog_dir,
                "num_java_files": len(rel_files),
                "java_files": rel_files,
                "patterns_evaluated": (
                    PATTERNS_BY_CASE[case] if role == "refactored" else []
                ),
            }
        )

    # 40 scoring units = 5 LLMs x 2 case studies x 4 patterns (refactored only).
    scoring_units = []
    for p in programs:
        if p["role"] != "refactored":
            continue
        for pat in p["patterns_evaluated"]:
            scoring_units.append(
                {
                    "case_study": p["case_study"],
                    "llm": p["llm"],
                    "pattern": pat,
                    "program": p["program"],
                }
            )

    manifest = {
        "note": (
            "Kim evaluated the 10 'refactored' programs (5 LLMs x 2 case studies). "
            "The two 'original_base' programs (POS, SmartWallet) are the pre-refactoring "
            "source and were NOT scored in Kim's tables; they are listed for completeness. "
            "A design pattern is NOT a per-file attribute: each refactored program embodies "
            "all four patterns for its case study simultaneously, so files map to "
            "(case_study, LLM) and patterns are evaluated at the program level. The unit of "
            "scoring is therefore (case_study, LLM, pattern) = 40 units."
        ),
        "case_studies": {
            "POSS": {"description": "Point of Sale System", "patterns": PATTERNS_BY_CASE["POSS"]},
            "SWS": {"description": "Smart Wallet System", "patterns": PATTERNS_BY_CASE["SWS"]},
        },
        "llms": ["ChatGPT", "Claude", "Copilot", "Gemini", "Meta"],
        "num_programs": len(programs),
        "num_refactored_programs": sum(1 for p in programs if p["role"] == "refactored"),
        "num_scoring_units": len(scoring_units),
        "programs": programs,
        "scoring_units": scoring_units,
        "files": files_index,
    }

    with open(OUT, "w") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"Wrote {OUT}")
    print(f"  programs: {len(programs)} ({manifest['num_refactored_programs']} refactored)")
    print(f"  files indexed: {len(files_index)}")
    print(f"  scoring units: {len(scoring_units)}")


if __name__ == "__main__":
    main()
