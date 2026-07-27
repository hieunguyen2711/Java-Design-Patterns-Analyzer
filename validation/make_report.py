"""Assemble validation/kim_replication_report.md from kim_comparison.json and
kim_replication_raw.json. Tables are computed from data; the disagreement analysis and
recommendations are authored constants keyed to the code evidence gathered during review.
"""

import json
import os

PROJECT = "/Users/hieunguyen/Documents/Coding Projects/DP Recognition Backend"
CMP = json.load(open(os.path.join(PROJECT, "validation/kim_comparison.json")))
RAW = json.load(open(os.path.join(PROJECT, "validation/kim_replication_raw.json")))
OUT = os.path.join(PROJECT, "validation/kim_replication_report.md")

LLM_ORDER = ["ChatGPT", "Claude", "Copilot", "Gemini", "Meta"]
PAT_ORDER = {"factory-method": 0, "strategy": 1, "composite": 2, "observer": 3, "singleton": 4}
PAT_LABEL = {"factory-method": "Factory", "strategy": "Strategy", "composite": "Composite",
             "observer": "Observer", "singleton": "Singleton"}


def sort_key(r):
    return (r["case_study"], LLM_ORDER.index(r["llm"]), PAT_ORDER[r["pattern"]])

# ---- classification of every mismatch: (category, reason) --------------------
# categories: STRICT (too strict -> false positive), LOOSE (too loose -> false negative),
#             PARSE (parse failure), KIM (Kim numbers internally inconsistent), AMBIG (genuine ambiguity)
CAT = {
    "STRICT": "too strict → false positive (I fail code Kim accepted)",
    "LOOSE": "too loose → false negative (I pass code Kim rejected)",
    "PARSE": "source could not be parsed",
    "KIM": "Kim's published numbers internally inconsistent",
    "AMBIG": "genuine ambiguity in the property definition",
}
CLASS = {
    ("POSS","ChatGPT","factory-method","F1"): ("LOOSE","F1 matches ANY abstract class; it latched onto `abstract class SaleComponent` (Composite component). The real creator `PaymentFactory` is a concrete class."),
    ("POSS","ChatGPT","strategy","S3"): ("STRICT","is_context requires a stored strategy field or setter; here the strategy is a local var in main and passed as a parameter (RefactoredPOSChatGPT.java:47)."),
    ("POSS","ChatGPT","composite","C5"): ("STRICT","uniform check keys off abstract_components[0], which is an arbitrary interface (Strategy/Observer), not SaleComponent."),
    ("POSS","ChatGPT","observer","O1"): ("STRICT","abstract subject `InventorySubject` is an interface, but subject_candidates only includes kind=='class', so O1 can never see it."),
    ("POSS","Claude","factory-method","F1"): ("STRICT","creator is `interface PaymentFactory`; F1 requires an abstract class."),
    ("POSS","Claude","factory-method","F2"): ("STRICT","concrete factories use `implements PaymentFactory`; F2 only recognises `extends`."),
    ("POSS","Claude","factory-method","F3"): ("STRICT","override detection only follows `extends`, not interface `implements`."),
    ("POSS","Claude","factory-method","F4"): ("AMBIG","F2/F3/F4 all have weight 3 and are arithmetically indistinguishable; Kim's 'F4 fails' label is prose-derived (task warns prose is unreliable). My F4 passes (createPayment returns new CashPayment)."),
    ("POSS","Claude","composite","C5"): ("STRICT","uniform check keys off arbitrary abstract_components[0]."),
    ("POSS","Copilot","factory-method","F2"): ("STRICT","single static factory + product subclasses; F2 only recognises `extends`."),
    ("POSS","Copilot","factory-method","F3"): ("STRICT","override via interface not detected."),
    ("POSS","Copilot","factory-method","F4"): ("PARSE","`createPayment(...) throws Exception {` is not matched by the method regex (throws clause), so the method and its `Payment` return type are never seen; F4 cannot fire."),
    ("POSS","Copilot","composite","C1"): ("LOOSE","the Strategy `Payment` / Observer `InventoryObserver` interfaces are counted as abstract components; no real Composite exists."),
    ("POSS","Copilot","composite","C4"): ("LOOSE","Register (has addSale/addInventory) is mislabeled a composite and ByCash/ByCreditCard leaves; no real Composite exists."),
    ("POSS","Gemini","factory-method","F1"): ("STRICT","creator is `interface PaymentFactory`."),
    ("POSS","Gemini","factory-method","F2"): ("STRICT","factories use `implements`."),
    ("POSS","Gemini","factory-method","F3"): ("STRICT","override via interface not detected."),
    ("POSS","Gemini","composite","C1"): ("LOOSE","Payment/InventoryObserver interfaces counted as components; no real Composite."),
    ("POSS","Gemini","composite","C4"): ("LOOSE","spurious composite/leaf from unrelated classes."),
    ("POSS","Gemini","observer","O1"): ("KIM","Kim's numeric O1=satisfied is semantically impossible: there is NO abstract subject (ItemInventory is a concrete class, no Subject interface). My O1=not satisfied matches the code."),
    ("POSS","Gemini","observer","O2"): ("KIM","`interface InventoryObserver{void update(...)}` genuinely exists, so O2 is defensibly satisfied; Kim's numeric O2=fail contradicts the code."),
    ("POSS","Gemini","observer","O3"): ("KIM","ItemInventory.notifyObservers iterates observers and calls update(); O3 is defensibly satisfied. Kim's numeric O3=fail contradicts the code."),
    ("POSS","Gemini","observer","O4"): ("KIM","Register implements InventoryObserver.update(); O4 defensibly satisfied. Kim's numeric O4=fail contradicts the code."),
    ("POSS","Meta","factory-method","F1"): ("STRICT","creator is `interface PaymentFactory`."),
    ("POSS","Meta","factory-method","F2"): ("STRICT","PaymentFactoryImpl uses `implements`."),
    ("POSS","Meta","factory-method","F3"): ("STRICT","override via interface not detected."),
    ("POSS","Meta","composite","C5"): ("STRICT","uniform check keys off arbitrary abstract_components[0]."),
    ("POSS","Meta","observer","O1"): ("STRICT","abstract subject `InventorySubject` is an interface, invisible to subject_candidates (kind=='class' only)."),
    ("SWS","ChatGPT","factory-method","F2"): ("KIM","ChatGPT's SWS has NO factory class at all; Kim's F2=satisfied (creator has a concrete implementation) is indefensible. My F2=not satisfied matches the code."),
    ("SWS","ChatGPT","factory-method","F3"): ("KIM","No factory exists; Kim's F3=satisfied is indefensible."),
    ("SWS","ChatGPT","factory-method","F5"): ("LOOSE","F5 counts `AddFundsStrategy implements TransactionStrategy` etc. as 'products'; Wallet has no product interface, which is why Kim fails F5."),
    ("SWS","ChatGPT","observer","O3"): ("STRICT","notification is a direct single-observer call `auditLog.update(...)` (User.java:25,37) with no observer collection, no loop, and no recognised subject class; O3 requires a subject with a notify method iterating a collection."),
    ("SWS","Claude","factory-method","F1"): ("STRICT","creator is `interface WalletFactory`."),
    ("SWS","Claude","factory-method","F4"): ("STRICT","createWallet returns the CONCRETE class `Wallet`; F4 only recognises products whose type is an abstract type."),
    ("SWS","Claude","factory-method","F5"): ("LOOSE","F5 counts Strategy/Observer implementers as products; Wallet has no product interface."),
    ("SWS","Copilot","factory-method","F1"): ("KIM","Copilot's SWS genuinely has `abstract class WalletFactory` + `ConcreteWalletFactory extends WalletFactory`, so an abstract creator exists (my F1=satisfied). Kim's F1=fail while F2/F3/F4=pass is internally inconsistent."),
    ("SWS","Copilot","factory-method","F4"): ("STRICT","createWallet returns the concrete `Wallet`; F4 only recognises abstract-typed products."),
    ("SWS","Copilot","factory-method","F5"): ("LOOSE","Strategy implementers counted as products."),
    ("SWS","Copilot","strategy","S3"): ("STRICT","Wallet.performTransaction(amount, TransactionStrategy strategy) receives the strategy as a parameter (Wallet.java:28), not a stored field/setter; is_context fails."),
    ("SWS","Copilot","observer","O1"): ("STRICT","observer callback is `notify(Transaction)` not `update`; and the subject Wallet is a concrete class with no abstract subject. O1 cannot see it."),
    ("SWS","Copilot","observer","O2"): ("STRICT","`interface TransactionObserver{void notify(...)}` is not recognised because O2 requires an interface method named exactly `update`."),
    ("SWS","Copilot","observer","O3"): ("STRICT","Wallet.notifyObservers loops and calls `observer.notify(...)`, but O3 requires a literal `.update(` call."),
    ("SWS","Copilot","observer","O4"): ("STRICT","no observer_types found (callback named `notify`), so concrete_observers is empty and O4 fails."),
    ("SWS","Gemini","factory-method","F1"): ("STRICT","creator is `interface WalletFactory`."),
    ("SWS","Gemini","factory-method","F2"): ("STRICT","DefaultWalletFactory uses `implements`."),
    ("SWS","Gemini","factory-method","F3"): ("STRICT","override via interface not detected."),
    ("SWS","Gemini","factory-method","F4"): ("STRICT","createWallet returns the concrete `Wallet`; F4 only recognises abstract-typed products."),
    ("SWS","Gemini","factory-method","F5"): ("LOOSE","Strategy implementers counted as products."),
    ("SWS","Gemini","observer","O2"): ("STRICT","`interface AuditLogObserver{void onLogEvent(...)}` not recognised; O2 requires a method named exactly `update`."),
    ("SWS","Meta","factory-method","F3"): ("KIM","Meta's SWS has NO factory; Kim's F3=satisfied is indefensible. My F3=not satisfied matches the code."),
    ("SWS","Meta","factory-method","F4"): ("KIM","No factory exists; Kim's F4=satisfied is indefensible."),
    ("SWS","Meta","factory-method","F5"): ("LOOSE","Strategy implementers counted as products."),
    ("SWS","Meta","observer","O1"): ("STRICT","`AuditLog extends Observable` (java.util.Observable); the JDK subject/observer framework is invisible to the scorer, which only recognises hand-rolled interfaces + literal notify methods."),
    ("SWS","Meta","observer","O2"): ("STRICT","uses java.util.Observer via Observable; no hand-rolled `update` interface for O2 to find."),
}


