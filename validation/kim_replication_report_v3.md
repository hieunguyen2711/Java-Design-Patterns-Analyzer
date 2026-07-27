# PIQS Scorer — Pass 2 (structural bug fixes A–E): Before/After (v3)

**Five structural fixes applied, all keyed to code STRUCTURE (never to Kim's class/method/file names):**

- **A** — Observer callback detected by role (subject invokes it on its observers), not the hard-coded name `update`. Now `notify`, `onLogEvent`, … all work.

- **B** — JDK Observer framework recognised: `extends Observable` ⇒ abstract subject; `implements Observer` ⇒ abstract observer.

- **C** — F5 'product' anchored to the type a factory method *returns*, so Strategy/Observer implementers no longer count as products.

- **D** — Composite C1/C4/C5 anchored to a real part–whole hierarchy (a concrete implementor that holds a collection of the component type); C5 compares the *actual* component's API. C2/C3 unchanged.

- **E** — method-signature parser accepts an optional `throws` clause, so factory methods declared `throws` are parsed and their return type captured.


Diffs: pass-2 only `validation/piqs_service_fix_pass2.diff`; cumulative `git diff`. Prior outputs preserved as `*_v2.*`.

## Headline: v2 → v3

| Metric | v2 | v3 | Δ |
|---|--:|--:|--:|
| Property-level agreement | 128/160 (80.0%) | 146/160 (91.2%) | **+11.2 pts** |
| Units matching all 3 scores exactly | 21/40 | 31/40 | +10 |
| Disagreements | 32 | 14 | −18 |

Across all three passes: **66.2% → 80.0% → 91.2%**.

**20 disagreements resolved; 2 new (both are Kim-side — see below).**

### Your predictions vs actual

- *Observer callback other than `update`, in a notify loop → O2/O3/O4 pass.* ✅ (SWS Copilot `notify`, Gemini `onLogEvent`).

- *`extends Observable` + `implements Observer` → O1/O2 pass.* ✅ (synthetic test; SWS Meta O1 resolved via Observable).

- *Strategy interface but no Composite → C1/C4/C5 do NOT fire.* ✅ (Copilot/Gemini POSS; synthetic negative control).

- *Factory method with a `throws` clause → return type captured, F4 evaluable.* ✅ (POSS Copilot F4 resolved; synthetic test).

- Reliability lifts: **F5 50%→100%, C1 60%→100%, C4 60%→100%, C5 40%→100%, O2 60%→80%, O3 70%→80%.**

## Per-property reliability: v2 → v3

| Prop | v2 | v3 | Reliable (≥80%)? | In must-not-drop set |
|---|--:|--:|:--:|:--:|
| F1 | 90.0% | 90.0% | ✅ | yes |
| F2 | 100.0% | 100.0% | ✅ | yes |
| F3 | 100.0% | 100.0% | ✅ | yes |
| F4 | 40.0% | 50.0% ⬆ | ❌ | — |
| F5 | 50.0% | 100.0% ⬆ | ✅ | — |
| S1 | 100.0% | 100.0% | ✅ | yes |
| S2 | 100.0% | 100.0% | ✅ | yes |
| S3 | 80.0% | 90.0% ⬆ | ✅ | — (S3 deferred) |
| S4 | 100.0% | 100.0% | ✅ | yes |
| C1 | 60.0% | 100.0% ⬆ | ✅ | — |
| C2 | 100.0% | 100.0% | ✅ | yes |
| C3 | 100.0% | 100.0% | ✅ | yes |
| C4 | 60.0% | 100.0% ⬆ | ✅ | — |
| C5 | 40.0% | 100.0% ⬆ | ✅ | — |
| O1 | 80.0% | 90.0% ⬆ | ✅ | yes |
| O2 | 60.0% | 80.0% ⬆ | ✅ | — |
| O3 | 70.0% | 80.0% ⬆ | ✅ | — |
| O4 | 80.0% | 80.0% | ✅ | — |
| G1 | 100.0% | 100.0% | ✅ | yes |

Only **F4** remains < 80% — driven by the deferred F4-concrete choice and one ambiguity (all analysed below).

### Zero-regression check (your step 3)

Protected set (S1,S2,S4,C2,C3,G1,F1,F2,F3,O1): **no drops ✅**. 
O1 in fact rose 80%→90%. Every already-100% property stayed 100%.

## Score-level: units that moved (v2 → v3)

| Case | LLM | Pattern | Kim PIQS | v2 PIQS | v3 PIQS | v3 exact? |
|---|---|---|--:|--:|--:|:--:|
| POSS | ChatGPT | Strategy | 100.00 | 77.73 | 100.00 | ✅ |
| POSS | ChatGPT | Composite | 100.00 | 79.43 | 100.00 | ✅ |
| POSS | Claude | Composite | 100.00 | 79.43 | 100.00 | ✅ |
| POSS | Copilot | Factory | 81.85 | 60.62 | 81.85 | ✅ |
| POSS | Copilot | Composite | 38.29 | 79.43 | 38.29 | ✅ |
| POSS | Gemini | Composite | 38.29 | 79.43 | 38.29 | ✅ |
| POSS | Meta | Composite | 100.00 | 79.43 | 100.00 | ✅ |
| SWS | ChatGPT | Factory | 42.46 | 60.62 | 42.46 | ✅ |
| SWS | ChatGPT | Observer | 77.73 | 51.82 | 77.73 | ✅ |
| SWS | Claude | Factory | 81.85 | 78.77 | 60.62 |  |
| SWS | Copilot | Factory | 63.69 | 78.77 | 60.62 |  |
| SWS | Copilot | Observer | 100.00 | 22.27 | 100.00 | ✅ |
| SWS | Gemini | Factory | 81.85 | 78.77 | 60.62 |  |
| SWS | Gemini | Observer | 25.91 | 0.00 | 77.73 |  |
| SWS | Meta | Factory | 63.69 | 60.62 | 42.46 |  |
| SWS | Meta | Observer | 48.18 | 0.00 | 22.27 |  |

## Every remaining disagreement (14), classified (your step 4)

| Category | Count |
|---|--:|
| Kim's published number contradicts the code (our verdict correct) — cite, do not match | 9 |
| Definitional choice the author deferred (F4-concrete / S3) — left unchanged | 4 |
| Genuine ambiguity in the property definition | 1 |

**No 'genuine remaining bug' in the fixed buckets** — every remaining disagreement is either a Kim-side error, an explicitly deferred definitional choice, or one arithmetic ambiguity.

| Case | LLM | Pattern | Prop | Kim | Mine | Category | Why |
|---|---|---|---|:--:|:--:|---|---|
| POSS | Claude | Factory | F4 | · | S | AMBIG | F2/F3/F4 are all weight 3 and arithmetically indistinguishable; Kim's 'F4 fails' label is prose-derived. My F4=satisfied (createPayment returns new CashPayment). |
| POSS | Gemini | Observer | O1 | S | · | KIM | No abstract subject exists (ItemInventory concrete, no Subject interface); Kim's numeric O1=satisfied is impossible. My O1=not satisfied matches the code. |
| POSS | Gemini | Observer | O2 | · | S | KIM | `interface InventoryObserver{void update}` exists and is notified; O2 defensibly satisfied. Kim's numeric O2=fail contradicts the code. |
| POSS | Gemini | Observer | O3 | · | S | KIM | ItemInventory loops observers calling update(); O3 defensibly satisfied. Kim's numeric O3=fail contradicts the code. |
| POSS | Gemini | Observer | O4 | · | S | KIM | Register implements InventoryObserver.update(); O4 defensibly satisfied. Kim's numeric O4=fail contradicts the code. |
| SWS | Claude | Factory | F4 | S | · | DEFER | createWallet returns the CONCRETE `Wallet`; whether a concrete-typed product satisfies F4 is the deferred F4-concrete definitional choice. Left as-is per instructions. |
| SWS | Copilot | Factory | F1 | · | S | KIM | `abstract class WalletFactory` + `ConcreteWalletFactory extends WalletFactory` genuinely exist (my F1=satisfied). Kim's F1=fail while F2/F3/F4=pass is internally inconsistent. |
| SWS | Copilot | Factory | F4 | S | · | DEFER | createWallet returns concrete `Wallet` (deferred F4-concrete choice). Left as-is. |
| SWS | Copilot | Strategy | S3 | S | · | DEFER | Wallet.performTransaction receives the strategy as a parameter, not a stored field/setter; the S3 strategy-as-parameter choice was explicitly deferred. Left as-is. |
| SWS | Gemini | Factory | F4 | S | · | DEFER | createWallet returns concrete `Wallet` (deferred F4-concrete choice). Left as-is. |
| SWS | Gemini | Observer | O3 | · | S | KIM | AuditLog holds List<AuditLogObserver>, loops calling onLogEvent(); ConsoleLogger is registered in main (`user.auditLog.addObserver(new ConsoleLogger())`). The observer is complete AND wired; O3 defensibly satisfied. Kim's O3=fail contradicts the code. |
| SWS | Gemini | Observer | O4 | · | S | KIM | ConsoleLogger implements AuditLogObserver.onLogEvent(); O4 defensibly satisfied. Kim's O4=fail contradicts the code. |
| SWS | Meta | Factory | F4 | S | · | KIM | Meta's SWS has NO factory class; Kim's F4=satisfied is indefensible. My F4=not satisfied matches the code. |
| SWS | Meta | Observer | O2 | S | · | KIM | `AuditLog extends Observable` but NO class implements Observer and no custom observer interface exists, so structurally there is no abstract observer. Kim's O2=satisfied (crediting the imported-but-unimplemented JDK Observer) is lenient; our O2=not satisfied is defensible. |

The **SWS Gemini O3/O4** and **POSS Gemini O1–O4** disagreements are the automated scorer correctly detecting complete, wired Observer implementations that Kim's numeric tables mark as failing — i.e. the scorer disagreeing *rightly* with flawed manual cells. Cite these; do not chase them.

## ⚠️ Flagged: one incidental change + a newly-surfaced latent cause (your STOP-and-report rule)

**S3 for POSS/ChatGPT flipped fail→pass (S3 overall 80%→90%) — but for the WRONG reason, and I did not intend to touch S3.** Root cause: Fix E now lets `main()` (declared `throws Exception`) be parsed, which exposed two *pre-existing latent parser bugs*:

1. **Local variables are mis-parsed as fields.** Inside `main`, `PaymentStrategy payment = PaymentFactory.getPaymentMethod(...)` is captured as a `PaymentStrategy` *field* of `RefactoredPOSChatGPT`, so `is_context`'s field check trips.

2. **Substring method-name matching.** `is_context`'s 'execute' check does `"pay" in method_body`, and `"pay"` occurs inside `"payment"`/`"PaymentFactory"`, so it matches spuriously.

Together these make `is_context` true → S3 passes, coincidentally agreeing with Kim. **This is not a real S3 fix.** Per your instruction I have *flagged, not fixed* it. Treat S3's genuine reliability as unchanged (the deferred strategy-as-parameter limitation still stands; SWS Copilot S3 still correctly fails).

**This is the distinct sixth cause you asked me to stop on:** latent parser imprecision — (a) local-variable-as-field extraction and (b) substring (not token) matching of method names. It is out of scope for pass 2; I recommend a dedicated pass to (i) restrict field extraction to class scope, and (ii) match method names as whole tokens. No further edits were made.

## Synthetic generality tests (your step 5) — none from Kim's corpus

`validation/synthetic_generality_tests.py` — **all pass**:

| Test | Result |
|---|:--:|
| Fix A: observer callback named `ping` in a notify loop → O2/O3/O4 pass | ✅ |
| Fix B: `extends Observable` + `implements Observer` → O1/O2 pass | ✅ |
| Fix D: Strategy interface, no part–whole → C1/C4/C5 = 0 (C2 leaf still 1, unchanged) | ✅ |
| Fix D: genuine part–whole (Dir holds List<Node>, File leaf) → C1..C5 = 1 | ✅ |
| Fix E: factory method `create() throws Exception` → F1 & F4 evaluable/pass | ✅ |

## Per-fix result summary

| Fix | Predicates | Resolved (v2→v3) |
|---|---|---|
| A — structural observer callback | O2, O3, O4 | SWS Copilot O2/O3/O4, SWS Gemini O2, SWS ChatGPT O3 |
| B — JDK Observable/Observer | O1, O2 | SWS Meta O1 |
| C — F5 product = factory return type | F5 | SWS ChatGPT/Claude/Copilot/Gemini/Meta F5 (all 5) |
| D — Composite real hierarchy | C1, C4, C5 | POSS Copilot/Gemini C1+C4; POSS ChatGPT/Claude/Meta C5 |
| E — throws-parser | F4 (+ incidental S3, flagged) | POSS Copilot F4 |

*Generated by `validation/make_report_v3.py`. Scorer changes confined to structural rules for Fixes A–E; see `piqs_service_fix_pass2.diff`.*
