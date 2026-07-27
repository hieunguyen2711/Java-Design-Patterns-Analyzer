"""Assemble validation/kim_replication_report_v4.md: before(v3)/after(v4) of the pass-3
parser-precision fixes (F class-scope fields, G whole-token identifiers). Precision-for-
scale, not score-chasing. Prominently reports the G1 protected regression (Bill Pugh holder
idiom) discovered by the now-correct extractor.
"""
import json
import os

PROJECT = "/Users/hieunguyen/Documents/Coding Projects/DP Recognition Backend"
V3 = json.load(open(os.path.join(PROJECT, "validation/kim_comparison_v3.json")))
V4 = json.load(open(os.path.join(PROJECT, "validation/kim_comparison.json")))
OUT = os.path.join(PROJECT, "validation/kim_replication_report_v4.md")

LLM_ORDER = ["ChatGPT", "Claude", "Copilot", "Gemini", "Meta"]
PAT_ORDER = {"factory-method": 0, "strategy": 1, "composite": 2, "observer": 3, "singleton": 4}
PAT_LABEL = {"factory-method": "Factory", "strategy": "Strategy", "composite": "Composite",
             "observer": "Observer", "singleton": "Singleton"}
PROPS = ["F1", "F2", "F3", "F4", "F5", "S1", "S2", "S3", "S4",
         "C1", "C2", "C3", "C4", "C5", "O1", "O2", "O3", "O4", "G1"]
# protected set for pass 3 (per instructions): everything >=90% EXCEPT deferred S3
PROTECTED = ["S1", "S2", "S4", "C2", "C3", "G1", "F1", "F2", "F3", "F5", "C1", "C4", "C5", "O1"]


def dis(c):
    return {(r["case_study"], r["llm"], r["pattern"], r["property"]) for r in c["property_comparison"] if not r["match"]}


def skey(t):
    return (t[0], LLM_ORDER.index(t[1]), PAT_ORDER[t[2]], t[3])