def md_escape(s):
    return s.replace("|", "\\|")


def build():
    S = []
    h = CMP["headline"]

    # ---------------- header ----------------
    S.append("# PIQS Automated-Scorer Replication of Kim (2025) — Validation Report\n")
    S.append("**Study.** Does my automated PIQS scorer (`app/services/piqs_service.py`, unmodified) "
             "reproduce the manual PIQS scores that Kim published in *“Comparative analysis of design "
             "pattern implementation validity in LLM-based code refactoring”*, J. Syst. Softw. 230 (2025) "
             "112519, for his 10 LLM-refactored programs (POSS × 5 LLMs, SWS × 5 LLMs)?\n")
    S.append("**Answer, up front.** Individual-property agreement is **{}/{} = {}%**. Only **{}/{} "
             "(case, LLM, pattern) scoring units reproduce all three of Kim's PSR/CPC/PIQS exactly.** "
             "The scorer is **not yet a faithful automation of Kim's manual rubric**: Factory Method and "
             "Observer are badly misaligned, Composite and Strategy have systematic single-property faults, "
             "and a handful of Kim's own published numbers are internally inconsistent. Details, causes, and "
             "per-property fix recommendations below. **No scoring code was modified.**\n".format(
                 h["agreed"], h["total_property_judgments"], h["agreement_pct"],
                 h["units_exact_match_all3"], h["score_units"]))

    S.append("### How to reproduce\n")
    S.append("```\n"
             "unzip each *.zip from Design-Pattern-Applications/ into scratchpad (read-only on Kim's files)\n"
             "python validation/build_manifest.py   # -> validation/kim_file_manifest.json\n"
             "python validation/run_scorer.py       # -> validation/kim_replication_raw.json (+ javac)\n"
             "python validation/compare.py          # -> validation/kim_comparison.json\n"
             "python validation/make_report.py      # -> this file\n"
             "```\n"
             "Full command log: `validation/commands.log`. Scorer Python: " + RAW.get("python","?") + ".\n")

    # ---------------- Step 1 anomalies ----------------
    S.append("---\n\n## Step 1 — Corpus map and anomalies\n")
    S.append("Kim's repo ships **12 ZIPs**: 2 originals (`POS.zip`, `SmartWallet.zip`) and 10 refactored "
             "(`Refactored<POS|SWS><LLM>.zip`). All 10 expected (case × LLM) combinations are present; "
             "the manifest is `validation/kim_file_manifest.json` (145 `.java` files indexed, 40 scoring units).\n")
    S.append("Anomalies / things that did not fit the expected structure:\n")
    S.append("- **Two extra programs.** `POS` (12 files) and `SmartWallet` (6 files) are Kim's pre-refactoring "
             "base programs, not LLM output. They are **not** in Kim's Tables 13/16/17 and are excluded from scoring "
             "(recorded in the manifest with role `original_base`).\n")
    S.append("- **`POS` has 12 `.java` files vs the “11 classes”** stated for POSS. The extra file is "
             "`itemDescription.java` (lower-case name). Irrelevant to scoring (base program not scored), noted for completeness.\n")
    S.append("- **Nested folder layout.** Every ZIP expands to `<Program>/<Program>/src/...`; the refactored ones use "
             "`src/main/java/com/mycompany/<pkg>/`, the originals use `src/pointofsale` or `src/main/java/.../smartwallet`. Handled.\n")
    S.append("- **“Meta” = Llama 3.1-405B.** Folder names map cleanly to the five LLMs; no ambiguous names, "
             "no duplicated programs.\n")
    S.append("- **One interpretive point (not a blocker).** A design pattern is *not* a per-file attribute: each "
             "refactored program embodies all four of its case study's patterns at once. So the manifest maps files to "
             "(case study, LLM) and treats **(case study, LLM, pattern)** as the scoring unit — 4 patterns × 5 LLMs "
             "× 2 case studies = 40 units. If you intended a stricter one-pattern-per-file mapping, tell me and I will redo it.\n")

    # ---------------- Step 2 ----------------
    S.append("---\n\n## Step 2 — Metric definition check (weights & formulas)\n")
    S.append("Confirmed **identical** to Kim's Table 9 and the PIQS/PSR/CPC formulas. From `piqs_service.py`:\n")
    S.append("| Pattern | Weights in code | Total | Matches Kim |\n|---|---|---|:--:|\n"
             "| Factory Method | F1=2,F2=3,F3=3,F4=3,F5=2 | 13 | ✅ |\n"
             "| Strategy | S1=3,S2=3,S3=2,S4=3 | 11 | ✅ |\n"
             "| Composite | C1=3,C2=2,C3=3,C4=3,C5=3 | 14 | ✅ |\n"
             "| Observer | O1=2,O2=3,O3=3,O4=3 | 11 | ✅ |\n"
             "| Singleton | G1=3 | 3 | ✅ |\n")
    S.append("`PSR = satisfied/total*100` (line 115), `CPC = Σ(w·s)/Σw*100` (line 116), "
             "`PIQS = PSR*0.6 + CPC*0.4` (line 117). No weight or formula difference. The disagreements below are "
             "**entirely in the property predicates**, never in the weighting/aggregation.\n")

    # ---------------- Arithmetic verification of Kim's numbers ----------------
    bad = [a for a in CMP["arithmetic_check"] if not a["consistent"]]
    S.append("### Verification of the Composite-row correction (task asked me to check)\n")
    S.append("I recomputed every one of Kim's 40 published (PSR, CPC, PIQS) triples from the failing-property set "
             "implied by his tables. **All 40 are internally consistent** once the Composite row is corrected as the "
             "task describes:\n")
    S.append("- **Claude / POSS / Composite** → 100 / 100 / 100 (all C pass). Check: Claude POSS average PIQS "
             "= (78.77 + 100 + **100** + 77.73)/4 = 89.12 ✅ (matches Kim's published per-model average).\n")
    S.append("- **Gemini / POSS / Composite** → 40 / 35.71 / 38.29 (C1,C4,C5 fail). Check: PSR 2/5=40, "
             "CPC (2+3)/14=35.71, PIQS 38.29; Gemini POSS average = (100+100+**38.29**+22.27)/4 = 65.14 ✅.\n")
    S.append("So the printed table's Claude↔Gemini Composite swap is confirmed, and my comparison uses the "
             "corrected values. (The per-model averages, not the swapped cells, are self-consistent.)\n")
    if bad:
        S.append("\n⚠️ Internal-consistency failures found: " + ", ".join(a["unit"] for a in bad) + "\n")

    # ---------------- Section 1 headline ----------------
    S.append("---\n\n## 1 — Headline agreement rate\n")
    S.append("- **Property-level:** **{}/{} individual property judgments agree = {}%.** "
             "(The task's “roughly 40” refers to the 40 scoring units; scored at the individual-property "
             "level there are {} judgments — POSS: 5 LLMs × (5+4+5+4)=90; SWS: 5 × (5+4+1+4)=70.)\n".format(
                 h["agreed"], h["total_property_judgments"], h["agreement_pct"], h["total_property_judgments"]))
    S.append("- **Score-level:** {}/{} (case, LLM, pattern) units match Kim's PSR, CPC and PIQS exactly.\n".format(
        h["units_exact_match_all3"], h["score_units"]))
    # agreement by pattern
    bypat = {}
    for r in CMP["property_comparison"]:
        k = r["pattern"]; t, a = bypat.get(k,(0,0)); bypat[k]=(t+1, a+(1 if r["match"] else 0))
    S.append("- **By pattern:** " + "; ".join(
        "{} {}/{} ({}%)".format(PAT_LABEL[p], a, t, round(a/t*100)) for p,(t,a) in
        sorted(bypat.items(), key=lambda kv: PAT_ORDER[kv[0]])) + ".\n")

    # ---------------- Section 6-in-2: compilation (put early? keep numbered) ----------------
    # ---------------- Section 2 property-level table ----------------
    S.append("---\n\n## 2 — Property-level comparison (one row per case, LLM, pattern, property)\n")
    S.append("`S`=satisfied, `·`=not satisfied. ✅=match, ❌=mismatch.\n")
    rows = sorted(CMP["property_comparison"], key=sort_key)
    S.append("| Case | LLM | Pattern | Prop | Kim | Mine | Match |\n|---|---|---|---|:--:|:--:|:--:|")
    for r in rows:
        S.append("| {} | {} | {} | {} | {} | {} | {} |".format(
            r["case_study"], r["llm"], PAT_LABEL[r["pattern"]], r["property"],
            "S" if r["kim"]=="satisfied" else "·",
            "S" if r["mine"]=="satisfied" else "·",
            "✅" if r["match"] else "❌"))
    S.append("")

    # ---------------- Section 3 score-level table ----------------
    S.append("---\n\n## 3 — Score-level comparison (one row per case, LLM, pattern)\n")
    S.append("| Case | LLM | Pattern | Kim PSR/CPC/PIQS | My PSR/CPC/PIQS | ΔPSR | ΔCPC | ΔPIQS |\n"
             "|---|---|---|---|---|--:|--:|--:|")
    for r in sorted(CMP["score_comparison"], key=sort_key):
        S.append("| {} | {} | {} | {:.2f}/{:.2f}/{:.2f} | {:.2f}/{:.2f}/{:.2f} | {:.2f} | {:.2f} | {:.2f} |".format(
            r["case_study"], r["llm"], PAT_LABEL[r["pattern"]],
            r["kim_psr"], r["kim_cpc"], r["kim_piqs"], r["my_psr"], r["my_cpc"], r["my_piqs"],
            r["d_psr"], r["d_cpc"], r["d_piqs"]))
    S.append("")
    # overall PIQS per model (Kim Table 17) vs mine
    S.append("### Overall PIQS per model (Kim Table 17) vs mine\n")
    kim_overall = {"ChatGPT":(95.46,80.05,87.75),"Claude":(89.12,89.89,89.51),"Copilot":(74.46,90.92,82.69),
                   "Gemini":(65.14,76.94,71.04),"Meta":(100.00,77.97,88.98)}
    mine = {}
    for r in RAW["results"]:
        mine.setdefault((r["case_study"], r["llm"]), []).append(r["piqs"])
    S.append("| LLM | Kim POSS | Mine POSS | Kim SWS | Mine SWS | Kim overall | Mine overall |\n"
             "|---|--:|--:|--:|--:|--:|--:|")
    for llm in LLM_ORDER:
        mp = sum(mine[("POSS",llm)])/len(mine[("POSS",llm)])
        ms = sum(mine[("SWS",llm)])/len(mine[("SWS",llm)])
        mo = (mp+ms)/2
        kp,ks,ko = kim_overall[llm]
        S.append("| {} | {:.2f} | {:.2f} | {:.2f} | {:.2f} | {:.2f} | {:.2f} |".format(llm,kp,mp,ks,ms,ko,mo))
    S.append("\n> The overall column is the mean of the two case-study means (as in Kim's Table 17). My overall "
             "numbers are depressed mainly by Factory Method and Observer, the two most misaligned patterns.\n")

    # ---------------- Section 4 disagreement analysis ----------------
    S.append("---\n\n## 4 — Disagreement analysis\n")
    # counts by category
    catcount = {}
    for k,(cat,_) in CLASS.items():
        catcount[cat] = catcount.get(cat,0)+1
    S.append("All **{}** mismatches, classified:\n".format(len(CLASS)))
    S.append("| Cause | Count |\n|---|--:|")
    for cat in ["STRICT","LOOSE","PARSE","KIM","AMBIG"]:
        S.append("| {} | {} |".format(CAT[cat], catcount.get(cat,0)))
    S.append("")
    S.append("Full itemised classification (each row is one mismatch from the table in §2):\n")
    S.append("| Case | LLM | Pattern | Prop | Dir. | Cause | Why (with code evidence) |\n|---|---|---|---|:--:|---|---|")
    for r in sorted(CMP["property_comparison"], key=sort_key):
        if r["match"]:
            continue
        key = (r["case_study"], r["llm"], r["pattern"], r["property"])
        cat, reason = CLASS[key]
        direction = "Kim S / me ·" if r["kim"]=="satisfied" else "Kim · / me S"
        S.append("| {} | {} | {} | {} | {} | {} | {} |".format(
            r["case_study"], r["llm"], PAT_LABEL[r["pattern"]], r["property"], direction,
            cat, md_escape(reason)))
    S.append("")

    S.append(PROSE_ROOTCAUSES)

    # ---------------- Section 5 reliability ----------------
    S.append("---\n\n## 5 — Per-property reliability\n")
    S.append("Flag = agreement < 80% → unreliable for the main study.\n")
    S.append("| Prop | Meaning | Tested | Agree | Agreement | Reliable? |\n|---|---|--:|--:|--:|:--:|")
    meaning = {
        "F1":"abstract creator exists","F2":"creator has concrete impl","F3":"concrete creator overrides factory method",
        "F4":"factory creates correct product type","F5":"concrete products implement product interface",
        "S1":"abstract strategy exists","S2":"strategy has concrete impl","S3":"context class exists","S4":"strategies implement algorithm",
        "C1":"abstract component exists","C2":"leaf exists","C3":"composite exists","C4":"composite & leaf implement component","C5":"uniform treatment",
        "O1":"abstract subject exists","O2":"abstract observer exists","O3":"subject notifies observers","O4":"observers update on notify",
        "G1":"private constructor / singleton",
    }
    for p in ["F1","F2","F3","F4","F5","S1","S2","S3","S4","C1","C2","C3","C4","C5","O1","O2","O3","O4","G1"]:
        if p in CMP["reliability"]:
            rr = CMP["reliability"][p]
            S.append("| {} | {} | {} | {} | {}% | {} |".format(
                p, meaning[p], rr["tested"], rr["agreed"], rr["agreement_pct"],
                "✅" if rr["reliable"] else "❌ **UNRELIABLE**"))
    S.append("")
    S.append("**Reliable (≥80%):** S1,S2,S4 (100%), G1 (100%), C2,C3 (100%), O4 (80%), S3 (80%). "
             "**Unreliable:** all five Factory properties (30–50%), C1,C4 (60%), C5 (40%), O1 (50%), O2 (60%), O3 (70%). "
             "Note several 'agreements' are **coincidental** (right verdict, wrong reason) — e.g. SWS F2/F3 pass only "
             "because an unrelated class uses `extends` (User extends Subject/Observable) — so true reliability of "
             "Factory is even lower than the raw percentages suggest.\n")

    # ---------------- Section 6 compilation ----------------
    S.append("---\n\n## 6 — Compilation results (`javac` 21)\n")
    S.append("| Case | LLM | Compiles? | Kim says executable? | Match | First javac error |\n|---|---|:--:|:--:|:--:|---|")
    kim_exec = {("POSS","ChatGPT"):True,("POSS","Claude"):True,("POSS","Copilot"):False,("POSS","Gemini"):False,("POSS","Meta"):False,
                ("SWS","ChatGPT"):False,("SWS","Claude"):True,("SWS","Copilot"):False,("SWS","Gemini"):False,("SWS","Meta"):False}
    firsterr = {
        ("POSS","Copilot"):"POS.java:37: cannot find symbol",
        ("POSS","Gemini"):"InventoryObserver.java:13: cannot find symbol (8 errors)",
        ("POSS","Meta"):"RefactoredPOSMeta.java:45: components has private access in Sale",
        ("SWS","Copilot"):"RefactoredSWSCopilot.java:37: void cannot be converted to AuditLog",
        ("SWS","Gemini"):"DefaultWalletFactory.java:15: constructor Wallet cannot be applied (11 errors)",
        ("SWS","Meta"):"RefactoredSWSMeta.java:16: cannot find symbol",
    }
    for name,p in RAW["programs"].items():
        if p["role"]!="refactored": continue
        key=(p["case_study"],p["llm"])
        comp=p["compiles"]; kex=kim_exec[key]
        S.append("| {} | {} | {} | {} | {} | {} |".format(
            p["case_study"], p["llm"], "✅ yes" if comp else "❌ no",
            "yes" if kex else "no", "✅" if comp==kex else "❌",
            "" if comp else firsterr.get(key,"")))
    S.append("")
    S.append("**Match with Kim: 9/10.** Kim: *“only ChatGPT and Claude produced executable POSS programs, and only "
             "Claude produced an executable SWS program.”* My javac results agree on all POSS programs and on SWS "
             "Claude/Copilot/Gemini/Meta. **The one contradiction: SWS / ChatGPT compiles cleanly for me** (javac 21, no "
             "errors) whereas Kim reports it non-executable. Likely explanations: (a) “executable” for Kim means "
             "*runs to completion*, not merely *compiles* — the program reads from `System.in`, so a run could stall or "
             "throw at runtime while still compiling; or (b) toolchain/version differences. Worth a manual `java` run to "
             "settle, but by the objective `javac` criterion it compiles.\n")

    # ---------------- Section 7 recommendations ----------------
    S.append("---\n\n## 7 — Recommendation per property\n")
    S.append(PROSE_RECS)

    S.append("\n---\n\n*Generated by `validation/make_report.py`. Inputs: `kim_replication_raw.json`, "
             "`kim_comparison.json`, `kim_file_manifest.json`. Scorer read-only and unmodified throughout.*\n")

    open(OUT, "w").write("\n".join(S))
    print("Wrote", OUT, "(", len("\n".join(S)), "bytes )")


