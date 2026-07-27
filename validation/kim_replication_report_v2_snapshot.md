# PIQS Scorer — Interface-as-Abstract-Role Fix: Before/After (v2)

**One conceptual change applied:** a Java `interface` now counts as fulfilling an *abstract* pattern role wherever the checker previously required an `abstract class`, and `implements` counts like `extends`. Concretely this reworked Factory Method **F1/F2/F3** (and the derived `isCreator`/`overrides`) and Observer **O1**. F1 was additionally anchored to the *creator role* so that static/switch **simple factories are deliberately rejected** as not-GoF. Nothing else was touched — no weights, formulas, thresholds, and none of the already-100% predicates.

Diff: `validation/piqs_service_fix.diff` (+63 / −9 lines, one file). Old outputs preserved as `*_v1.*`.

## Headline: before → after

| Metric | Before (v1) | After (v2) | Δ |
|---|--:|--:|--:|
| Property-level agreement | 106/160 (66.2%) | 128/160 (80.0%) | **+13.8 pts** |
| Units matching all 3 scores exactly | 16/40 | 21/40 | +5 |
| Disagreements | 54 | 32 | −22 |

**22 disagreements resolved, 0 new regressions.** The change is strictly monotonic — it only flipped wrong verdicts to correct ones, never the reverse. Resolved by property: F1 ×6, F2 ×6, F3 ×7, O1 ×3.

### Expected vs actual (your predictions)

- *“Factory Method agreement should rise sharply (was 38%).”* ✅ Factory F1 30%→90%, F2 40%→100%, F3 30%→100%. (F4/F5 unchanged — those are separate causes, see below.)

- *“Observer O1/O2 should improve (were 50% / 60%).”* ✅ **O1 50%→80%.** ❌ **O2 unchanged at 60%** — see the important note below: O2 is *not* broken by the interface issue.

- *“A few Factory cases (simple factories: ChatGPT POSS, possibly Meta) should STILL disagree.”* ❌ **This did not happen — and it is good news, explained next.**

- *“Strategy, Singleton, Composite-core unchanged.”* ✅ All identical to v1.

## Per-property reliability: before → after

| Prop | Before | After | Reliable now (≥80%)? |
|---|--:|--:|:--:|
| F1 | 30.0% | 90.0% ⬆ | ✅ |
| F2 | 40.0% | 100.0% ⬆ | ✅ |
| F3 | 30.0% | 100.0% ⬆ | ✅ |
| F4 | 40.0% | 40.0% | ❌ |
| F5 | 50.0% | 50.0% | ❌ |
| S1 | 100.0% | 100.0% | ✅ |
| S2 | 100.0% | 100.0% | ✅ |
| S3 | 80.0% | 80.0% | ✅ |
| S4 | 100.0% | 100.0% | ✅ |
| C1 | 60.0% | 60.0% | ❌ |
| C2 | 100.0% | 100.0% | ✅ |
| C3 | 100.0% | 100.0% | ✅ |
| C4 | 60.0% | 60.0% | ❌ |
| C5 | 40.0% | 40.0% | ❌ |
| O1 | 50.0% | 80.0% ⬆ | ✅ |
| O2 | 60.0% | 60.0% | ❌ |
| O3 | 70.0% | 70.0% | ❌ |
| O4 | 80.0% | 80.0% | ✅ |
| G1 | 100.0% | 100.0% | ✅ |

Still < 80% after the fix (all due to **separate, unrelated causes** left unfixed per your one-change constraint): **F4, F5, C1, C4, C5, O2, O3**.

## ⚠️ Important finding: the simple-factory rejection AGREES with Kim (it does not disagree)

Your Change 2 assumed our checker was *stricter* than Kim on the static/switch simple factories (ChatGPT POSS, Copilot POSS) and that rejecting them would keep us disagreeing with Kim. **The data shows the opposite.** Kim *also* fails F1 on both simple factories (his Table 13 / derived failing-property set lists “F1 fails” for ChatGPT POSS and Copilot POSS). So:

- **Before the fix**, our checker *wrongly passed* F1 on ChatGPT POSS (it matched the unrelated `abstract class SaleComponent`). That was the disagreement — we were too *loose*, not too strict.

- **After the fix**, F1 correctly fails on both simple factories, which **matches Kim**. ChatGPT POSS Factory now scores **80.00 / 84.62 / 81.85 — identical to Kim's published numbers.**

- **Net: there are ZERO remaining disagreements attributable to the simple-factory rejection.** The deliberate design decision still stands (and is documented in the code comment you asked for), but on Kim's corpus it *converges with* Kim rather than diverging. **There is nothing to cite as an intentional definitional difference on the simple factories** — Kim already treated them the same way.

