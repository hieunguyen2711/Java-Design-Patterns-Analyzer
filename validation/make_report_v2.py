"""Assemble validation/kim_replication_report_v2.md: before/after comparison of the
interface-as-abstract-role fix. Reads the v1 snapshots and the current (v2) outputs.
"""

import json
import os

PROJECT = "/Users/hieunguyen/Documents/Coding Projects/DP Recognition Backend"
V1 = json.load(open(os.path.join(PROJECT, "validation/kim_comparison_v1.json")))
V2 = json.load(open(os.path.join(PROJECT, "validation/kim_comparison.json")))
RAW2 = json.load(open(os.path.join(PROJECT, "validation/kim_replication_raw.json")))
OUT = os.path.join(PROJECT, "validation/kim_replication_report_v2.md")

LLM_ORDER = ["ChatGPT", "Claude", "Copilot", "Gemini", "Meta"]
PAT_ORDER = {"factory-method": 0, "strategy": 1, "composite": 2, "observer": 3, "singleton": 4}
PAT_LABEL = {"factory-method": "Factory", "strategy": "Strategy", "composite": "Composite",
             "observer": "Observer", "singleton": "Singleton"}
PROPS = ["F1", "F2", "F3", "F4", "F5", "S1", "S2", "S3", "S4",
         "C1", "C2", "C3", "C4", "C5", "O1", "O2", "O3", "O4", "G1"]


def dis(c):
    return {(r["case_study"], r["llm"], r["pattern"], r["property"]) for r in c["property_comparison"] if not r["match"]}


def skey(t):
    return (t[0], LLM_ORDER.index(t[1]), PAT_ORDER[t[2]], t[3])


