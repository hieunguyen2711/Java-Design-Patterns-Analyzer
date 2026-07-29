# Builder / Decorator / Template Method — final property spec

This is the reviewable record of what was implemented in
`app.services.piqs_service.PIQSService` for the three new GoF patterns. It records the final
`Bn / Dn / Tn` statements, their structural/behavioral tag, the final weight, the critical set,
and the Decorator-vs-Proxy limitation.

The metric formulas are **unchanged** from Kim's five existing patterns:

- **PSR** = satisfied / total × 100
- **CPC** = Σ(wᵢ·sᵢ) / Σ(wᵢ) × 100 — weighted average over **all** properties
- **PIQS** = PSR × 0.6 + CPC × 0.4

Weighting follows Kim's Table 9 philosophy (RULE 2), which overrides the draft's provisional
weights where they conflicted:

- **weight 3** — the relationship/behaviour that makes the pattern actually work (also the
  **critical set**: a program is recognised AS the pattern only when *all* its weight-3
  properties hold).
- **weight 2** — existence-of-a-role, and properties governing component interaction.
- **weight 1** — supporting / peripheral.

All detection is **structural** — return types, field types, call targets, abstract/concrete,
`extends`/`implements`. **Nothing is keyed to a class name, method name, or file path.** Roles
are detected by shape.

## Reused scaffolding

Base predicates reused verbatim from the five existing patterns: `isAbstract`, `isConcrete`,
`hasMethod`, `returns`, `implements`, `extends`, `overrides`, `accepts`, `calls`, `reads`,
`modifies`. Pass-3 precision work reused: whole-token identifier matching (`_calls_method`,
`_mentions_token`, `_has_verb_prefix`) and class-scope-only field extraction (`_class_scope_only`).
Substring name matching and method-local-variable-as-field are **not** reintroduced.

Two new AST helpers were added (the only ones the codebase lacked):

- **`callsWithin(method, target)`** — does `method`'s body invoke a method named exactly
  `target`? (whole-token; reused by D3 and T3). Implemented as `_calls_within`.
- **`fieldOfType(class, type)`** — does `class` hold a class-scope field of the given type?
  (reused by D2). Implemented as `_field_of_type`.

One infrastructure change: `JavaMethod.has_body` distinguishes a `;`-terminated declaration (an
abstract-class abstract method / bodyless interface method) from an empty-bodied concrete method
(`{}`). Both previously left `body == ""`; Template Method needs to tell them apart. The five
existing patterns never read this field.

Interface-vs-abstract handling follows the codebase rule: a Java **interface counts as an
abstract type** for any role that may be abstract; `isAbstract` is required only where a pattern
genuinely demands it.

---

## Builder — critical set {B1, B2}

Derived roles: `isBuilder`, `isProduct`, `isTerminalMethod`, `isStepMethod`, computed over each
candidate's **effective** (inherited) method/field set so a classic GoF builder split across an
abstract `Builder` (declares `getResult()`) and a `ConcreteBuilder` (defines void build-parts) is
seen as one builder family.

| ID | Statement | Tag | Weight |
|----|-----------|-----|--------|
| **B1** | `build()` returns a product distinct from the builder (a builder has step methods **and** a terminal method whose return type ≠ the builder type). | behavioral | **3** (critical) |
| **B2** | Step/configuration methods assemble the product: fluent-return-`this` **XOR** void-buildPart + `getResult()`. | behavioral | **3** (critical) |
| B3 | Builder type and product type are distinct. | structural | 2 |
| B4 | Telescoping-constructor avoidance / staged construction (a fluent chain, or ≥ 2 discrete step methods). | structural | 2 |
| B5 | Product effectively immutable — no public mutator for a built field (a non-project product, e.g. `String`, is treated as immutable). | structural | 1 |
| B6 | Director orchestrates **XOR** client drives the fluent chain (fluent steps ⇒ client-driven; else a non-builder/non-product type invokes a builder step method). | behavioral | 1 |

**Accepted variants (RULE 3):** interface / abstract-class / concrete static-nested builder;
`builder()` static factory or public constructor; builder reuse; mutable or immutable product
(B5 weight handles the difference). **Rejected:** a plain class with setters and no terminal
product-returning method (B1 fails); a "builder" whose `build()` returns the builder/`void`
(B1 fails).

---

## Decorator — critical set {D2, D3}

Derived roles: `isComponent` (an abstract type — interface or abstract class), `isDecorator`
(a class that conforms to a component **and** holds a field of that component type), `wraps`,
`delegatesTo`.

| ID | Statement | Tag | Weight |
|----|-----------|-----|--------|
| D1 | Decorator conforms to the **same** component type as what it wraps (is-a matches has-a). | structural | 2 |
| **D2** | Decorator holds a component-typed reference (composition). | structural | **3** (critical) |
| **D3** | Decorator delegates to the wrapped reference in its component methods (see the *any-vs-all* judgment call below). | behavioral | **3** (critical) |
| D4 | Transparent enhancement — no interface conversion: the decorator exposes the wrapped component's whole operation set (distinguishes from **Adapter**). | structural | 2 |
| D5 | Abstract decorator base / recursive composability — a collapsed single decorator is accepted (it wraps the component type, so it can wrap another decorator). | structural | 1 |
| D6 | **Full delegation (non-critical diagnostic)** — every implemented component operation forwards to the wrapped reference. Flags partial delegation *without* changing recognition. | behavioral | 1 |

