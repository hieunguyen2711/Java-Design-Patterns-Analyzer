# PIQS Scorer — Pass 3 (parser precision F & G): Before/After (v4)

**Goal of this pass: extractor *correctness for the main study*, not a higher Kim score.** Two fixes, both in the fact-extraction layer (no pattern-predicate logic changed):

- **F** — field extraction restricted to class-body scope. Method-local variables are no longer mis-captured as fields. (`_class_scope_only` strips every method/ctor/initialiser/nested-type body via brace-depth tracking.)

- **G** — identifier tests match whole tokens, not substrings. `pay` no longer matches inside `payment`; `add` operations detected by camelCase verb prefix (addChild yes, address no).


Diff (pass-3 only): `validation/piqs_service_fix_pass3.diff` (+61 / −10). v3 outputs preserved as `*_v3.*`.

## Headline: v3 → v4  (a DECREASE is the correct outcome here)

| Metric | v3 | v4 | Δ |
|---|--:|--:|--:|
| Property-level agreement | 146/160 (91.2%) | 141/160 (88.1%) | -3.1 pts |
| Units matching all 3 scores exactly | 31/40 | 26/40 | -5 |
| Disagreements | 14 | 19 | +5 |

**This pass is precision-for-scale, not score-chasing.** The 5 extra disagreements are: **4 correct S3 corrections** (deferred strategy-as-parameter, previously propped up by the local-variable-as-field bug) and **1 protected regression on G1** (reported in full below). The scorer is now *more correct* even though the Kim number ticked down — exactly what you asked for.

## Per-property reliability: v3 → v4

| Prop | v3 | v4 | Δ | Note |
|---|--:|--:|:--:|---|
| F1 | 90.0% | 90.0% |  |  |
| F2 | 100.0% | 100.0% |  |  |
| F3 | 100.0% | 100.0% |  |  |
| F4 | 50.0% | 50.0% |  | deferred F4-concrete + 1 ambiguity |
| F5 | 100.0% | 100.0% |  |  |
| S1 | 100.0% | 100.0% |  |  |
| S2 | 100.0% | 100.0% |  |  |
| S3 | 90.0% | 50.0% | ⬇ | deferred strategy-as-parameter (expected ⬇, correct) |
| S4 | 100.0% | 100.0% |  |  |
| C1 | 100.0% | 100.0% |  |  |
| C2 | 100.0% | 100.0% |  |  |
| C3 | 100.0% | 100.0% |  |  |
| C4 | 100.0% | 100.0% |  |  |
| C5 | 100.0% | 100.0% |  |  |
| O1 | 90.0% | 90.0% |  |  |
| O2 | 80.0% | 80.0% |  |  |
| O3 | 80.0% | 80.0% |  |  |
| O4 | 80.0% | 80.0% |  |  |
| G1 | 100.0% | 80.0% | ⬇ | **PROTECTED REGRESSION — holder idiom, see below** |

## Zero-regression check on the protected set (your step 3)

⚠️ **One protected property dropped — STOPPING to report as instructed:**

- **G1**: 100.0% → 80.0%

Every other protected property held exactly (F1 90, F2 100, F3 100, F5 100, S1/S2/S4 100, C1–C5 100, O1 90, G... see below). The one drop is **G1**, analysed next. **It is NOT a fix leaking into predicate logic** — Fix F is a correct extractor change; it exposed a pre-existing narrowness in the G1 predicate.

## ⚠️ G1 protected regression — Bill Pugh holder idiom (STOP-and-report)

**SWS/Copilot Singleton G1 flipped satisfied → not satisfied.** Root cause, exactly:

```java
// RefactoredSWSCopilot/CurrencyConverter.java
class CurrencyConverter {
    private CurrencyConverter() { }                    // private ctor  (has_private_ctor OK)
    public static CurrencyConverter getInstance() {     // accessor      (has_instance_method OK)
        return Holder.INSTANCE;
    }
    private static class Holder {                       // <-- nested static holder
        private static final CurrencyConverter INSTANCE = new CurrencyConverter();
    }
}
```

- **Before Fix F**, field extraction scanned the whole class body, so the nested `Holder.INSTANCE` field *leaked upward* and was counted as a static instance field of `CurrencyConverter`. `has_static_instance` was true — right answer, wrong mechanism.

- **After Fix F**, `CurrencyConverter` correctly has **0** fields (INSTANCE belongs to `Holder`). But `has_static_instance` only looks for a `static <SelfType>` field declared *directly in the singleton class*, so it does not recognise the Bill Pugh holder idiom, and **G1 fails**.