# Classification of the REMAINING (v2) disagreements.
# DELIBERATE = intentional simple-factory rejection (disagreement we WANT)
# KIM        = Kim's published number is lenient/internally inconsistent (not our bug)
# BUG        = a separate, unrelated cause (NOT the interface issue) -- fix proposed, not applied
# AMBIG      = genuine ambiguity in the property definition
REMAIN = {
    ("POSS","ChatGPT","strategy","S3"): ("BUG","S3 rejects strategy-as-parameter (context passes strategy as a method arg, not a stored field/setter). SEPARATE cause; not fixed."),
    ("POSS","ChatGPT","composite","C5"): ("BUG","C5 uniform check keys off an arbitrary abstract_components[0]. SEPARATE cause; not fixed."),
    ("POSS","Claude","factory-method","F4"): ("AMBIG","Kim marks F4 failed, but F2/F3/F4 are all weight 3 and arithmetically indistinguishable; the label is prose-derived. My F4 passes (createPayment returns new CashPayment)."),
    ("POSS","Claude","composite","C5"): ("BUG","C5 uniform check (arbitrary component[0]). SEPARATE cause; not fixed."),
    ("POSS","Copilot","factory-method","F4"): ("BUG","Parser drops `createPayment(...) throws Exception {` (throws clause), so its Payment return type is invisible and F4 cannot fire. SEPARATE cause (parser); not fixed."),
    ("POSS","Copilot","composite","C1"): ("BUG","Composite counts any interface (Strategy `Payment`, Observer) as a component; no real Composite exists. SEPARATE cause; not fixed."),
    ("POSS","Copilot","composite","C4"): ("BUG","Register.addSale/addInventory mislabeled a composite. SEPARATE cause; not fixed."),
    ("POSS","Gemini","composite","C1"): ("BUG","Interfaces counted as components; no real Composite. SEPARATE cause; not fixed."),
    ("POSS","Gemini","composite","C4"): ("BUG","Spurious composite/leaf. SEPARATE cause; not fixed."),
    ("POSS","Gemini","observer","O1"): ("KIM","Kim's numeric O1=satisfied is impossible: no abstract subject exists (ItemInventory is concrete). My O1=not satisfied matches the code."),
    ("POSS","Gemini","observer","O2"): ("KIM","`interface InventoryObserver{void update}` exists, so O2 is defensibly satisfied; Kim's numeric O2=fail contradicts the code."),
    ("POSS","Gemini","observer","O3"): ("KIM","notifyObservers iterates and calls update(); O3 defensibly satisfied. Kim's numeric O3=fail contradicts the code."),
    ("POSS","Gemini","observer","O4"): ("KIM","Register implements update(); O4 defensibly satisfied. Kim's numeric O4=fail contradicts the code."),
    ("POSS","Meta","composite","C5"): ("BUG","C5 uniform check (arbitrary component[0]). SEPARATE cause; not fixed."),
    ("SWS","ChatGPT","factory-method","F5"): ("BUG","F5 counts Strategy implementers as 'products' (Wallet has no product interface). SEPARATE cause (product definition); not fixed."),
    ("SWS","ChatGPT","observer","O3"): ("BUG","O3 rejects single-observer direct notification (`auditLog.update(...)`, no collection/loop). SEPARATE cause (observer notify shape); not fixed."),
    ("SWS","Claude","factory-method","F4"): ("BUG","F4 only accepts abstract-typed products; createWallet returns the concrete `Wallet`. SEPARATE cause (concrete product); not fixed."),
    ("SWS","Claude","factory-method","F5"): ("BUG","F5 counts Strategy implementers as products. SEPARATE cause; not fixed."),
    ("SWS","Copilot","factory-method","F1"): ("KIM","Copilot's SWS genuinely has `abstract class WalletFactory` + `ConcreteWalletFactory extends WalletFactory`, so an abstract creator exists (my F1 now = satisfied). Kim's F1=fail while F2/F3/F4=pass is internally inconsistent."),
    ("SWS","Copilot","factory-method","F4"): ("BUG","createWallet returns concrete `Wallet`; F4 only accepts abstract-typed products. SEPARATE cause; not fixed."),
    ("SWS","Copilot","factory-method","F5"): ("BUG","F5 counts Strategy implementers as products. SEPARATE cause; not fixed."),
    ("SWS","Copilot","strategy","S3"): ("BUG","S3 rejects strategy-as-parameter (Wallet.performTransaction takes the strategy as an arg). SEPARATE cause; not fixed."),
    ("SWS","Copilot","observer","O2"): ("BUG","Observer callback is `notify(Transaction)`, not `update`; O2 hard-codes the name `update`. SEPARATE cause (method naming); not fixed."),
    ("SWS","Copilot","observer","O3"): ("BUG","Wallet.notifyObservers calls `observer.notify(...)`, but O3 requires a literal `.update(`. SEPARATE cause (naming); not fixed."),
    ("SWS","Copilot","observer","O4"): ("BUG","No observer_types found (callback named `notify`), so O4 fails. SEPARATE cause (naming); not fixed."),
    ("SWS","Gemini","factory-method","F4"): ("BUG","createWallet returns concrete `Wallet`. SEPARATE cause (concrete product); not fixed."),
    ("SWS","Gemini","factory-method","F5"): ("BUG","F5 counts Strategy implementers as products. SEPARATE cause; not fixed."),
    ("SWS","Gemini","observer","O2"): ("BUG","Observer callback is `onLogEvent`, not `update`; O2 hard-codes `update`. SEPARATE cause (naming); not fixed."),
    ("SWS","Meta","factory-method","F4"): ("KIM","Meta's SWS has NO factory class; Kim's F4=satisfied is indefensible. My F4=not satisfied matches the code."),
    ("SWS","Meta","factory-method","F5"): ("BUG","F5 counts Strategy implementers as products. SEPARATE cause; not fixed."),
    ("SWS","Meta","observer","O1"): ("BUG","`AuditLog extends Observable` (java.util.Observable); the JDK subject framework is invisible. SEPARATE cause (JDK framework); not fixed."),
    ("SWS","Meta","observer","O2"): ("BUG","Uses java.util.Observer via Observable; no hand-rolled `update` interface. SEPARATE cause (JDK framework); not fixed."),
}
CATLABEL = {
    "DELIBERATE": "Deliberate — simple/static factory, not GoF (intended disagreement)",
    "KIM": "Kim lenient / numbers internally inconsistent (not our bug)",
    "BUG": "Genuine remaining issue — SEPARATE cause, fix proposed, NOT applied",
    "AMBIG": "Genuine ambiguity in the property definition",
}


