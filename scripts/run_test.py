import json
import re
import time
from pathlib import Path


import requests

API_URL = "http://localhost:8000/analyze"
ZIPPED_DIR = Path("datasets_obfuscated")
OUTPUT_FILE = Path("obfuscated_results.json")
MODEL = "qwen3-coder-30b-a3b-instruct"


PATTERN_ALIASES: dict[str, list[str]] = {
    # GoF Creational
    "abstract-factory":                         ["abstract factory"],
    "builder":                                  ["builder"],
    "factory":                                  ["factory method", "factory"],
    "factory-method":                           ["factory method"],
    "factory-kit":                              ["factory kit", "factory"],
    "prototype":                                ["prototype"],
    "singleton":                                ["singleton"],
    "multiton":                                 ["multiton"],
    "object-pool":                              ["object pool"],
    "monostate":                                ["monostate"],
    # GoF Structural
    "adapter":                                  ["adapter"],
    "bridge":                                   ["bridge"],
    "composite":                                ["composite"],
    "decorator":                                ["decorator"],
    "dynamic-proxy":                            ["dynamic proxy", "proxy"],
    "facade":                                   ["facade"],
    "flyweight":                                ["flyweight"],
    "marker-interface":                         ["marker interface"],
    "private-class-data":                       ["private class data"],
    "proxy":                                    ["proxy"],
    "twin":                                     ["twin"],
    "virtual-proxy":                            ["virtual proxy", "proxy"],
    # GoF Behavioral
    "acyclic-visitor":                          ["acyclic visitor", "visitor"],
    "chain-of-responsibility":                  ["chain of responsibility"],
    "command":                                  ["command"],
    "interpreter":                              ["interpreter"],
    "iterator":                                 ["iterator"],
    "mediator":                                 ["mediator"],
    "memento":                                  ["memento"],
    "null-object":                              ["null object"],
    "observer":                                 ["observer"],
    "specification":                            ["specification"],
    "state":                                    ["state"],
    "strategy":                                 ["strategy"],
    "template-method":                          ["template method"],
    # Concurrency
    "active-object":                            ["active object"],
    "actor-model":                              ["actor model", "actor"],
    "balking":                                  ["balking"],
    "double-checked-locking":                   ["double-checked locking", "double checked locking"],
    "double-buffer":                            ["double buffer"],
    "guarded-suspension":                       ["guarded suspension"],
    "monitor":                                  ["monitor"],
    "promise":                                  ["promise"],
    "reactor":                                  ["reactor"],
    "thread-pool-executor":                     ["thread pool", "executor"],
    # Architectural / Enterprise
    "data-access-object":                       ["data access object", "dao"],
    "data-mapper":                              ["data mapper"],
    "data-transfer-object":                     ["data transfer object", "dto"],
    "dependency-injection":                     ["dependency injection"],
    "event-sourcing":                           ["event sourcing"],
    "identity-map":                             ["identity map"],
    "model-view-controller":                    ["model view controller", "mvc"],
    "model-view-presenter":                     ["model view presenter", "mvp"],
    "page-controller":                          ["page controller"],
    "repository":                               ["repository"],
    "resource-acquisition-is-initialization":   ["resource acquisition is initialization", "raii"],
    "service-layer":                            ["service layer"],
    "service-locator":                          ["service locator"],
    "service-stub":                             ["service stub"],
    "single-table-inheritance":                 ["single table inheritance"],
    "table-inheritance":                        ["table inheritance"],
    "table-module":                             ["table module"],
    "transaction-script":                       ["transaction script"],
    "unit-of-work":                             ["unit of work"],
    # UI / Presentation
    "monad":                                    ["monad"],
    "view-helper":                              ["view helper"],
    # Idioms / Other
    "ambassador":                               ["ambassador"],
    "business-delegate":                        ["business delegate"],
    "collection-pipeline":                      ["collection pipeline"],
    "combinator":                               ["combinator"],
    "converter":                                ["converter"],
    "curiously-recurring-template-pattern":     ["curiously recurring template", "crtp"],
    "dirty-flag":                               ["dirty flag"],
    "execute-around":                           ["execute around"],
    "fluent-interface":                         ["fluent interface"],
    "function-composition":                     ["function composition"],
    "page-object":                              ["page object"],
    "role-object":                              ["role object"],
    "servant":                                  ["servant"],
    "special-case":                             ["special case"],
    "trampoline":                               ["trampoline"],
    "update-method":                            ["update method"],
    "value-object":                             ["value object"],
}