- **This is a PREDICATE-LOGIC gap, not an extractor bug.** Fix F is correct. Per your constraints (‘if a predicate needs its logic changed, STOP and report; that is a different pass’ and ‘if you find a seventh distinct cause, STOP and report — do not fix it here’), **I did NOT change the predicate.**

- **Impact for the main study:** classic singletons (`private static X instance;` in the class) still score G1 correctly — Fix F keeps genuine class-scope fields (verified: the other 4 SWS singletons stayed G1=1, and a synthetic classic-singleton keeps its field). Only the **holder idiom** is mis-scored.

- **Recommended pass 4 (needs your approval — it is a predicate change):** broaden `has_static_instance` to also accept a `static` field of the singleton's type declared in a **nested static class** of that singleton (the holder). That restores G1 for the holder idiom without reintroducing the local-variable bug.


**Decision needed from you:** approve the pass-4 G1 predicate broadening, or accept the holder-idiom limitation. I have left G1 as-is pending your call.

## S3 dropped more than the single cell you anticipated (90% → 50%) — and that is correct

You expected POSS/ChatGPT S3 to flip. In fact **four** POSS S3 cells flipped (ChatGPT, Claude, Copilot, Gemini), because *all four* of those contexts use the strategy via a method-local variable or parameter, and each was being held up by the same local-variable-as-field bug. With the extractor corrected, `is_context` (which requires a stored strategy field or setter — the **deferred strategy-as-parameter** definition) correctly fails for all of them. These are the same deferred category, not new bugs. The 5 remaining S3 passes are contexts with a genuine class-scope strategy field.

## Fix A confirmed NOT re-broken

Observer callbacks are still detected structurally (subject invokes them on its observers), independent of name. SWS/Copilot (`notify`) and SWS/Gemini (`onLogEvent`) Observer O2/O3/O4 remain resolved in v4, and the synthetic guard `A-not-rebroken` (callback `ping`) passes. No name-based callback detection was reintroduced.

## Audit — every substring/identifier check found, and its disposition (Fix G)

| Location | Before | Action |
|---|---|---|
| Strategy `execute` | `name in m.body` (substring; `"pay"` in `"payment"`) | → `_calls_method` (whole-token call) |
| Strategy `setter` | `m.name.lower().startswith("set")` | → `_has_verb_prefix(name,"set")` (camelCase verb) |
| Composite `is_add`/`is_remove` | `startswith("add")` / `startswith("remove")` | → `_has_verb_prefix` |
| Composite `composites` | `"add" in name.lower() or "remove" in name.lower()` (substring) | → `_has_verb_prefix` |
| Composite `is_add_child`/`is_remove_child` | `startswith(...)` | → `_has_verb_prefix` |
| Singleton `accesses_field` | `f.name in m.body` (substring) | → `_mentions_token` (whole-token) |
| Factory `"abstract" in m.modifiers` | set membership | left (exact, not substring) |
| Observer `"Observer" in t.implements` (×2) | list membership of an exact interface name | left (exact; correctly does NOT match `TransactionObserver`) |
| Singleton `"private"/"static" in m.modifiers/f.modifiers` (×3) | set membership | left (exact, not substring) |
| Observer callback detection (Fix A) | already structural (subject-invokes + reads param) | left — NOT reverted to names |

Every substring-containment identifier test (`X in body` / `X in name`) was converted to whole-token or exact-call matching. Set/list membership checks (`X in modifiers` / `X in implements`) are already exact and were left unchanged.

## Synthetic generality tests — all 10 pass (`synthetic_generality_tests.py`)

| Test | Result |
|---|:--:|
| A: observer callback `ping` in notify loop → O2/O3/O4 pass | ✅ |
| B: `extends Observable` + `implements Observer` → O1/O2 pass | ✅ |
| D: Strategy-only (no part-whole) → C1/C4/C5 = 0 | ✅ |
| D: genuine part-whole → C1..C5 = 1 | ✅ |
| E: factory method with `throws` → F1 & F4 pass | ✅ |
| **F: method-local var NOT a field** (0 Foo fields) | ✅ |
| **F: genuine class-scope field kept** (1 Foo field) | ✅ |
| **G: `pay` does NOT match inside `payment`/`PaymentFactory`** | ✅ |
| **G: `pay(` matches; addChild yes / address no** | ✅ |
| **A-not-rebroken: `ping` callback still detected after Fix G** | ✅ |

## Every remaining disagreement (19), classified (your step 4)

| Category | Count |
|---|--:|
| Kim's number contradicts the code (our verdict correct) — cite, do not match | 9 |
| Deferred definitional choice: F4 concrete-typed product | 3 |
| Deferred definitional choice: S3 strategy-as-parameter (now correctly failing) | 5 |
| Genuine ambiguity in the property definition | 1 |
| PROTECTED-SET REGRESSION — predicate gap exposed by the correct extractor (flagged, not fixed) | 1 |