# classification of the 19 remaining v4 disagreements
REMAIN = {
    ("POSS","ChatGPT","strategy","S3"): ("DEFER-S3","Strategy is a method-local/param, not a stored field/setter; with locals no longer mis-parsed as fields, is_context correctly fails. The deferred strategy-as-parameter choice."),
    ("POSS","Claude","strategy","S3"): ("DEFER-S3","Strategy used via local/param, not a stored field. Deferred strategy-as-parameter choice (newly surfaced by Fix F)."),
    ("POSS","Copilot","strategy","S3"): ("DEFER-S3","Strategy used via local/param. Deferred strategy-as-parameter choice (newly surfaced by Fix F)."),
    ("POSS","Gemini","strategy","S3"): ("DEFER-S3","Strategy used via local/param. Deferred strategy-as-parameter choice (newly surfaced by Fix F)."),
    ("SWS","Copilot","strategy","S3"): ("DEFER-S3","Wallet.performTransaction receives the strategy as a parameter. Deferred strategy-as-parameter choice (already failing in v3)."),
    ("POSS","Claude","factory-method","F4"): ("AMBIG","F2/F3/F4 are all weight 3 and arithmetically indistinguishable; Kim's 'F4 fails' is prose-derived. My F4=satisfied."),
    ("POSS","Gemini","observer","O1"): ("KIM","No abstract subject exists (ItemInventory concrete); Kim's numeric O1=satisfied is impossible. Our O1=not satisfied matches the code."),
    ("POSS","Gemini","observer","O2"): ("KIM","InventoryObserver interface exists and is notified; O2 defensibly satisfied. Kim's numeric O2=fail contradicts the code."),
    ("POSS","Gemini","observer","O3"): ("KIM","ItemInventory loops observers calling update(); O3 defensibly satisfied. Kim's O3=fail contradicts the code."),
    ("POSS","Gemini","observer","O4"): ("KIM","Register implements update(); O4 defensibly satisfied. Kim's O4=fail contradicts the code."),
    ("SWS","Claude","factory-method","F4"): ("DEFER-F4","createWallet returns the concrete `Wallet`; the F4-concrete-product choice was deferred. Left as-is."),
    ("SWS","Copilot","factory-method","F1"): ("KIM","`abstract class WalletFactory` + `ConcreteWalletFactory extends` genuinely exist (F1=satisfied). Kim's F1=fail while F2/F3/F4=pass is inconsistent."),
    ("SWS","Copilot","factory-method","F4"): ("DEFER-F4","createWallet returns concrete `Wallet` (deferred F4-concrete choice). Left as-is."),
    ("SWS","Gemini","factory-method","F4"): ("DEFER-F4","createWallet returns concrete `Wallet` (deferred F4-concrete choice). Left as-is."),
    ("SWS","Gemini","observer","O3"): ("KIM","AuditLog loops observers calling onLogEvent(); ConsoleLogger is registered in main. Observer complete and wired; O3 defensibly satisfied. Kim's O3=fail contradicts the code."),
    ("SWS","Gemini","observer","O4"): ("KIM","ConsoleLogger implements onLogEvent(); O4 defensibly satisfied. Kim's O4=fail contradicts the code."),
    ("SWS","Meta","factory-method","F4"): ("KIM","Meta's SWS has NO factory class; Kim's F4=satisfied is indefensible. Our F4=not satisfied matches the code."),
    ("SWS","Meta","observer","O2"): ("KIM","`extends Observable` but no class implements Observer; structurally no abstract observer. Kim's O2=satisfied is lenient; ours is defensible."),
    ("SWS","Copilot","singleton","G1"): ("REGRESS","PROTECTED-SET REGRESSION (see dedicated section). Bill Pugh holder idiom: the static instance lives in a nested `Holder` class. Fix F correctly stops the nested field leaking into CurrencyConverter; this exposes that `has_static_instance` only inspects the singleton class itself. Predicate-logic gap, NOT a fix leak. Flagged, not fixed."),
}
CATLABEL = {
    "KIM": "Kim's number contradicts the code (our verdict correct) — cite, do not match",
    "DEFER-F4": "Deferred definitional choice: F4 concrete-typed product",
    "DEFER-S3": "Deferred definitional choice: S3 strategy-as-parameter (now correctly failing)",
    "AMBIG": "Genuine ambiguity in the property definition",
    "REGRESS": "PROTECTED-SET REGRESSION — predicate gap exposed by the correct extractor (flagged, not fixed)",
}


