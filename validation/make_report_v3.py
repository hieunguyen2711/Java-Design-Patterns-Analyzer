"""Assemble validation/kim_replication_report_v3.md: before(v2)/after(v3) comparison of
the pass-2 structural fixes (A observer callback, B JDK Observable/Observer, C F5 product,
D Composite hierarchy, E throws-parser). Reads v2 snapshots and current v3 outputs.
"""

import json
import os

PROJECT = "/Users/hieunguyen/Documents/Coding Projects/DP Recognition Backend"
V2 = json.load(open(os.path.join(PROJECT, "validation/kim_comparison_v2.json")))
V3 = json.load(open(os.path.join(PROJECT, "validation/kim_comparison.json")))
RAW3 = json.load(open(os.path.join(PROJECT, "validation/kim_replication_raw.json")))
OUT = os.path.join(PROJECT, "validation/kim_replication_report_v3.md")

LLM_ORDER = ["ChatGPT", "Claude", "Copilot", "Gemini", "Meta"]
PAT_ORDER = {"factory-method": 0, "strategy": 1, "composite": 2, "observer": 3, "singleton": 4}
PAT_LABEL = {"factory-method": "Factory", "strategy": "Strategy", "composite": "Composite",
             "observer": "Observer", "singleton": "Singleton"}
PROPS = ["F1", "F2", "F3", "F4", "F5", "S1", "S2", "S3", "S4",
         "C1", "C2", "C3", "C4", "C5", "O1", "O2", "O3", "O4", "G1"]
PROTECTED = ["F1", "F2", "F3", "S1", "S2", "S4", "C2", "C3", "G1", "O1"]  # must-not-drop (S3 excluded)


def dis(c):
    return {(r["case_study"], r["llm"], r["pattern"], r["property"]) for r in c["property_comparison"] if not r["match"]}


def skey(t):
    return (t[0], LLM_ORDER.index(t[1]), PAT_ORDER[t[2]], t[3])


# Classification of the 14 REMAINING (v3) disagreements.
# KIM   = Kim's published number contradicts the code (our verdict correct) -> cite, never match
# DEFER = definitional choice the author explicitly deferred (F4-concrete, S3) -> leave
# AMBIG = genuine ambiguity in the property definition
REMAIN = {
    ("POSS","Claude","factory-method","F4"): ("AMBIG","F2/F3/F4 are all weight 3 and arithmetically indistinguishable; Kim's 'F4 fails' label is prose-derived. My F4=satisfied (createPayment returns new CashPayment)."),
    ("POSS","Gemini","observer","O1"): ("KIM","No abstract subject exists (ItemInventory concrete, no Subject interface); Kim's numeric O1=satisfied is impossible. My O1=not satisfied matches the code."),
    ("POSS","Gemini","observer","O2"): ("KIM","`interface InventoryObserver{void update}` exists and is notified; O2 defensibly satisfied. Kim's numeric O2=fail contradicts the code."),
    ("POSS","Gemini","observer","O3"): ("KIM","ItemInventory loops observers calling update(); O3 defensibly satisfied. Kim's numeric O3=fail contradicts the code."),
    ("POSS","Gemini","observer","O4"): ("KIM","Register implements InventoryObserver.update(); O4 defensibly satisfied. Kim's numeric O4=fail contradicts the code."),
    ("SWS","Claude","factory-method","F4"): ("DEFER","createWallet returns the CONCRETE `Wallet`; whether a concrete-typed product satisfies F4 is the deferred F4-concrete definitional choice. Left as-is per instructions."),
    ("SWS","Copilot","factory-method","F1"): ("KIM","`abstract class WalletFactory` + `ConcreteWalletFactory extends WalletFactory` genuinely exist (my F1=satisfied). Kim's F1=fail while F2/F3/F4=pass is internally inconsistent."),
    ("SWS","Copilot","factory-method","F4"): ("DEFER","createWallet returns concrete `Wallet` (deferred F4-concrete choice). Left as-is."),
    ("SWS","Copilot","strategy","S3"): ("DEFER","Wallet.performTransaction receives the strategy as a parameter, not a stored field/setter; the S3 strategy-as-parameter choice was explicitly deferred. Left as-is."),
    ("SWS","Gemini","factory-method","F4"): ("DEFER","createWallet returns concrete `Wallet` (deferred F4-concrete choice). Left as-is."),
    ("SWS","Gemini","observer","O3"): ("KIM","AuditLog holds List<AuditLogObserver>, loops calling onLogEvent(); ConsoleLogger is registered in main (`user.auditLog.addObserver(new ConsoleLogger())`). The observer is complete AND wired; O3 defensibly satisfied. Kim's O3=fail contradicts the code."),
    ("SWS","Gemini","observer","O4"): ("KIM","ConsoleLogger implements AuditLogObserver.onLogEvent(); O4 defensibly satisfied. Kim's O4=fail contradicts the code."),
    ("SWS","Meta","factory-method","F4"): ("KIM","Meta's SWS has NO factory class; Kim's F4=satisfied is indefensible. My F4=not satisfied matches the code."),
    ("SWS","Meta","observer","O2"): ("KIM","`AuditLog extends Observable` but NO class implements Observer and no custom observer interface exists, so structurally there is no abstract observer. Kim's O2=satisfied (crediting the imported-but-unimplemented JDK Observer) is lenient; our O2=not satisfied is defensible."),
}
CATLABEL = {
    "KIM": "Kim's published number contradicts the code (our verdict correct) — cite, do not match",
    "DEFER": "Definitional choice the author deferred (F4-concrete / S3) — left unchanged",
    "AMBIG": "Genuine ambiguity in the property definition",
}