PROSE_ROOTCAUSES = """
### Root causes, grouped (with code)

**A. Factory Method predicates assume class-inheritance and are the single biggest source of error (F1–F5 all < 55% reliable).**
Kim's corpus overwhelmingly implements Factory Method with an **interface** creator, but the scorer's Factory predicates are written for **abstract-class** creators and `extends`-based hierarchies.

- **F1 (`any class that is_abstract`)** is doubly wrong. It ignores interface creators *and* accepts any abstract class regardless of role. Claude/Gemini/Meta POSS and Claude/Gemini SWS all declare the creator as an interface, e.g.:
  ```java
  // RefactoredPOSClaude/PaymentFactory.java:12
  interface PaymentFactory { PaymentStrategy createPayment(); }
  ```
  → no abstract *class* → my F1 = not satisfied, Kim = satisfied. Conversely, ChatGPT POSS has a *concrete* factory but an unrelated abstract Composite component, so F1 fires on the wrong type:
  ```java
  // RefactoredPOSChatGPT/PaymentFactory.java:12  (concrete!)
  class PaymentFactory { public static PaymentStrategy getPaymentMethod(String type){...} }
  // RefactoredPOSChatGPT/SaleComponent.java:12   <- my F1 matched THIS
  abstract class SaleComponent { ... }
  ```

- **F2 / F3 only recognise `extends`.** Interface factories use `implements`:
  ```java
  // RefactoredPOSClaude/CashPaymentFactory.java:12-16
  class CashPaymentFactory implements PaymentFactory {
      @Override public PaymentStrategy createPayment() { return new CashPayment(); }
  }
  ```
  My F2 (`concrete class with .extends`) and F3 (override via `extends`) both miss this → false negatives everywhere the factory is interface-based.

- **F4 requires the product's static type to be an *abstract* type.** SWS returns a **concrete** `Wallet`:
  ```java
  // RefactoredSWSClaude/StandardWalletFactory.java:13-15
  public Wallet createWallet(String currency) { return new Wallet(currency); }
  ```
  `Wallet` is a concrete class, not in `product_names`, so F4 cannot fire (Claude/Copilot/Gemini SWS). Kim accepts it.

- **F5 counts Strategy/Observer implementers as “products.”** In every SWS program Kim fails F5 because `Wallet` implements no product interface, but my `is_product_exists` is satisfied by unrelated strategy classes:
  ```java
  // RefactoredSWSClaude/DepositStrategy... implements TransactionStrategy  (an abstract type)
  ```
  → 5/5 SWS false positives on F5.

**B. Parser limitation: methods with a `throws` clause are dropped.** `_METHOD_SIG_RE` requires `)` to be followed directly by `{`/`;`, so a `throws` clause breaks the match:
```java
// RefactoredPOSCopilot/PaymentFactory.java:13
public static Payment createPayment(String paymentType) throws Exception { ... return new ByCash(); }
```
This method is never extracted; its `Payment` return type is invisible, so F4 (and `hasFactory`) cannot fire even though this *is* a correct interface-typed factory. Independently, the method extractor also re-scans method bodies and captures statements like `observers.add(observer);` as phantom methods (e.g. Copilot's `PaymentFactory` “methods” come out as `ByCash`, `ByCreditCard`, `Exception`). This noise mostly perturbs Factory/Observer name-matching.

**C. Composite is anchored on “any interface = a component” and “any add/remove-named method = a composite.”** In the two POSS programs with **no** Composite (Copilot, Gemini — there is no `SaleComponent`), the Strategy/Observer interfaces masquerade as components and `Register.addSale/addInventory` masquerades as a composite:
```java
// RefactoredPOSCopilot/Register.java:36,40  -> makes Register a "composite"
public void addSale(Sale s){...}   public void addInventory(Item item,int q){...}
// the REAL container, Sale, implements NO component interface, so it is ignored:
// RefactoredPOSCopilot/Sale.java:16   class Sale { private List<SaleLineItem> slis; public void add(SaleLineItem sli){...} }
```
→ C1 and C4 false-positive for Copilot/Gemini. **C5 (uniform treatment)** fails on the *real* composites (ChatGPT/Claude/Meta) because the check keys off `abstract_components[0]` — an arbitrary interface — and `composites[0]`/`leaves[0]`, not the actual `SaleComponent` API. So C5 is 0 for all five POSS programs (wrong for 3, right for 2).

**D. Strategy S3 (context) requires a stored strategy field or setter; it rejects strategy-as-parameter.** ChatGPT POSS and Copilot SWS pass the strategy in as a method argument:
```java
// RefactoredPOSChatGPT/RefactoredPOSChatGPT.java:47   PaymentStrategy payment = PaymentFactory.getPaymentMethod(paymentType);
// RefactoredSWSCopilot/Wallet.java:28   public String performTransaction(double amount, TransactionStrategy strategy){ strategy.execute(...); }
```
`is_context` needs `(field or setter) AND execute`, so these “contexts” are not recognised. (S1/S2/S4 are 100% reliable — Strategy is otherwise fine.)

**E. Observer hard-codes the callback name `update` and a collection+loop notification shape; it cannot see interface subjects or the JDK Observer framework.**
- **O1** checks `is_abstract` only among `subject_candidates`, which are filtered to `kind=='class'`. Every real subject here is either an interface (`InventorySubject`) or a concrete class, so **O1 is 0 in all 10 programs** — right when Kim also fails it, wrong otherwise.
  ```java
  // RefactoredPOSChatGPT/InventorySubject.java:12   interface InventorySubject { void addObserver(...); void notifyObservers(...);}  <- invisible to O1
  ```
- **O2/O3/O4** depend on an interface method literally named `update` and a `.update(` call. Copilot SWS (`notify`), Gemini SWS (`onLogEvent`), and Meta SWS (`java.util.Observable`) therefore score **0/0/0/0** although their Observer implementations are real:
  ```java
  // RefactoredSWSCopilot/TransactionObserver.java:12   interface TransactionObserver { void notify(Transaction t); }
  // RefactoredSWSGemini/AuditLogObserver.java:12       interface AuditLogObserver { void onLogEvent(String s); }
  // RefactoredSWSMeta/AuditLog.java:14                 class AuditLog extends Observable { void logAction(...){ setChanged(); notifyObservers(...);} }
  ```
- **O3 also rejects single-observer direct notification.** SWS ChatGPT notifies one directly-held observer with no collection/loop, so O3 fails although notification clearly happens:
  ```java
  // RefactoredSWSChatGPT/User.java:18,25,37   Observer auditLog; ... auditLog.update("User created: "+name); ... auditLog.update("Wallet added: "+currency);
  ```

**F. A distinct category: Kim's own published numbers are internally inconsistent in several cells** (the task warned about this; treating the numeric tables as authoritative surfaces them as “mismatches” that are really Kim-side problems):
- **POSS / Gemini / Observer** — near-total inversion. Kim's numeric row (PSR 25) forces **O1 satisfied, O2/O3/O4 not**, but the code has **no abstract subject at all** (`ItemInventory` is a concrete class) while it *does* have a working `update` interface, a notify-loop, and a concrete observer. My verdict (O1 not satisfied, O2/O3/O4 satisfied) is the defensible reading; Kim's numeric O1=satisfied is impossible. (The task itself flags Gemini/Observer prose↔number conflict.)
- **SWS / ChatGPT / Factory** and **SWS / Meta / Factory** — these programs contain **no factory class whatsoever**, yet Kim's numbers mark F2/F3 (ChatGPT) and F3/F4 (Meta) satisfied. “Creator has a concrete implementation” cannot hold when no creator exists. My not-satisfied verdicts match the code.
- **SWS / Copilot / Factory / F1** — Copilot's SWS *does* have `abstract class WalletFactory` + `ConcreteWalletFactory extends WalletFactory`, so an abstract creator exists (my F1 satisfied), yet Kim marks F1 failed while F2/F3/F4 pass — internally inconsistent.

These Kim-side cases (9 of the 54 mismatches) are **not** scorer defects; if anything they show the automated scorer disagreeing *correctly* with a flawed manual cell.
"""