def build():
    S = []
    h3, h4 = V3["headline"], V4["headline"]
    d3, d4 = dis(V3), dis(V4)
    resolved, new = d3 - d4, d4 - d3

    S.append("# PIQS Scorer — Pass 3 (parser precision F & G): Before/After (v4)\n")
    S.append("**Goal of this pass: extractor *correctness for the main study*, not a higher Kim score.** "
             "Two fixes, both in the fact-extraction layer (no pattern-predicate logic changed):\n")
    S.append("- **F** — field extraction restricted to class-body scope. Method-local variables are no longer mis-captured as fields. (`_class_scope_only` strips every method/ctor/initialiser/nested-type body via brace-depth tracking.)\n")
    S.append("- **G** — identifier tests match whole tokens, not substrings. `pay` no longer matches inside `payment`; `add` operations detected by camelCase verb prefix (addChild yes, address no).\n")
    S.append("\nDiff (pass-3 only): `validation/piqs_service_fix_pass3.diff` (+61 / −10). v3 outputs preserved as `*_v3.*`.\n")

    S.append("## Headline: v3 → v4  (a DECREASE is the correct outcome here)\n")
    S.append("| Metric | v3 | v4 | Δ |\n|---|--:|--:|--:|")
    S.append("| Property-level agreement | {}/160 ({}%) | {}/160 ({}%) | {} pts |".format(
        h3["agreed"], h3["agreement_pct"], h4["agreed"], h4["agreement_pct"],
        round(h4["agreement_pct"] - h3["agreement_pct"], 1)))
    S.append("| Units matching all 3 scores exactly | {}/40 | {}/40 | {} |".format(
        h3["units_exact_match_all3"], h4["units_exact_match_all3"],
        h4["units_exact_match_all3"] - h3["units_exact_match_all3"]))
    S.append("| Disagreements | {} | {} | +{} |".format(len(d3), len(d4), len(d4) - len(d3)))
    S.append("")
    S.append("**This pass is precision-for-scale, not score-chasing.** The 5 extra disagreements are: **4 correct S3 "
             "corrections** (deferred strategy-as-parameter, previously propped up by the local-variable-as-field bug) "
             "and **1 protected regression on G1** (reported in full below). The scorer is now *more correct* even though "
             "the Kim number ticked down — exactly what you asked for.\n")

    # reliability
    S.append("## Per-property reliability: v3 → v4\n")
    S.append("| Prop | v3 | v4 | Δ | Note |\n|---|--:|--:|:--:|---|")
    for p in PROPS:
        r3 = V3["reliability"][p]["agreement_pct"]
        r4 = V4["reliability"][p]["agreement_pct"]
        arrow = "⬇" if r4 < r3 else ("⬆" if r4 > r3 else "")
        note = ""
        if p == "S3":
            note = "deferred strategy-as-parameter (expected ⬇, correct)"
        elif p == "G1":
            note = "**PROTECTED REGRESSION — holder idiom, see below**"
        elif p == "F4":
            note = "deferred F4-concrete + 1 ambiguity"
        S.append("| {} | {}% | {}% | {} | {} |".format(p, r3, r4, arrow, note))
    S.append("")

    # zero-regression check
    S.append("## Zero-regression check on the protected set (your step 3)\n")
    drops = [(p, V3["reliability"][p]["agreement_pct"], V4["reliability"][p]["agreement_pct"])
             for p in PROTECTED if V4["reliability"][p]["agreement_pct"] < V3["reliability"][p]["agreement_pct"]]
    if drops:
        S.append("⚠️ **One protected property dropped — STOPPING to report as instructed:**\n")
        for p, a, b in drops:
            S.append("- **{}**: {}% → {}%".format(p, a, b))
        S.append("\nEvery other protected property held exactly (F1 90, F2 100, F3 100, F5 100, S1/S2/S4 100, C1–C5 100, O1 90, G... see below). "
                 "The one drop is **G1**, analysed next. **It is NOT a fix leaking into predicate logic** — Fix F is a correct extractor change; it exposed a pre-existing narrowness in the G1 predicate.\n")
    else:
        S.append("No protected property dropped.\n")

    # G1 dedicated section
    S.append("## ⚠️ G1 protected regression — Bill Pugh holder idiom (STOP-and-report)\n")
    S.append("**SWS/Copilot Singleton G1 flipped satisfied → not satisfied.** Root cause, exactly:\n")
    S.append("```java\n"
             "// RefactoredSWSCopilot/CurrencyConverter.java\n"
             "class CurrencyConverter {\n"
             "    private CurrencyConverter() { }                    // private ctor  (has_private_ctor OK)\n"
             "    public static CurrencyConverter getInstance() {     // accessor      (has_instance_method OK)\n"
             "        return Holder.INSTANCE;\n"
             "    }\n"
             "    private static class Holder {                       // <-- nested static holder\n"
             "        private static final CurrencyConverter INSTANCE = new CurrencyConverter();\n"
             "    }\n"
             "}\n"
             "```\n")
    S.append("- **Before Fix F**, field extraction scanned the whole class body, so the nested `Holder.INSTANCE` "
             "field *leaked upward* and was counted as a static instance field of `CurrencyConverter`. `has_static_instance` "
             "was true — right answer, wrong mechanism.\n")
    S.append("- **After Fix F**, `CurrencyConverter` correctly has **0** fields (INSTANCE belongs to `Holder`). But "
             "`has_static_instance` only looks for a `static <SelfType>` field declared *directly in the singleton class*, "
             "so it does not recognise the Bill Pugh holder idiom, and **G1 fails**.\n")
    S.append("- **This is a PREDICATE-LOGIC gap, not an extractor bug.** Fix F is correct. Per your constraints "
             "(‘if a predicate needs its logic changed, STOP and report; that is a different pass’ and ‘if you find a "
             "seventh distinct cause, STOP and report — do not fix it here’), **I did NOT change the predicate.**\n")
    S.append("- **Impact for the main study:** classic singletons (`private static X instance;` in the class) still score "
             "G1 correctly — Fix F keeps genuine class-scope fields (verified: the other 4 SWS singletons stayed G1=1, and "
             "a synthetic classic-singleton keeps its field). Only the **holder idiom** is mis-scored.\n")
    S.append("- **Recommended pass 4 (needs your approval — it is a predicate change):** broaden `has_static_instance` "
             "to also accept a `static` field of the singleton's type declared in a **nested static class** of that "
             "singleton (the holder). That restores G1 for the holder idiom without reintroducing the local-variable bug.\n")
    S.append("\n**Decision needed from you:** approve the pass-4 G1 predicate broadening, or accept the holder-idiom "
             "limitation. I have left G1 as-is pending your call.\n")

    # S3 larger-than-expected
    S.append("## S3 dropped more than the single cell you anticipated (90% → 50%) — and that is correct\n")
    S.append("You expected POSS/ChatGPT S3 to flip. In fact **four** POSS S3 cells flipped "
             "(ChatGPT, Claude, Copilot, Gemini), because *all four* of those contexts use the strategy via a "
             "method-local variable or parameter, and each was being held up by the same local-variable-as-field bug. "
             "With the extractor corrected, `is_context` (which requires a stored strategy field or setter — the "
             "**deferred strategy-as-parameter** definition) correctly fails for all of them. These are the same deferred "
             "category, not new bugs. The 5 remaining S3 passes are contexts with a genuine class-scope strategy field.\n")

    # Fix A not rebroken
    S.append("## Fix A confirmed NOT re-broken\n")
    S.append("Observer callbacks are still detected structurally (subject invokes them on its observers), independent of "
             "name. SWS/Copilot (`notify`) and SWS/Gemini (`onLogEvent`) Observer O2/O3/O4 remain resolved in v4, and the "
             "synthetic guard `A-not-rebroken` (callback `ping`) passes. No name-based callback detection was reintroduced.\n")

    # audit list
    S.append("## Audit — every substring/identifier check found, and its disposition (Fix G)\n")
    S.append("| Location | Before | Action |\n|---|---|---|")
    S.append("| Strategy `execute` | `name in m.body` (substring; `\"pay\"` in `\"payment\"`) | → `_calls_method` (whole-token call) |")
    S.append("| Strategy `setter` | `m.name.lower().startswith(\"set\")` | → `_has_verb_prefix(name,\"set\")` (camelCase verb) |")
    S.append("| Composite `is_add`/`is_remove` | `startswith(\"add\")` / `startswith(\"remove\")` | → `_has_verb_prefix` |")
    S.append("| Composite `composites` | `\"add\" in name.lower() or \"remove\" in name.lower()` (substring) | → `_has_verb_prefix` |")
    S.append("| Composite `is_add_child`/`is_remove_child` | `startswith(...)` | → `_has_verb_prefix` |")
    S.append("| Singleton `accesses_field` | `f.name in m.body` (substring) | → `_mentions_token` (whole-token) |")
    S.append("| Factory `\"abstract\" in m.modifiers` | set membership | left (exact, not substring) |")
    S.append("| Observer `\"Observer\" in t.implements` (×2) | list membership of an exact interface name | left (exact; correctly does NOT match `TransactionObserver`) |")
    S.append("| Singleton `\"private\"/\"static\" in m.modifiers/f.modifiers` (×3) | set membership | left (exact, not substring) |")
    S.append("| Observer callback detection (Fix A) | already structural (subject-invokes + reads param) | left — NOT reverted to names |")
    S.append("")
    S.append("Every substring-containment identifier test (`X in body` / `X in name`) was converted to whole-token or "
             "exact-call matching. Set/list membership checks (`X in modifiers` / `X in implements`) are already exact and "
             "were left unchanged.\n")

    # synthetic
    S.append("## Synthetic generality tests — all 10 pass (`synthetic_generality_tests.py`)\n")
    S.append("| Test | Result |\n|---|:--:|")
    for t in ["A: observer callback `ping` in notify loop → O2/O3/O4 pass",
              "B: `extends Observable` + `implements Observer` → O1/O2 pass",
              "D: Strategy-only (no part-whole) → C1/C4/C5 = 0",
              "D: genuine part-whole → C1..C5 = 1",
              "E: factory method with `throws` → F1 & F4 pass",
              "**F: method-local var NOT a field** (0 Foo fields)",
              "**F: genuine class-scope field kept** (1 Foo field)",
              "**G: `pay` does NOT match inside `payment`/`PaymentFactory`**",
              "**G: `pay(` matches; addChild yes / address no**",
              "**A-not-rebroken: `ping` callback still detected after Fix G**"]:
        S.append("| {} | ✅ |".format(t))
    S.append("")

    # remaining classification
    S.append("## Every remaining disagreement ({}), classified (your step 4)\n".format(len(d4)))
    counts = {}
    for _, (c, _) in REMAIN.items():
        counts[c] = counts.get(c, 0) + 1
    S.append("| Category | Count |\n|---|--:|")
    for c in ["KIM", "DEFER-F4", "DEFER-S3", "AMBIG", "REGRESS"]:
        S.append("| {} | {} |".format(CATLABEL[c], counts.get(c, 0)))
    S.append("")
    S.append("| Case | LLM | Pattern | Prop | Kim | Mine | Category | Why |\n|---|---|---|---|:--:|:--:|---|---|")
    for key in sorted(d4, key=skey):
        cat, why = REMAIN[key]
        row = next(r for r in V4["property_comparison"]
                   if (r["case_study"], r["llm"], r["pattern"], r["property"]) == key)
        S.append("| {} | {} | {} | {} | {} | {} | {} | {} |".format(
            key[0], key[1], PAT_LABEL[key[2]], key[3],
            "S" if row["kim"] == "satisfied" else "·",
            "S" if row["mine"] == "satisfied" else "·",
            cat, why.replace("|", "\\|")))
    S.append("")
    S.append("**No genuine remaining bug in the pattern predicates except the one flagged G1 predicate gap.** "
             "Everything else is Kim-side, an explicitly deferred definitional choice, or one arithmetic ambiguity.\n")

    S.append("\n---\n\n*Generated by `validation/make_report_v4.py`. Scorer changes confined to the fact-extraction "
             "layer (Fixes F, G); see `piqs_service_fix_pass3.diff`. No pattern-predicate logic was changed; the G1 "
             "holder-idiom gap is flagged for a decision.*\n")

    open(OUT, "w").write("\n".join(S))
    print("Wrote", OUT)
    print("resolved:", len(resolved), "new:", len(new), "remaining:", len(d4), "classified:", len(REMAIN))
    print("protected drops:", [p for p, _, _ in drops])
    assert set(REMAIN.keys()) == d4, "classification mismatch: %s" % (set(REMAIN) ^ d4)


if __name__ == "__main__":
    build()
