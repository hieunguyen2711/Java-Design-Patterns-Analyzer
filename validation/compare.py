"""Compare my scorer output (kim_replication_raw.json) against Kim's published ground
truth. Emits validation/kim_comparison.json with property-level and score-level
comparisons, headline agreement, per-property reliability, and an arithmetic
self-check of Kim's published numbers.
"""

import json
import os

PROJECT = "/Users/hieunguyen/Documents/Coding Projects/DP Recognition Backend"
RAW = os.path.join(PROJECT, "validation/kim_replication_raw.json")
OUT = os.path.join(PROJECT, "validation/kim_comparison.json")

WEIGHTS = {
    "factory-method": {"F1": 2, "F2": 3, "F3": 3, "F4": 3, "F5": 2},
    "strategy": {"S1": 3, "S2": 3, "S3": 2, "S4": 3},
    "composite": {"C1": 3, "C2": 2, "C3": 3, "C4": 3, "C5": 3},
    "observer": {"O1": 2, "O2": 3, "O3": 3, "O4": 3},
    "singleton": {"G1": 3},
}
PROP_ORDER = {
    "factory-method": ["F1", "F2", "F3", "F4", "F5"],
    "strategy": ["S1", "S2", "S3", "S4"],
    "composite": ["C1", "C2", "C3", "C4", "C5"],
    "observer": ["O1", "O2", "O3", "O4"],
    "singleton": ["G1"],
}

# Kim's FAILING properties per (case, llm, pattern). Everything not listed passes.
# Source: task "which individual properties failed" tables (numeric-table-authoritative).
KIM_FAILS = {
    ("POSS", "ChatGPT"): {"factory-method": {"F1"}, "strategy": set(), "composite": set(), "observer": set()},
    ("POSS", "Claude"):  {"factory-method": {"F4"}, "strategy": set(), "composite": set(), "observer": {"O1"}},
    ("POSS", "Copilot"): {"factory-method": {"F1"}, "strategy": set(), "composite": {"C1", "C4", "C5"}, "observer": {"O1"}},
    ("POSS", "Gemini"):  {"factory-method": set(), "strategy": set(), "composite": {"C1", "C4", "C5"}, "observer": {"O2", "O3", "O4"}},
    ("POSS", "Meta"):    {"factory-method": set(), "strategy": set(), "composite": set(), "observer": set()},
    ("SWS", "ChatGPT"):  {"factory-method": {"F1", "F4", "F5"}, "strategy": set(), "singleton": set(), "observer": {"O1"}},
    ("SWS", "Claude"):   {"factory-method": {"F5"}, "strategy": set(), "singleton": set(), "observer": {"O1"}},
    ("SWS", "Copilot"):  {"factory-method": {"F1", "F5"}, "strategy": set(), "singleton": set(), "observer": set()},
    ("SWS", "Gemini"):   {"factory-method": {"F5"}, "strategy": set(), "singleton": set(), "observer": {"O1", "O3", "O4"}},
    ("SWS", "Meta"):     {"factory-method": {"F1", "F5"}, "strategy": set(), "singleton": set(), "observer": {"O3", "O4"}},
}

