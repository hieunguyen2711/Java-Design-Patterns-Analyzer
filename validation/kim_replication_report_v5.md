# PIQS Scorer — Pass 4 (definitional changes: G1 idioms, F4 conditional concrete): v4 → v5

**Unlike passes 1–3, this pass deliberately changes what two predicates MEAN.** The oracle for this pass is the **mutation battery** (`validation/run_mutation_battery.py`, 12 purpose-built cases); Kim's agreement is secondary. Exactly two predicates changed; nothing else.

Diff (pass-4 only): `validation/piqs_service_fix_pass4.diff`. v4 outputs preserved as `*_v4.*`.

## What changed — OLD vs NEW meaning

**G1 (a singleton exists)** — now recognises all three canonical Java realisations:

| | OLD (≤v4) | NEW (v5) |
|---|---|---|
| classic in-class `private static Self instance` | ✅ | ✅ (unchanged) |
| Bill Pugh holder (instance in nested static class) | ❌ (only worked via the field-leak bug, fixed in pass 3) | ✅ static instance may live in a nested static holder |
| enum singleton (single constant) | ❌ (enums not even parsed) | ✅ a single-constant `enum` is the sole instance (implicitly private ctor) |
| accessor method | required name `getInstance` | any **static method returning the singleton's type** (name-independent) |

Still rejected: public constructor; accessor that returns `new` every call (no stored instance); an enum *constant group* (≥2 constants) used with a public static factory handing out non-enum instances.


**F4 (factory creates products of the correct type)** — now accepts a concrete product in a single-product domain:

| | OLD (≤v4) | NEW (v5) |
|---|---|---|
| returns abstract / in an abstract hierarchy | ✅ | ✅ (unchanged) |
| returns a **concrete** product, **no abstract product** type in the program | ❌ (penalised) | ✅ accepted (single-product domain, e.g. one `Wallet`) |
| abstract product hierarchy EXISTS but factory returns a concrete type OUTSIDE it | ❌ | ❌ (still fails) |

**S3 was considered and deliberately LEFT STRICT** — a context must store/hold the strategy (field/injected) and delegate; receiving it only as a method parameter does not satisfy S3. No change made.

## Mutation battery — THE ORACLE for this pass (all 12 match their label ✅)

Purpose-built cases, none from Kim's corpus; materialised under `validation/mutation_battery/`.

| Case | Property | Expected | Result |
|---|:--:|:--:|:--:|
| `g1_classic_field` | G1 | PASS | ✅ |
| `g1_bill_pugh_holder` | G1 | PASS | ✅ |
| `g1_enum_singleton` | G1 | PASS | ✅ |
| `g1_public_ctor` | G1 | FAIL | ✅ |
| `g1_new_every_call` | G1 | FAIL | ✅ |
| `g1_enum_constant_group` | G1 | FAIL | ✅ |
| `f4_concrete_single_product` | F4 | PASS | ✅ |
| `f4_abstract_hierarchy` | F4 | PASS | ✅ |
| `f4_abstract_exists_returns_outside` | F4 | FAIL | ✅ |
| `f4_returns_unrelated_non_product` | F4 | FAIL | ✅ |
| `s3_stored_field_delegates` | S3 | PASS | ✅ |
| `s3_parameter_only` | S3 | FAIL | ✅ |

(Includes the two S3 regression guards — stored-field context PASSES, parameter-only context FAILS — confirming S3 stayed strict.)

## Kim agreement (secondary) — v4 → v5

| Metric | v4 | v5 | Δ |
|---|--:|--:|--:|
| Property-level agreement | 141/160 (88.1%) | 146/160 (91.2%) | **+3.1 pts** |
| Units matching all 3 scores exactly | 26/40 | 30/40 | +4 |
| Disagreements | 19 | 14 | −5 |

Resolved (v4→v5): **SWS/Copilot G1** (holder idiom now recognised) and **SWS Claude/Copilot/Gemini/Meta F4** (concrete `Wallet`, no abstract wallet type → single-product domain). All expected. Full arc: 66.2 → 80.0 → 91.2 → 88.1 → **91.2%**.

## Per-property reliability v4 → v5 — only G1 and F4 moved (zero-regression check)

| Prop | v4 | v5 | Δ |
|---|--:|--:|:--:|
| F1 | 90.0% | 90.0% |  |
| F2 | 100.0% | 100.0% |  |
| F3 | 100.0% | 100.0% |  |
| F4 | 50.0% | 90.0% | **CHANGED** |
| F5 | 100.0% | 100.0% |  |
| S1 | 100.0% | 100.0% |  |
| S2 | 100.0% | 100.0% |  |
| S3 | 50.0% | 50.0% |  |
| S4 | 100.0% | 100.0% |  |
| C1 | 100.0% | 100.0% |  |
| C2 | 100.0% | 100.0% |  |
| C3 | 100.0% | 100.0% |  |
| C4 | 100.0% | 100.0% |  |
| C5 | 100.0% | 100.0% |  |
| O1 | 90.0% | 90.0% |  |
| O2 | 80.0% | 80.0% |  |
| O3 | 80.0% | 80.0% |  |
| O4 | 80.0% | 80.0% |  |
| G1 | 80.0% | 100.0% | **CHANGED** |