| Case | LLM | Pattern | Prop | Kim | Mine | Category | Why |
|---|---|---|---|:--:|:--:|---|---|
| POSS | ChatGPT | Strategy | S3 | S | · | DEFER-S3 | Strategy is a method-local/param, not a stored field/setter; with locals no longer mis-parsed as fields, is_context correctly fails. The deferred strategy-as-parameter choice. |
| POSS | Claude | Factory | F4 | · | S | AMBIG | F2/F3/F4 are all weight 3 and arithmetically indistinguishable; Kim's 'F4 fails' is prose-derived. My F4=satisfied. |
| POSS | Claude | Strategy | S3 | S | · | DEFER-S3 | Strategy used via local/param, not a stored field. Deferred strategy-as-parameter choice (newly surfaced by Fix F). |
| POSS | Copilot | Strategy | S3 | S | · | DEFER-S3 | Strategy used via local/param. Deferred strategy-as-parameter choice (newly surfaced by Fix F). |
| POSS | Gemini | Strategy | S3 | S | · | DEFER-S3 | Strategy used via local/param. Deferred strategy-as-parameter choice (newly surfaced by Fix F). |
| POSS | Gemini | Observer | O1 | S | · | KIM | No abstract subject exists (ItemInventory concrete); Kim's numeric O1=satisfied is impossible. Our O1=not satisfied matches the code. |
| POSS | Gemini | Observer | O2 | · | S | KIM | InventoryObserver interface exists and is notified; O2 defensibly satisfied. Kim's numeric O2=fail contradicts the code. |
| POSS | Gemini | Observer | O3 | · | S | KIM | ItemInventory loops observers calling update(); O3 defensibly satisfied. Kim's O3=fail contradicts the code. |
| POSS | Gemini | Observer | O4 | · | S | KIM | Register implements update(); O4 defensibly satisfied. Kim's O4=fail contradicts the code. |
| SWS | Claude | Factory | F4 | S | · | DEFER-F4 | createWallet returns the concrete `Wallet`; the F4-concrete-product choice was deferred. Left as-is. |
| SWS | Copilot | Factory | F1 | · | S | KIM | `abstract class WalletFactory` + `ConcreteWalletFactory extends` genuinely exist (F1=satisfied). Kim's F1=fail while F2/F3/F4=pass is inconsistent. |
| SWS | Copilot | Factory | F4 | S | · | DEFER-F4 | createWallet returns concrete `Wallet` (deferred F4-concrete choice). Left as-is. |
| SWS | Copilot | Strategy | S3 | S | · | DEFER-S3 | Wallet.performTransaction receives the strategy as a parameter. Deferred strategy-as-parameter choice (already failing in v3). |
| SWS | Copilot | Singleton | G1 | S | · | REGRESS | PROTECTED-SET REGRESSION (see dedicated section). Bill Pugh holder idiom: the static instance lives in a nested `Holder` class. Fix F correctly stops the nested field leaking into CurrencyConverter; this exposes that `has_static_instance` only inspects the singleton class itself. Predicate-logic gap, NOT a fix leak. Flagged, not fixed. |
| SWS | Gemini | Factory | F4 | S | · | DEFER-F4 | createWallet returns concrete `Wallet` (deferred F4-concrete choice). Left as-is. |
| SWS | Gemini | Observer | O3 | · | S | KIM | AuditLog loops observers calling onLogEvent(); ConsoleLogger is registered in main. Observer complete and wired; O3 defensibly satisfied. Kim's O3=fail contradicts the code. |
| SWS | Gemini | Observer | O4 | · | S | KIM | ConsoleLogger implements onLogEvent(); O4 defensibly satisfied. Kim's O4=fail contradicts the code. |
| SWS | Meta | Factory | F4 | S | · | KIM | Meta's SWS has NO factory class; Kim's F4=satisfied is indefensible. Our F4=not satisfied matches the code. |
| SWS | Meta | Observer | O2 | S | · | KIM | `extends Observable` but no class implements Observer; structurally no abstract observer. Kim's O2=satisfied is lenient; ours is defensible. |

**No genuine remaining bug in the pattern predicates except the one flagged G1 predicate gap.** Everything else is Kim-side, an explicitly deferred definitional choice, or one arithmetic ambiguity.


---

*Generated by `validation/make_report_v4.py`. Scorer changes confined to the fact-extraction layer (Fixes F, G); see `piqs_service_fix_pass3.diff`. No pattern-predicate logic was changed; the G1 holder-idiom gap is flagged for a decision.*