def build():
    S = []
    h2, h3 = V2["headline"], V3["headline"]
    d2, d3 = dis(V2), dis(V3)
    resolved = d2 - d3
    new = d3 - d2

    S.append("# PIQS Scorer — Pass 2 (structural bug fixes A–E): Before/After (v3)\n")
    S.append("**Five structural fixes applied, all keyed to code STRUCTURE (never to Kim's class/method/file names):**\n")
    S.append("- **A** — Observer callback detected by role (subject invokes it on its observers), not the hard-coded name `update`. Now `notify`, `onLogEvent`, … all work.\n")
    S.append("- **B** — JDK Observer framework recognised: `extends Observable` ⇒ abstract subject; `implements Observer` ⇒ abstract observer.\n")
    S.append("- **C** — F5 'product' anchored to the type a factory method *returns*, so Strategy/Observer implementers no longer count as products.\n")
    S.append("- **D** — Composite C1/C4/C5 anchored to a real part–whole hierarchy (a concrete implementor that holds a collection of the component type); C5 compares the *actual* component's API. C2/C3 unchanged.\n")
    S.append("- **E** — method-signature parser accepts an optional `throws` clause, so factory methods declared `throws` are parsed and their return type captured.\n")
    S.append("\nDiffs: pass-2 only `validation/piqs_service_fix_pass2.diff`; cumulative `git diff`. Prior outputs preserved as `*_v2.*`.\n")

    S.append("## Headline: v2 → v3\n")
    S.append("| Metric | v2 | v3 | Δ |\n|---|--:|--:|--:|")
    S.append("| Property-level agreement | {}/160 ({}%) | {}/160 ({}%) | **+{} pts** |".format(
        h2["agreed"], h2["agreement_pct"], h3["agreed"], h3["agreement_pct"],
        round(h3["agreement_pct"] - h2["agreement_pct"], 1)))
    S.append("| Units matching all 3 scores exactly | {}/40 | {}/40 | +{} |".format(
        h2["units_exact_match_all3"], h3["units_exact_match_all3"],
        h3["units_exact_match_all3"] - h2["units_exact_match_all3"]))
    S.append("| Disagreements | {} | {} | −{} |".format(len(d2), len(d3), len(d2) - len(d3)))
    S.append("")
    S.append("Across all three passes: **66.2% → 80.0% → 91.2%**.\n")
    S.append("**{} disagreements resolved; {} new (both are Kim-side — see below).**\n".format(len(resolved), len(new)))

    S.append("### Your predictions vs actual\n")
    S.append("- *Observer callback other than `update`, in a notify loop → O2/O3/O4 pass.* ✅ (SWS Copilot `notify`, Gemini `onLogEvent`).\n")
    S.append("- *`extends Observable` + `implements Observer` → O1/O2 pass.* ✅ (synthetic test; SWS Meta O1 resolved via Observable).\n")
    S.append("- *Strategy interface but no Composite → C1/C4/C5 do NOT fire.* ✅ (Copilot/Gemini POSS; synthetic negative control).\n")
    S.append("- *Factory method with a `throws` clause → return type captured, F4 evaluable.* ✅ (POSS Copilot F4 resolved; synthetic test).\n")
    S.append("- Reliability lifts: **F5 50%→100%, C1 60%→100%, C4 60%→100%, C5 40%→100%, O2 60%→80%, O3 70%→80%.**\n")

    # reliability v2->v3
    S.append("## Per-property reliability: v2 → v3\n")
    S.append("| Prop | v2 | v3 | Reliable (≥80%)? | In must-not-drop set |\n|---|--:|--:|:--:|:--:|")
    for p in PROPS:
        r2 = V2["reliability"][p]["agreement_pct"]
        r3 = V3["reliability"][p]["agreement_pct"]
        arrow = " ⬆" if r3 > r2 else (" ⬇" if r3 < r2 else "")
        rel = "✅" if V3["reliability"][p]["reliable"] else "❌"
        prot = "yes" if p in PROTECTED else ("— (S3 deferred)" if p == "S3" else "—")
        S.append("| {} | {}% | {}%{} | {} | {} |".format(p, r2, r3, arrow, rel, prot))
    S.append("")
    still = [p for p in PROPS if not V3["reliability"][p]["reliable"]]
    S.append("Only **{}** remains < 80% — driven by the deferred F4-concrete choice and one ambiguity (all analysed below).\n".format(", ".join(still) or "nothing"))

    # zero-regression confirmation
    drops = [p for p in PROTECTED if V3["reliability"][p]["agreement_pct"] < V2["reliability"][p]["agreement_pct"]]
    S.append("### Zero-regression check (your step 3)\n")
    S.append("Protected set (S1,S2,S4,C2,C3,G1,F1,F2,F3,O1): **{}**. ".format(
        "no drops ✅" if not drops else "DROPPED: " + ", ".join(drops)))
    S.append("O1 in fact rose 80%→90%. Every already-100% property stayed 100%.\n")

    # moved score units
    S.append("## Score-level: units that moved (v2 → v3)\n")
    sc2 = {(r["case_study"], r["llm"], r["pattern"]): r for r in V2["score_comparison"]}
    sc3 = {(r["case_study"], r["llm"], r["pattern"]): r for r in V3["score_comparison"]}
    S.append("| Case | LLM | Pattern | Kim PIQS | v2 PIQS | v3 PIQS | v3 exact? |\n|---|---|---|--:|--:|--:|:--:|")
    for key in sorted(sc3, key=lambda k: (k[0], LLM_ORDER.index(k[1]), PAT_ORDER[k[2]])):
        a, b = sc2[key], sc3[key]
        if abs(a["my_piqs"] - b["my_piqs"]) < 0.005:
            continue
        exact = "✅" if (b["d_psr"] == 0 and b["d_cpc"] == 0 and b["d_piqs"] == 0) else ""
        S.append("| {} | {} | {} | {:.2f} | {:.2f} | {:.2f} | {} |".format(
            key[0], key[1], PAT_LABEL[key[2]], b["kim_piqs"], a["my_piqs"], b["my_piqs"], exact))
    S.append("")

    # remaining classified
    S.append("## Every remaining disagreement ({}), classified (your step 4)\n".format(len(d3)))
    counts = {}
    for _, (c, _) in REMAIN.items():
        counts[c] = counts.get(c, 0) + 1
    S.append("| Category | Count |\n|---|--:|")
    for c in ["KIM", "DEFER", "AMBIG"]:
        S.append("| {} | {} |".format(CATLABEL[c], counts.get(c, 0)))
    S.append("")
    S.append("**No 'genuine remaining bug' in the fixed buckets** — every remaining disagreement is either a Kim-side error, an explicitly deferred definitional choice, or one arithmetic ambiguity.\n")
    S.append("| Case | LLM | Pattern | Prop | Kim | Mine | Category | Why |\n|---|---|---|---|:--:|:--:|---|---|")
    for key in sorted(d3, key=skey):
        cat, why = REMAIN[key]
        row = next(r for r in V3["property_comparison"]
                   if (r["case_study"], r["llm"], r["pattern"], r["property"]) == key)
        S.append("| {} | {} | {} | {} | {} | {} | {} | {} |".format(
            key[0], key[1], PAT_LABEL[key[2]], key[3],
            "S" if row["kim"] == "satisfied" else "·",
            "S" if row["mine"] == "satisfied" else "·",
            cat, why.replace("|", "\\|")))
    S.append("")
    S.append("The **SWS Gemini O3/O4** and **POSS Gemini O1–O4** disagreements are the automated scorer correctly detecting complete, wired Observer implementations that Kim's numeric tables mark as failing — i.e. the scorer disagreeing *rightly* with flawed manual cells. Cite these; do not chase them.\n")

    # sixth-cause flag
    S.append("## ⚠️ Flagged: one incidental change + a newly-surfaced latent cause (your STOP-and-report rule)\n")
    S.append("**S3 for POSS/ChatGPT flipped fail→pass (S3 overall 80%→90%) — but for the WRONG reason, and I did not intend to touch S3.** Root cause: Fix E now lets `main()` (declared `throws Exception`) be parsed, which exposed two *pre-existing latent parser bugs*:\n")
    S.append("1. **Local variables are mis-parsed as fields.** Inside `main`, `PaymentStrategy payment = PaymentFactory.getPaymentMethod(...)` is captured as a `PaymentStrategy` *field* of `RefactoredPOSChatGPT`, so `is_context`'s field check trips.\n")
    S.append("2. **Substring method-name matching.** `is_context`'s 'execute' check does `\"pay\" in method_body`, and `\"pay\"` occurs inside `\"payment\"`/`\"PaymentFactory\"`, so it matches spuriously.\n")
    S.append("Together these make `is_context` true → S3 passes, coincidentally agreeing with Kim. **This is not a real S3 fix.** Per your instruction I have *flagged, not fixed* it. Treat S3's genuine reliability as unchanged (the deferred strategy-as-parameter limitation still stands; SWS Copilot S3 still correctly fails).\n")
    S.append("**This is the distinct sixth cause you asked me to stop on:** latent parser imprecision — (a) local-variable-as-field extraction and (b) substring (not token) matching of method names. It is out of scope for pass 2; I recommend a dedicated pass to (i) restrict field extraction to class scope, and (ii) match method names as whole tokens. No further edits were made.\n")

    # synthetic tests
    S.append("## Synthetic generality tests (your step 5) — none from Kim's corpus\n")
    S.append("`validation/synthetic_generality_tests.py` — **all pass**:\n")
    S.append("| Test | Result |\n|---|:--:|")
    S.append("| Fix A: observer callback named `ping` in a notify loop → O2/O3/O4 pass | ✅ |")
    S.append("| Fix B: `extends Observable` + `implements Observer` → O1/O2 pass | ✅ |")
    S.append("| Fix D: Strategy interface, no part–whole → C1/C4/C5 = 0 (C2 leaf still 1, unchanged) | ✅ |")
    S.append("| Fix D: genuine part–whole (Dir holds List<Node>, File leaf) → C1..C5 = 1 | ✅ |")
    S.append("| Fix E: factory method `create() throws Exception` → F1 & F4 evaluable/pass | ✅ |")
    S.append("")

    S.append("## Per-fix result summary\n")
    S.append("| Fix | Predicates | Resolved (v2→v3) |\n|---|---|---|")
    S.append("| A — structural observer callback | O2, O3, O4 | SWS Copilot O2/O3/O4, SWS Gemini O2, SWS ChatGPT O3 |")
    S.append("| B — JDK Observable/Observer | O1, O2 | SWS Meta O1 |")
    S.append("| C — F5 product = factory return type | F5 | SWS ChatGPT/Claude/Copilot/Gemini/Meta F5 (all 5) |")
    S.append("| D — Composite real hierarchy | C1, C4, C5 | POSS Copilot/Gemini C1+C4; POSS ChatGPT/Claude/Meta C5 |")
    S.append("| E — throws-parser | F4 (+ incidental S3, flagged) | POSS Copilot F4 |")
    S.append("")
    S.append("*Generated by `validation/make_report_v3.py`. Scorer changes confined to structural rules for Fixes A–E; see `piqs_service_fix_pass2.diff`.*\n")

    open(OUT, "w").write("\n".join(S))
    print("Wrote", OUT)
    print("resolved:", len(resolved), "new:", len(new), "remaining:", len(d3), "classified:", len(REMAIN))
    assert set(REMAIN.keys()) == d3, "classification set != remaining disagreements: %s" % (set(REMAIN) ^ d3)
    assert not drops, "protected regression: %s" % drops


if __name__ == "__main__":
    build()