> Per your constraint “if you find a second, unrelated cause of disagreement, STOP and report it”: this reversed premise is that report. I still implemented the rejection exactly as you specified (it is correct and it is what your criterion “no creator role played by subclasses” implies); I am only flagging that its *relationship to Kim* is agreement, not disagreement.

## Score-level: the units that moved

| Case | LLM | Pattern | Kim PIQS | v1 PIQS | v2 PIQS | v2 exact? |
|---|---|---|--:|--:|--:|:--:|
| POSS | ChatGPT | Factory | 81.85 | 100.00 | 81.85 | ✅ |
| POSS | ChatGPT | Observer | 100.00 | 77.73 | 100.00 | ✅ |
| POSS | Claude | Factory | 78.77 | 39.38 | 100.00 |  |
| POSS | Copilot | Factory | 81.85 | 18.15 | 60.62 |  |
| POSS | Gemini | Factory | 100.00 | 39.38 | 100.00 | ✅ |
| POSS | Meta | Factory | 100.00 | 39.38 | 100.00 | ✅ |
| POSS | Meta | Observer | 100.00 | 77.73 | 100.00 | ✅ |
| SWS | ChatGPT | Factory | 42.46 | 18.15 | 60.62 |  |
| SWS | Claude | Factory | 81.85 | 60.62 | 78.77 |  |
| SWS | Copilot | Observer | 100.00 | 0.00 | 22.27 |  |
| SWS | Gemini | Factory | 81.85 | 18.15 | 78.77 |  |
| SWS | Meta | Factory | 63.69 | 39.38 | 60.62 |  |

(Rows omitted where v1 and v2 are identical.) Full per-unit data: `kim_comparison.json` (v2) and `kim_comparison_v1.json`.

## Every remaining disagreement, classified (per your Step 5)

| Category | Count |
|---|--:|
| Deliberate — simple/static factory, not GoF (intended disagreement) | 0 |
| Kim lenient / numbers internally inconsistent (not our bug) | 6 |
| Genuine ambiguity in the property definition | 1 |
| Genuine remaining issue — SEPARATE cause, fix proposed, NOT applied | 25 |

**Deliberate simple-factory disagreements: 0** (see finding above). The remaining 32 split into Kim-side problems and separate unrelated causes I did **not** touch:

| Case | LLM | Pattern | Prop | Kim | Mine | Category | Note |
|---|---|---|---|:--:|:--:|---|---|
| POSS | ChatGPT | Strategy | S3 | S | · | BUG | S3 rejects strategy-as-parameter (context passes strategy as a method arg, not a stored field/setter). SEPARATE cause; not fixed. |
| POSS | ChatGPT | Composite | C5 | S | · | BUG | C5 uniform check keys off an arbitrary abstract_components[0]. SEPARATE cause; not fixed. |
| POSS | Claude | Factory | F4 | · | S | AMBIG | Kim marks F4 failed, but F2/F3/F4 are all weight 3 and arithmetically indistinguishable; the label is prose-derived. My F4 passes (createPayment returns new CashPayment). |
| POSS | Claude | Composite | C5 | S | · | BUG | C5 uniform check (arbitrary component[0]). SEPARATE cause; not fixed. |
| POSS | Copilot | Factory | F4 | S | · | BUG | Parser drops `createPayment(...) throws Exception {` (throws clause), so its Payment return type is invisible and F4 cannot fire. SEPARATE cause (parser); not fixed. |
| POSS | Copilot | Composite | C1 | · | S | BUG | Composite counts any interface (Strategy `Payment`, Observer) as a component; no real Composite exists. SEPARATE cause; not fixed. |
| POSS | Copilot | Composite | C4 | · | S | BUG | Register.addSale/addInventory mislabeled a composite. SEPARATE cause; not fixed. |
| POSS | Gemini | Composite | C1 | · | S | BUG | Interfaces counted as components; no real Composite. SEPARATE cause; not fixed. |
| POSS | Gemini | Composite | C4 | · | S | BUG | Spurious composite/leaf. SEPARATE cause; not fixed. |
| POSS | Gemini | Observer | O1 | S | · | KIM | Kim's numeric O1=satisfied is impossible: no abstract subject exists (ItemInventory is concrete). My O1=not satisfied matches the code. |
| POSS | Gemini | Observer | O2 | · | S | KIM | `interface InventoryObserver{void update}` exists, so O2 is defensibly satisfied; Kim's numeric O2=fail contradicts the code. |
| POSS | Gemini | Observer | O3 | · | S | KIM | notifyObservers iterates and calls update(); O3 defensibly satisfied. Kim's numeric O3=fail contradicts the code. |
| POSS | Gemini | Observer | O4 | · | S | KIM | Register implements update(); O4 defensibly satisfied. Kim's numeric O4=fail contradicts the code. |
| POSS | Meta | Composite | C5 | S | · | BUG | C5 uniform check (arbitrary component[0]). SEPARATE cause; not fixed. |
| SWS | ChatGPT | Factory | F5 | · | S | BUG | F5 counts Strategy implementers as 'products' (Wallet has no product interface). SEPARATE cause (product definition); not fixed. |
| SWS | ChatGPT | Observer | O3 | S | · | BUG | O3 rejects single-observer direct notification (`auditLog.update(...)`, no collection/loop). SEPARATE cause (observer notify shape); not fixed. |
| SWS | Claude | Factory | F4 | S | · | BUG | F4 only accepts abstract-typed products; createWallet returns the concrete `Wallet`. SEPARATE cause (concrete product); not fixed. |
| SWS | Claude | Factory | F5 | · | S | BUG | F5 counts Strategy implementers as products. SEPARATE cause; not fixed. |
| SWS | Copilot | Factory | F1 | · | S | KIM | Copilot's SWS genuinely has `abstract class WalletFactory` + `ConcreteWalletFactory extends WalletFactory`, so an abstract creator exists (my F1 now = satisfied). Kim's F1=fail while F2/F3/F4=pass is internally inconsistent. |
| SWS | Copilot | Factory | F4 | S | · | BUG | createWallet returns concrete `Wallet`; F4 only accepts abstract-typed products. SEPARATE cause; not fixed. |
| SWS | Copilot | Factory | F5 | · | S | BUG | F5 counts Strategy implementers as products. SEPARATE cause; not fixed. |
| SWS | Copilot | Strategy | S3 | S | · | BUG | S3 rejects strategy-as-parameter (Wallet.performTransaction takes the strategy as an arg). SEPARATE cause; not fixed. |
| SWS | Copilot | Observer | O2 | S | · | BUG | Observer callback is `notify(Transaction)`, not `update`; O2 hard-codes the name `update`. SEPARATE cause (method naming); not fixed. |
| SWS | Copilot | Observer | O3 | S | · | BUG | Wallet.notifyObservers calls `observer.notify(...)`, but O3 requires a literal `.update(`. SEPARATE cause (naming); not fixed. |
| SWS | Copilot | Observer | O4 | S | · | BUG | No observer_types found (callback named `notify`), so O4 fails. SEPARATE cause (naming); not fixed. |
| SWS | Gemini | Factory | F4 | S | · | BUG | createWallet returns concrete `Wallet`. SEPARATE cause (concrete product); not fixed. |
| SWS | Gemini | Factory | F5 | · | S | BUG | F5 counts Strategy implementers as products. SEPARATE cause; not fixed. |
| SWS | Gemini | Observer | O2 | S | · | BUG | Observer callback is `onLogEvent`, not `update`; O2 hard-codes `update`. SEPARATE cause (naming); not fixed. |
| SWS | Meta | Factory | F4 | S | · | KIM | Meta's SWS has NO factory class; Kim's F4=satisfied is indefensible. My F4=not satisfied matches the code. |
| SWS | Meta | Factory | F5 | · | S | BUG | F5 counts Strategy implementers as products. SEPARATE cause; not fixed. |
| SWS | Meta | Observer | O1 | S | · | BUG | `AuditLog extends Observable` (java.util.Observable); the JDK subject framework is invisible. SEPARATE cause (JDK framework); not fixed. |
| SWS | Meta | Observer | O2 | S | · | BUG | Uses java.util.Observer via Observable; no hand-rolled `update` interface. SEPARATE cause (JDK framework); not fixed. |

### Proposed fixes for the separate causes (NOT applied — for your review)

These are distinct from the interface issue and were left untouched:

- **F4 (concrete-typed products)** — SWS Claude/Copilot/Gemini: allow a factory method's product type to be a concrete class, not only an abstract type. **F4 (parser)** — POSS Copilot: fix `_METHOD_SIG_RE` to accept a `throws` clause so factory methods aren't dropped.

- **F5 (product definition)** — anchor 'product' to the type the factory method returns, so Strategy/Observer implementers stop counting as products (all 5 SWS false positives).

- **S3 (context)** — accept a class that uses a strategy via parameter/local, not only a stored field/setter.

- **C1/C4/C5 (Composite)** — anchor the component to a real part–whole hierarchy; compare the actual component's API against the specific composite/leaf (not `abstract_components[0]`).

- **O2/O3/O4 (Observer naming + JDK)** — do not hard-code the callback name `update`; recognise `notify`/`onLogEvent`/`java.util.Observer`, single-observer direct notification, and `Observable`.

- **Kim-side (cite, don't fix)** — POSS Gemini Observer; SWS Copilot F1; SWS Meta F4 are Kim's internally-inconsistent cells; our (now-correct) verdicts disagree with his numbers on purpose.


---

*Generated by `validation/make_report_v2.py`. Inputs: v1 snapshots + current v2 outputs. Scorer change limited to the interface-as-abstract-role concept; see `piqs_service_fix.diff`.*