# Kim's published PSR/CPC/PIQS (Tables 13 & 16), Composite row corrected per task note.
KIM_SCORES = {
    ("POSS", "ChatGPT", "factory-method"): (80.00, 84.62, 81.85),
    ("POSS", "ChatGPT", "strategy"): (100.0, 100.0, 100.0),
    ("POSS", "ChatGPT", "composite"): (100.0, 100.0, 100.0),
    ("POSS", "ChatGPT", "observer"): (100.0, 100.0, 100.0),
    ("POSS", "Claude", "factory-method"): (80.00, 76.92, 78.77),
    ("POSS", "Claude", "strategy"): (100.0, 100.0, 100.0),
    ("POSS", "Claude", "composite"): (100.0, 100.0, 100.0),   # corrected
    ("POSS", "Claude", "observer"): (75.00, 81.82, 77.73),
    ("POSS", "Copilot", "factory-method"): (80.00, 84.62, 81.85),
    ("POSS", "Copilot", "strategy"): (100.0, 100.0, 100.0),
    ("POSS", "Copilot", "composite"): (40.00, 35.71, 38.29),
    ("POSS", "Copilot", "observer"): (75.00, 81.82, 77.73),
    ("POSS", "Gemini", "factory-method"): (100.0, 100.0, 100.0),
    ("POSS", "Gemini", "strategy"): (100.0, 100.0, 100.0),
    ("POSS", "Gemini", "composite"): (40.00, 35.71, 38.29),   # corrected
    ("POSS", "Gemini", "observer"): (25.00, 18.18, 22.27),
    ("POSS", "Meta", "factory-method"): (100.0, 100.0, 100.0),
    ("POSS", "Meta", "strategy"): (100.0, 100.0, 100.0),
    ("POSS", "Meta", "composite"): (100.0, 100.0, 100.0),
    ("POSS", "Meta", "observer"): (100.0, 100.0, 100.0),
    ("SWS", "ChatGPT", "factory-method"): (40.00, 46.15, 42.46),
    ("SWS", "ChatGPT", "strategy"): (100.0, 100.0, 100.0),
    ("SWS", "ChatGPT", "singleton"): (100.0, 100.0, 100.0),
    ("SWS", "ChatGPT", "observer"): (75.00, 81.82, 77.73),
    ("SWS", "Claude", "factory-method"): (80.00, 84.62, 81.85),
    ("SWS", "Claude", "strategy"): (100.0, 100.0, 100.0),
    ("SWS", "Claude", "singleton"): (100.0, 100.0, 100.0),
    ("SWS", "Claude", "observer"): (75.00, 81.82, 77.73),
    ("SWS", "Copilot", "factory-method"): (60.00, 69.23, 63.69),
    ("SWS", "Copilot", "strategy"): (100.0, 100.0, 100.0),
    ("SWS", "Copilot", "singleton"): (100.0, 100.0, 100.0),
    ("SWS", "Copilot", "observer"): (100.0, 100.0, 100.0),
    ("SWS", "Gemini", "factory-method"): (80.00, 84.62, 81.85),
    ("SWS", "Gemini", "strategy"): (100.0, 100.0, 100.0),
    ("SWS", "Gemini", "singleton"): (100.0, 100.0, 100.0),
    ("SWS", "Gemini", "observer"): (25.00, 27.27, 25.91),
    ("SWS", "Meta", "factory-method"): (60.00, 69.23, 63.69),
    ("SWS", "Meta", "strategy"): (100.0, 100.0, 100.0),
    ("SWS", "Meta", "singleton"): (100.0, 100.0, 100.0),
    ("SWS", "Meta", "observer"): (50.00, 45.45, 48.18),
}

LLM_ORDER = ["ChatGPT", "Claude", "Copilot", "Gemini", "Meta"]


def kim_scores_from_fails(pattern, fails):
    """Recompute PSR/CPC/PIQS from a failing-property set, to (a) verify Kim's numbers
    and (b) provide the expected per-property verdict."""
    props = PROP_ORDER[pattern]
    w = WEIGHTS[pattern]
    sat = {p: (0 if p in fails else 1) for p in props}
    satisfied = sum(sat.values())
    total = len(props)
    earned = sum(w[p] * sat[p] for p in props)
    wtotal = sum(w.values())
    psr = satisfied / total * 100
    cpc = earned / wtotal * 100
    piqs = psr * 0.6 + cpc * 0.4
    return sat, round(psr, 2), round(cpc, 2), round(piqs, 2)