**Accepted variants (RULE 3):** interface or abstract-class component; a collapsed single
decorator with no abstract base (D5 low-weight); constructor or setter injection of the wrapped
reference. **Rejected:** a subclass that extends the concrete component with no wrapped reference
(D2 fails); a wrapper that delegates to nothing (D3 fails).

### D3 semantics — the *any-vs-all* decision (RESOLVED)

D3 reads **"at least one component method delegates to the wrapped reference"** (existential). A
wrapper that delegates in some methods but hard-codes/ignores the delegate in others (*partial
delegation*) therefore **passes** D3. The stricter reading — "*all/most* component operations
forward" — would reject partial delegation, but it would **also** reject legitimate
method-suppressing decorators (read-only views, capability-reducing wrappers) that intentionally
short-circuit some operations.

**Decision (approved):** keep the critical D3 = existential "any", and add a **non-critical D6**
diagnostic that is satisfied only when *every* implemented component operation forwards. This gives
visibility into partial delegation without changing recognition (the critical set stays {D2, D3}).
The `t1_decorator_partial_delegation_accepted` case demonstrates it: recognised (D2=1, D3=1) with
**D6=0** flagging the incomplete forwarding; the five full-delegation decorators all score D6=1.
This mirrors the checker's accept-any-conforming-wrapper philosophy (it already accepts Proxy).

### Known limitation — Decorator vs Proxy (RULE 4, encoded not fixed)

Decorator and Proxy are **structurally identical** under static analysis: both conform to the
component interface, hold a component-typed reference, and delegate to it. "Adds behaviour"
(Decorator) vs "controls access" (Proxy) is a semantic intent that is **not statically
decidable**. This checker does **not** attempt to distinguish them — any structurally-conforming
wrapper is accepted as Decorator. This is stated in a code comment on `_evaluate_decorator` and
will be disclosed in the paper's threats to validity. (D4 distinguishes Decorator from *Adapter*,
which is decidable — an Adapter converts to a different interface — but makes **no** claim about
Proxy.)

This limitation is now **demonstrated**, not merely asserted: the battery case
`t3_decorator_lazy_proxy_KNOWN_LIMITATION` is a genuine lazy-init/virtual **Proxy** (holds the
component, delegates, but its added logic *controls access* — it creates the real subject on
first use). The checker recognises it as a Decorator (D2=1, D3=1, PIQS 100). The case carries an
in-source `// KNOWN LIMITATION` comment so reviewers see the accepted-Proxy fact directly.

---

## Template Method — critical set {T3}

Derived roles: `isAbstractClassType` (abstract class or interface), `isTemplateMethod` (a
concrete method that invokes ≥ 1 deferred operation), `isPrimitiveOp` (a bodyless abstract method
implemented by subclasses), `isHook` (a concrete overridable method the template invokes and a
subclass overrides — a default-body extension point).

| ID | Statement | Tag | Weight |
|----|-----------|-----|--------|
| T1 | A concrete template method exists in an abstract type (a fixed skeleton). | structural | 2 |
| T2 | ≥ 1 abstract primitive and/or hook deferred to subclasses. | structural | 2 |
| **T3** | The template body invokes the primitive/hook operations (inversion of control). | behavioral | **3** (critical) |
| T4 | Template method is `final` / non-overridable (non-`final` accepted, lower-scoring). | structural | 2 |
| T5 | Subclass overrides the primitives, **not** the template method. | behavioral | 2 |

**Accepted variants (RULE 3):** `final` or non-`final` template (T4 weight handles it); abstract
primitives or default-body hooks (T2). **Rejected:** an abstract "template" method (T1 fails — no
fixed skeleton); an abstract class with a concrete method but zero deferred steps (T2 fails); a
concrete method whose abstract siblings are never called from it (T3 fails).

A genuine primitive must declare a return type — this rejects pseudo-methods the signature regex
harvests from call expressions inside method bodies (e.g. `System.out.println(...)`), which would
otherwise fake inversion of control.

---

## Definitional decisions

These are explicit, recorded choices of the same kind as two decisions already made and documented
for the original five patterns:

- **F4 — concrete single product** is accepted as Factory Method when there is no abstract product
  hierarchy the factory bypasses (see the `_evaluate_factory_method` "Change 2" comment and the
  `f4_concrete_single_product` mutation case).
- **S3 — a strategy passed only as a method parameter** (not held as context state) is *rejected*
  as the Context role (see the `s3_parameter_only` mutation case).

New decision recorded in this work:

- **Template Method in an interface (Java-8 default method): ACCEPTED.** `isAbstractClassType`
  treats a Java interface as an abstract type, so an interface with a **default-method template**
  that calls **abstract interface primitives** is recognised as Template Method (T3 holds).
  *Justification:* a default method is a genuine concrete skeleton, the abstract interface methods
  are genuinely deferred to implementors, and this is a real, common modern idiom (e.g.
  `Comparator`, `Collector`-style helpers); accepting it is also consistent with the codebase's
  interface-as-abstract-role rule already applied to the other roles. Demonstrated by the MUST-PASS
  case `t4_template_interface_default_method` (an `interface Report` whose `default render()` calls
  abstract `header()`/`body()`), verified recognised (T3=1). The classic abstract-*class* form
  remains fully supported; this decision only *adds* the interface form, it does not replace it.

## Oracle

There is no Kim ground truth for these three patterns (Kim 2025 never covered them). The oracle is
`validation/mutation_battery_bdt/` + `validation/run_mutation_battery_bdt.py`:

- **CONFIRMED cases (27)** — 18 MUST-PASS (JDK-exemplar analogues + idiomatic variants, including
  the "discriminating middle" cases: genuine-enhance decorator, primitive+hook template, fluent
  interface builder, Java-8 default-method template, Proxy-as-Decorator) and 9 MUST-FAIL (degenerate
  forms: hollow builder, fluent-no-terminal builder, no-IoC / private-helper templates, no-delegation
  wrapper, plain inheritance). A case's verdict is "is the pattern" iff **all** critical (weight-3)
  properties hold. Every case matches its label and compiles under `javac`; these gate the exit code.
- **D6 diagnostics (5)** — demonstrate that the non-critical Decorator D6 flag separates partial
  (D6=0) from full (D6=1) delegation *without* changing recognition (every case stays recognised via
  the critical {D2,D3} set).

The three pass-5 probe cases that began as *open findings* were resolved after review (two Builder
gaps fixed, the Decorator D3 semantics decided) — see *Resolved findings* below. Per the
coverage-pass golden rule, no probe was forced green by a predicate change **before** approval.

## Resolved findings (pass-5 coverage probes → approved changes)

Three probe cases surfaced the "discriminating middle" and were **independently re-verified** (each
traced against the code and re-run through the scorer by a separate agent). All three are now
**resolved** with approval; the changes touch only `_evaluate_builder` / `_evaluate_decorator`
(new patterns) — the five original patterns are byte-identical (Kim 91.2% unchanged).

1. **Builder B2 — hollow steps (discrimination gap) → FIXED.**
   `t1_builder_hollow_steps_ignored`: a fluent step sets a builder field that `build()` ignores
   (product built with defaults) was wrongly recognised. **Fix applied:** a terminal now qualifies
   only if its body references a builder effective-field (whole token) **or** mentions `this` — so
   `return new Gadget();` is no longer a terminal (B1→0), while `new Pizza(this)`, `return product;`,
   `return value;`, `new Car(color, wheels)` are kept. Verified non-regressing across the whole
   builder battery and extra edge cases (abstract-class fluent, `this.field`-consuming terminal).
   *Documented caveat:* the `this` clause is a structural proxy — a pathological `new Gadget(this)`
   that ignores the arg still passes; full detection needs deeper dataflow. This is an accepted
   residual limitation, not a bug.

2. **Decorator D3 — partial delegation (judgment call) → DECIDED (keep "any" + add D6).**
   See *D3 semantics* above. Recognition stays existential ("any method delegates"); a **non-critical
   D6** diagnostic (weight 1) flags when not every operation forwards. `t1_decorator_partial_delegation_accepted`
   is recognised (D2=1, D3=1) with D6=0; the five full-delegation decorators score D6=1. Rationale
   for keeping "any": an "all/most" rule would wrongly reject canonical method-suppressing decorators
   (`Collections.unmodifiableList`, whose mutators throw instead of forwarding).

3. **Builder B1/B2 — fluent *interface* builder missed (discrimination gap) → FIXED.**
   `t2_builder_interface_fluent`: an idiomatic fluent builder whose steps return the **interface**
   type (`return this` typed as the abstraction) was not recognised. **Fix applied:** fluent-step
   detection broadened from `m.return_type == t.name` to also accept a return type the builder
   `_conforms_to` — so a step returning an interface/superclass the builder implements/extends counts.
   Verified non-regressing: the MUST-FAIL `builder_build_returns_this` and
   `t1_builder_fluent_setters_no_terminal` stay failing (no distinct-product terminal); the fix also
   generalises to abstract-class fluent builders. *Theoretical edge (absent from the battery):* a
   builder conforming to its own product type could lose its terminal under the broadened rule.

*(Parser note, benign — no action needed:* the interface default-method template's `render()` body
harvests a spurious `body` pseudo-method from the `body()` call expression; it is correctly filtered
by the `return_type is not None` guard and has zero effect on T3. The D6 helper applies the same
guard — it skips bodyless pseudo-methods so a call-harvested duplicate cannot mask a real method's
delegation.)*