**Only F4 and G1 changed** (G1 80→100, F4 50→90). Every other predicate is byte-identical to v4 — confirmed by the property-level delta: the only cells that moved are G1/F4 (no unnamed predicate touched). S3 held at 50% (intentionally strict). Simple-factory rejection still holds (F1 90%, POSS ChatGPT/Copilot still fail F1). Kim-side inconsistent cells still (correctly) disagree.

## Remaining disagreements (14), classified

| Category | Count |
|---|--:|
| Kim's number contradicts the code (our verdict correct) — cite, do not match | 8 |
| S3 strategy-as-parameter — intentionally strict, LEFT UNCHANGED this pass | 5 |
| Genuine ambiguity in the property definition | 1 |

| Case | LLM | Pattern | Prop | Kim | Mine | Category | Why |
|---|---|---|---|:--:|:--:|---|---|
| POSS | ChatGPT | Strategy | S3 | S | · | DEFER-S3 | Strategy used via local/parameter, not a stored field. S3 intentionally strict (unchanged). |
| POSS | Claude | Factory | F4 | · | S | AMBIG | F2/F3/F4 all weight 3 and arithmetically indistinguishable; Kim's 'F4 fails' is prose-derived. Our F4=satisfied (returns new CashPayment in the PaymentStrategy hierarchy). |
| POSS | Claude | Strategy | S3 | S | · | DEFER-S3 | Strategy used via local/parameter. S3 intentionally strict (unchanged). |
| POSS | Copilot | Strategy | S3 | S | · | DEFER-S3 | Strategy used via local/parameter. S3 intentionally strict (unchanged). |
| POSS | Gemini | Strategy | S3 | S | · | DEFER-S3 | Strategy used via local/parameter. S3 intentionally strict (unchanged). |
| POSS | Gemini | Observer | O1 | S | · | KIM | No abstract subject exists; Kim's numeric O1=satisfied is impossible. Ours matches the code. |
| POSS | Gemini | Observer | O2 | · | S | KIM | InventoryObserver interface exists and is notified; O2 defensibly satisfied. Kim's O2=fail contradicts the code. |
| POSS | Gemini | Observer | O3 | · | S | KIM | ItemInventory loops observers calling update(); O3 defensibly satisfied. Kim's O3=fail contradicts the code. |
| POSS | Gemini | Observer | O4 | · | S | KIM | Register implements update(); O4 defensibly satisfied. Kim's O4=fail contradicts the code. |
| SWS | Copilot | Factory | F1 | · | S | KIM | `abstract class WalletFactory` + `ConcreteWalletFactory extends` genuinely exist. Kim's F1=fail while F2/F3/F4=pass is inconsistent. |
| SWS | Copilot | Strategy | S3 | S | · | DEFER-S3 | Strategy received as a method parameter, not stored. S3 is intentionally strict (unchanged); we cite the disagreement. |
| SWS | Gemini | Observer | O3 | · | S | KIM | AuditLog loops observers calling onLogEvent(); ConsoleLogger registered in main. Complete and wired; O3 defensibly satisfied. Kim's O3=fail contradicts the code. |
| SWS | Gemini | Observer | O4 | · | S | KIM | ConsoleLogger implements onLogEvent(); O4 defensibly satisfied. Kim's O4=fail contradicts the code. |
| SWS | Meta | Observer | O2 | S | · | KIM | `extends Observable` but no class implements Observer; structurally no abstract observer. Kim's O2=satisfied is lenient; ours is defensible. |

No genuine remaining bug: 8 Kim-side errors (cite), 5 deferred S3-as-parameter (intentional), 1 arithmetic ambiguity.

## Regression suites

- **Mutation battery:** 12/12 match their label (oracle).

- **Synthetic generality suite (pass-3):** 10/10 still pass — Fixes A–G intact (structural observer callbacks, JDK Observer, Composite hierarchy, throws-parser, class-scope fields, whole-token matching).

- **Kim corpus:** only G1/F4 cells changed; no unnamed predicate regressed.


---

*Generated by `validation/make_report_v5.py`. Two predicate-meaning changes only (G1, F4); see `piqs_service_fix_pass4.diff`. Oracle: `run_mutation_battery.py`. Kim's files never touched.*