def build():
    S = []
    h1, h2 = V1["headline"], V2["headline"]
    d1, d2 = dis(V1), dis(V2)
    resolved = d1 - d2
    regress = d2 - d1

    S.append("# PIQS Scorer — Interface-as-Abstract-Role Fix: Before/After (v2)\n")
    S.append("**One conceptual change applied:** a Java `interface` now counts as fulfilling an "
             "*abstract* pattern role wherever the checker previously required an `abstract class`, and "
             "`implements` counts like `extends`. Concretely this reworked Factory Method **F1/F2/F3** "
             "(and the derived `isCreator`/`overrides`) and Observer **O1**. F1 was additionally anchored to "
             "the *creator role* so that static/switch **simple factories are deliberately rejected** as "
             "not-GoF. Nothing else was touched — no weights, formulas, thresholds, and none of the "
             "already-100% predicates.\n")
    S.append("Diff: `validation/piqs_service_fix.diff` (+63 / −9 lines, one file). "
             "Old outputs preserved as `*_v1.*`.\n")

    S.append("## Headline: before → after\n")
    S.append("| Metric | Before (v1) | After (v2) | Δ |\n|---|--:|--:|--:|")
    S.append("| Property-level agreement | {}/160 ({}%) | {}/160 ({}%) | **+{} pts** |".format(
        h1["agreed"], h1["agreement_pct"], h2["agreed"], h2["agreement_pct"],
        round(h2["agreement_pct"]-h1["agreement_pct"], 1)))
    S.append("| Units matching all 3 scores exactly | {}/40 | {}/40 | +{} |".format(
        h1["units_exact_match_all3"], h2["units_exact_match_all3"],
        h2["units_exact_match_all3"]-h1["units_exact_match_all3"]))
    S.append("| Disagreements | {} | {} | −{} |".format(len(d1), len(d2), len(d1)-len(d2)))
    S.append("")
    S.append("**{} disagreements resolved, {} new regressions.** The change is strictly monotonic — it only "
             "flipped wrong verdicts to correct ones, never the reverse. Resolved by property: "
             "F1 ×6, F2 ×6, F3 ×7, O1 ×3.\n".format(len(resolved), len(regress)))

    S.append("### Expected vs actual (your predictions)\n")
    S.append("- *“Factory Method agreement should rise sharply (was 38%).”* ✅ Factory F1 30%→90%, "
             "F2 40%→100%, F3 30%→100%. (F4/F5 unchanged — those are separate causes, see below.)\n")
    S.append("- *“Observer O1/O2 should improve (were 50% / 60%).”* ✅ **O1 50%→80%.** ❌ **O2 unchanged at 60%** — "
             "see the important note below: O2 is *not* broken by the interface issue.\n")
    S.append("- *“A few Factory cases (simple factories: ChatGPT POSS, possibly Meta) should STILL disagree.”* "
             "❌ **This did not happen — and it is good news, explained next.**\n")
    S.append("- *“Strategy, Singleton, Composite-core unchanged.”* ✅ All identical to v1.\n")

    # ---- Reliability before/after ----
    S.append("## Per-property reliability: before → after\n")
    S.append("| Prop | Before | After | Reliable now (≥80%)? |\n|---|--:|--:|:--:|")
    for p in PROPS:
        r1 = V1["reliability"].get(p); r2 = V2["reliability"].get(p)
        flag = "✅" if r2["reliable"] else "❌"
        changed = " ⬆" if r2["agreement_pct"] > r1["agreement_pct"] else ""
        S.append("| {} | {}% | {}%{} | {} |".format(p, r1["agreement_pct"], r2["agreement_pct"], changed, flag))
    S.append("")
    still = [p for p in PROPS if not V2["reliability"][p]["reliable"]]
    S.append("Still < 80% after the fix (all due to **separate, unrelated causes** left unfixed per your "
             "one-change constraint): **" + ", ".join(still) + "**.\n")

    # ---- The simple-factory finding ----
    S.append("## ⚠️ Important finding: the simple-factory rejection AGREES with Kim (it does not disagree)\n")
    S.append("Your Change 2 assumed our checker was *stricter* than Kim on the static/switch simple factories "
             "(ChatGPT POSS, Copilot POSS) and that rejecting them would keep us disagreeing with Kim. "
             "**The data shows the opposite.** Kim *also* fails F1 on both simple factories (his Table 13 / derived "
             "failing-property set lists “F1 fails” for ChatGPT POSS and Copilot POSS). So:\n")
    S.append("- **Before the fix**, our checker *wrongly passed* F1 on ChatGPT POSS (it matched the unrelated "
             "`abstract class SaleComponent`). That was the disagreement — we were too *loose*, not too strict.\n")
    S.append("- **After the fix**, F1 correctly fails on both simple factories, which **matches Kim**. ChatGPT POSS "
             "Factory now scores **80.00 / 84.62 / 81.85 — identical to Kim's published numbers.**\n")
    S.append("- **Net: there are ZERO remaining disagreements attributable to the simple-factory rejection.** "
             "The deliberate design decision still stands (and is documented in the code comment you asked for), "
             "but on Kim's corpus it *converges with* Kim rather than diverging. **There is nothing to cite as an "
             "intentional definitional difference on the simple factories** — Kim already treated them the same way.\n")
    S.append("> Per your constraint “if you find a second, unrelated cause of disagreement, STOP and report it”: "
             "this reversed premise is that report. I still implemented the rejection exactly as you specified "
             "(it is correct and it is what your criterion “no creator role played by subclasses” implies); I am only "
             "flagging that its *relationship to Kim* is agreement, not disagreement.\n")

    # ---- Score-level before/after for factory + O1 rows ----
    S.append("## Score-level: the units that moved\n")
    v2raw = {(r["case_study"], r["llm"], r["pattern"]): r for r in RAW2["results"]}
    sc1 = {(r["case_study"], r["llm"], r["pattern"]): r for r in V1["score_comparison"]}
    sc2 = {(r["case_study"], r["llm"], r["pattern"]): r for r in V2["score_comparison"]}
    S.append("| Case | LLM | Pattern | Kim PIQS | v1 PIQS | v2 PIQS | v2 exact? |\n|---|---|---|--:|--:|--:|:--:|")
    for key in sorted(sc2.keys(), key=lambda k: (k[0], LLM_ORDER.index(k[1]), PAT_ORDER[k[2]])):
        a, b = sc1[key], sc2[key]
        if abs(a["my_piqs"]-b["my_piqs"]) < 0.005 and b["d_piqs"] > 0.005 and a["d_piqs"] > 0.005:
            continue  # unchanged and still off -> skip to keep table focused
        if a["my_piqs"] == b["my_piqs"] and b["d_piqs"] == 0 and a["d_piqs"] == 0:
            continue  # unchanged and already exact -> skip
        exact = "✅" if (b["d_psr"] == 0 and b["d_cpc"] == 0 and b["d_piqs"] == 0) else ""
        S.append("| {} | {} | {} | {:.2f} | {:.2f} | {:.2f} | {} |".format(
            key[0], key[1], PAT_LABEL[key[2]], b["kim_piqs"], a["my_piqs"], b["my_piqs"], exact))
    S.append("\n(Rows omitted where v1 and v2 are identical.) Full per-unit data: `kim_comparison.json` (v2) "
             "and `kim_comparison_v1.json`.\n")

    # ---- Remaining disagreements classified ----
    S.append("## Every remaining disagreement, classified (per your Step 5)\n")
    counts = {}
    for _, (cat, _) in REMAIN.items():
        counts[cat] = counts.get(cat, 0) + 1
    S.append("| Category | Count |\n|---|--:|")
    for cat in ["DELIBERATE", "KIM", "AMBIG", "BUG"]:
        S.append("| {} | {} |".format(CATLABEL[cat], counts.get(cat, 0)))
    S.append("")
    S.append("**Deliberate simple-factory disagreements: 0** (see finding above). "
             "The remaining {} split into Kim-side problems and separate unrelated causes I did **not** touch:\n".format(len(d2)))
    S.append("| Case | LLM | Pattern | Prop | Kim | Mine | Category | Note |\n|---|---|---|---|:--:|:--:|---|---|")
    for key in sorted(d2, key=skey):
        cat, reason = REMAIN[key]
        row = next(r for r in V2["property_comparison"]
                   if (r["case_study"], r["llm"], r["pattern"], r["property"]) == key)
        S.append("| {} | {} | {} | {} | {} | {} | {} | {} |".format(
            key[0], key[1], PAT_LABEL[key[2]], key[3],
            "S" if row["kim"] == "satisfied" else "·",
            "S" if row["mine"] == "satisfied" else "·",
            cat, reason.replace("|", "\\|")))
    S.append("")

    # ---- proposed (unapplied) fixes for the separate causes ----
    S.append("### Proposed fixes for the separate causes (NOT applied — for your review)\n")
    S.append("These are distinct from the interface issue and were left untouched:\n")
    S.append("- **F4 (concrete-typed products)** — SWS Claude/Copilot/Gemini: allow a factory method's product "
             "type to be a concrete class, not only an abstract type. **F4 (parser)** — POSS Copilot: fix "
             "`_METHOD_SIG_RE` to accept a `throws` clause so factory methods aren't dropped.\n")
    S.append("- **F5 (product definition)** — anchor 'product' to the type the factory method returns, so Strategy/"
             "Observer implementers stop counting as products (all 5 SWS false positives).\n")
    S.append("- **S3 (context)** — accept a class that uses a strategy via parameter/local, not only a stored field/setter.\n")
    S.append("- **C1/C4/C5 (Composite)** — anchor the component to a real part–whole hierarchy; compare the actual "
             "component's API against the specific composite/leaf (not `abstract_components[0]`).\n")
    S.append("- **O2/O3/O4 (Observer naming + JDK)** — do not hard-code the callback name `update`; recognise "
             "`notify`/`onLogEvent`/`java.util.Observer`, single-observer direct notification, and `Observable`.\n")
    S.append("- **Kim-side (cite, don't fix)** — POSS Gemini Observer; SWS Copilot F1; SWS Meta F4 are Kim's "
             "internally-inconsistent cells; our (now-correct) verdicts disagree with his numbers on purpose.\n")

    S.append("\n---\n\n*Generated by `validation/make_report_v2.py`. Inputs: v1 snapshots + current v2 outputs. "
             "Scorer change limited to the interface-as-abstract-role concept; see `piqs_service_fix.diff`.*\n")

    open(OUT, "w").write("\n".join(S))
    print("Wrote", OUT)
    print("resolved:", len(resolved), "regressions:", len(regress),
          "remaining:", len(d2), "classified:", len(REMAIN))
    assert len(regress) == 0, "unexpected regression!"
    assert set(REMAIN.keys()) == d2, "classification set != remaining disagreements"


if __name__ == "__main__":
    build()