def main():
    raw = json.load(open(RAW))
    my = {(r["case_study"], r["llm"], r["pattern"]): r for r in raw["results"]}

    prop_rows = []
    score_rows = []
    # reliability[prop] = [tested, agreed]
    reliability = {}

    arithmetic_check = []

    for (case, llm), patmap in KIM_FAILS.items():
        for pattern, fails in patmap.items():
            kim_sat, kpsr, kcpc, kpiqs = kim_scores_from_fails(pattern, fails)
            pub = KIM_SCORES[(case, llm, pattern)]
            # verify our derived-from-fails numbers match Kim's published table
            arithmetic_check.append({
                "unit": f"{case}/{llm}/{pattern}",
                "published": pub,
                "recomputed_from_failset": [kpsr, kcpc, kpiqs],
                "consistent": (abs(pub[0]-kpsr) < 0.05 and abs(pub[1]-kcpc) < 0.05 and abs(pub[2]-kpiqs) < 0.05),
            })

            r = my[(case, llm, pattern)]
            for p in PROP_ORDER[pattern]:
                kim_v = kim_sat[p]
                my_v = r["properties"][p]["satisfaction"]
                match = (kim_v == my_v)
                prop_rows.append({
                    "case_study": case, "llm": llm, "pattern": pattern, "property": p,
                    "kim": "satisfied" if kim_v else "not satisfied",
                    "mine": "satisfied" if my_v else "not satisfied",
                    "match": match,
                })
                t, a = reliability.get(p, (0, 0))
                reliability[p] = (t + 1, a + (1 if match else 0))

            score_rows.append({
                "case_study": case, "llm": llm, "pattern": pattern,
                "kim_psr": pub[0], "kim_cpc": pub[1], "kim_piqs": pub[2],
                "my_psr": r["psr"], "my_cpc": r["cpc"], "my_piqs": r["piqs"],
                "d_psr": round(abs(pub[0]-r["psr"]), 2),
                "d_cpc": round(abs(pub[1]-r["cpc"]), 2),
                "d_piqs": round(abs(pub[2]-r["piqs"]), 2),
            })

    total_props = len(prop_rows)
    agreed_props = sum(1 for x in prop_rows if x["match"])
    exact_units = sum(1 for s in score_rows if s["d_psr"] == 0 and s["d_cpc"] == 0 and s["d_piqs"] == 0)

    reliability_out = {
        p: {"tested": t, "agreed": a, "agreement_pct": round(a / t * 100, 1), "reliable": (a / t) >= 0.8}
        for p, (t, a) in reliability.items()
    }

    out = {
        "headline": {
            "total_property_judgments": total_props,
            "agreed": agreed_props,
            "agreement_pct": round(agreed_props / total_props * 100, 1),
            "score_units": len(score_rows),
            "units_exact_match_all3": exact_units,
        },
        "arithmetic_check": arithmetic_check,
        "property_comparison": prop_rows,
        "score_comparison": score_rows,
        "reliability": reliability_out,
    }
    json.dump(out, open(OUT, "w"), indent=2)

    print(f"Wrote {OUT}\n")
    print(f"HEADLINE: {agreed_props}/{total_props} property judgments agree = {out['headline']['agreement_pct']}%")
    print(f"Score units exactly matching all 3 metrics: {exact_units}/{len(score_rows)}\n")

    bad = [a for a in arithmetic_check if not a["consistent"]]
    print(f"Arithmetic self-check of Kim's published numbers: {len(arithmetic_check)-len(bad)}/{len(arithmetic_check)} internally consistent")
    for a in bad:
        print(f"  INCONSISTENT: {a['unit']} published={a['published']} recomputed={a['recomputed_from_failset']}")

    print("\nPer-property reliability:")
    for p in ["F1","F2","F3","F4","F5","S1","S2","S3","S4","C1","C2","C3","C4","C5","O1","O2","O3","O4","G1"]:
        if p in reliability_out:
            r = reliability_out[p]
            flag = "" if r["reliable"] else "   <-- UNRELIABLE (<80%)"
            print(f"  {p}: {r['agreed']}/{r['tested']} = {r['agreement_pct']}%{flag}")

    print("\nDisagreements (property-level):")
    for x in prop_rows:
        if not x["match"]:
            print(f"  {x['case_study']}/{x['llm']}/{x['pattern']}/{x['property']}: Kim={x['kim']:14} Mine={x['mine']}")


if __name__ == "__main__":
    main()