def is_match(zipped_stem: str, formatted_repsonse: str) -> bool:
    '''
        This function verifies if the LLM correctly identifies the pattern or not
        It takes in the file name and compare it to the LLM's answer.
    '''
    formatted_lower = formatted_repsonse.lower()  # lowercase so comparison is case-insensitive
    aliaes = PATTERN_ALIASES.get(zipped_stem) # Get the list from the key name
    if aliaes:
        return any(alias in formatted_lower for alias in aliaes)
    return re.sub(r"[-_]", " ", zipped_stem).lower() in formatted_lower #Fall back if the name differs.

def format_raw_response(raw_analysis: str) -> str:
    """
    Extracts just the design pattern name from the LLM's raw analysis.
    Looks for lines like '**Pattern Identified:** Abstract Factory'
    Falls back to returning the first non-empty line if no match is found.
    """
    # Try to match "Pattern Identified: <name>" (with or without markdown bold)
    match = re.search(
        r"\*{0,2}Pattern(?:\s+Identified)?\*{0,2}[:：]\s*\*{0,2}(.+?)\*{0,2}$",
        raw_analysis,
        re.IGNORECASE | re.MULTILINE,
    )
    if match:
        return match.group(1).strip()

    # Fallback: return the first non-empty line
    for line in raw_analysis.splitlines():
        stripped = line.strip("*# ").strip()
        if stripped:
            return stripped

    return raw_analysis.strip()

def main():
    zip_files = sorted(ZIPPED_DIR.glob("*.zip"))
    if not zip_files:
        print("No zip files found in", ZIPPED_DIR)
        return
    
    results = [] 
    for idx, zip_path in enumerate(zip_files, start=1):
        stem = zip_path.stem # Get the names of the file without the extension
        print(f"[{idx}/{len(zip_files)}] {stem} ...", end=" ", flush=True)

        try:
            with open(zip_path, "rb") as f: #Try to open the path in the "read binary" mode
                response = requests.post(
                    API_URL, 
                    files={"file": (zip_path.name, f, "application/zip")},
                    data={"model": MODEL},
                    timeout=360,
                )

            if not response.ok:
                print(f"HTTP {response.status_code}")
                results.append({"pattern": stem, 
                                "llm_answer": f"ERROR: HTTP {response.status_code}", 
                                "status" : "Not Pass!"})
                continue
            raw_analysis = response.json().get("raw_analysis", "")
            formatted_repsonse = format_raw_response(raw_analysis)
            passed = is_match(stem, formatted_repsonse)
            label = "Pass" if passed else "Not Pass"
            print(label)
            results.append({"pattern": stem, "llm_answer":formatted_repsonse, "Status": label})

                
        except requests.exceptions.Timeout:
            print("TIMEOUT, TRY AGAIN LATER!")
            results.append({"pattern": stem, "llm_answer": "ERROR: Request timed out", "Status": "Not Pass"})
        except Exception as e:
            print("Error:", e)
            results.append({"pattern": stem, "llm_answer": f"Error: {e}", "Status": "Not Passed"})
        
        time.sleep(1)
    OUTPUT_FILE.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    passed = sum(1 for r in results if r["Status"] == "Pass")
    print(f"\nDone. {passed}/{len(results)} passed. Results -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