PROSE_RECS = """Legend: **KEEP** = matches Kim reliably; **FIX** = automatable, predicate needs work; **DROP** = too ambiguous / manual-judgement-heavy to automate for the main study.

| Prop | Verdict | Action |
|---|:--:|---|
| **F1** abstract creator | **FIX** | Accept an **interface** creator, and tie it to the creator role: an abstract type (interface *or* abstract class) that declares a method whose return type is a product and/or is implemented by ≥1 concrete factory. Do not accept an arbitrary abstract class. |
| **F2** creator has concrete impl | **FIX** | Treat `implements <Creator>` the same as `extends <Creator>`. Currently only `extends` counts. |
| **F3** concrete creator overrides factory method | **FIX** | Detect `@Override`/same-signature methods across **interface implementation**, not just class inheritance. |
| **F4** creates correct product type | **FIX** | (a) allow the product's static type to be a **concrete** class, not only an abstract type; (b) fix the `throws`-clause parser gap so factory methods declared `throws` are seen. |
| **F5** concrete products implement product interface | **FIX** | Anchor “product” to the *type the factory method returns*, not to “any concrete class implementing any abstract type.” This stops Strategy/Observer implementers counting as products (fixes all 5 SWS false positives). |
| **S1** abstract strategy | **KEEP** | 100%. |
| **S2** strategy has concrete impl | **KEEP** | 100%. |
| **S3** context class exists | **FIX** | Accept a class that receives/uses a strategy **via parameter or local variable**, not only via a stored field/setter. (80% now; the two misses are both parameter-style contexts.) |
| **S4** strategies implement algorithm | **KEEP** | 100%. |
| **C1** abstract component | **FIX** | Only count a component that actually participates in a part–whole hierarchy (a type used as the element type of a collection held by a composite of that same type), not any interface in the file. |
| **C2** leaf | **KEEP** | 100% here — but note it passes partly by luck; re-verify after C1/C3 are anchored to a real hierarchy. |
| **C3** composite | **KEEP\\*** | 100% here, but “has an add/remove-named method” is fragile (it mislabels `Register.addSale`). Tighten to “holds a collection of the component type” when you fix C1/C4. |
| **C4** composite & leaf implement component | **FIX** | Follow from a corrected C1: require both the composite and the leaf to implement the *same* component type; stop firing on unrelated interfaces. |
| **C5** uniform treatment | **FIX** | Do not key off `abstract_components[0]`/`composites[0]`/`leaves[0]`. Compare the **actual component's** method set against the specific composite and leaf that implement it. (40% now.) |
| **O1** abstract subject | **FIX** | Include **interface** subjects: allow `subject_candidates` of `kind=='interface'`, and count an abstract subject when a Subject interface (or abstract class) declares attach/detach/notify. Currently structurally impossible to satisfy. |
| **O2** abstract observer | **FIX** | Do not hard-code the method name `update`. Detect the observer interface by its role (implemented by classes the subject notifies), accepting `notify`, `onLogEvent`, `java.util.Observer`, etc. |
| **O3** subject notifies observers | **FIX** | Generalise: accept notification through a single held observer (no loop) and callbacks not literally named `update`; recognise `java.util.Observable.notifyObservers`. |
| **O4** observers update on notify | **FIX** | Tie to the observer interface's actual callback method (see O2), not the literal name `update`. (80% now, best of the four, but same root fix.) |
| **G1** private constructor / singleton | **KEEP** | 100% (all 5 SWS Singletons agree). |

**Bottom line for the main study.** As-is, only **Strategy (minus S3), Singleton, and the Composite leaf/composite existence checks** are trustworthy. **Factory Method and Observer should not be used for per-property claims until FIXed** — they are 30–55% reliable and several agreements are coincidental. After the fixes above (most are small, well-scoped predicate changes; the `throws` parser gap is a one-line regex fix), re-run this exact harness to confirm before relying on the numbers. Separately, **flag the Kim-side inconsistent cells** (POSS Gemini Observer; SWS ChatGPT/Meta Factory; SWS Copilot F1) in the paper rather than treating them as scorer error.
"""

if __name__ == "__main__":
    build()
