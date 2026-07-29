"""PIQS evaluation service with explicit base and derived predicates for 5 GoF patterns."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


_PATTERN_WEIGHTS = {
    "factory-method": {"F1": 2, "F2": 3, "F3": 3, "F4": 3, "F5": 2},
    "strategy": {"S1": 3, "S2": 3, "S3": 2, "S4": 3},
    "composite": {"C1": 3, "C2": 2, "C3": 3, "C4": 3, "C5": 3},
    "observer": {"O1": 2, "O2": 3, "O3": 3, "O4": 3},
    "singleton": {"G1": 3},
    # --- New patterns (Builder / Decorator / Template Method). Weights follow Kim's Table 9
    # philosophy (RULE 2): weight 3 = the enabling relationship/behaviour that makes the
    # pattern work (also the CRITICAL set); weight 2 = existence-of-a-role / interaction;
    # weight 1 = supporting/peripheral. See validation/bdt_property_spec.md.
    "builder": {"B1": 3, "B2": 3, "B3": 2, "B4": 2, "B5": 1, "B6": 1},
    "decorator": {"D1": 2, "D2": 3, "D3": 3, "D4": 2, "D5": 1, "D6": 1},
    "template-method": {"T1": 2, "T2": 2, "T3": 3, "T4": 2, "T5": 2},
}

# The critical property set per pattern -- the weight-3 relationship/behaviour properties.
# A program is recognised AS the pattern only when ALL of its critical properties hold; the
# BDT mutation battery keys its MUST-PASS / MUST-FAIL verdicts off exactly this set.
_CRITICAL_PROPERTIES = {
    "factory-method": {"F2", "F3", "F4"},
    "strategy": {"S1", "S2", "S4"},
    "composite": {"C1", "C3", "C4", "C5"},
    "observer": {"O2", "O3", "O4"},
    "singleton": {"G1"},
    "builder": {"B1", "B2"},
    "decorator": {"D2", "D3"},
    "template-method": {"T3"},
}

_DECL_RE = re.compile(
    r"\b(public\s+)?(?P<abs>abstract\s+)?(?P<kind>class|interface|enum)\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?:\s+extends\s+(?P<extends>[A-Za-z_][A-Za-z0-9_\.]*))?"
    r"(?:\s+implements\s+(?P<implements>[^\{]+))?\s*\{",
    re.MULTILINE,
)

# Fix E: an optional `throws <exceptions>` clause may sit between the parameter list and
# the opening brace/semicolon. Without this, methods like `create(...) throws IOException {`
# were not matched at all and their return type became invisible (breaking Factory F4).
_METHOD_SIG_RE = re.compile(
    r"(?P<mods>(?:(?:public|protected|private|static|final|abstract|synchronized)\s+)*)"
    r"(?:(?P<ret>[A-Za-z_][A-Za-z0-9_<>\[\]\.]*?)\s+)?"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\((?P<params>[^)]*)\)\s*"
    r"(?:throws\s+[A-Za-z_][A-Za-z0-9_,.\s]*?\s*)?"
    r"(?P<tail>\{|;)",
    re.MULTILINE,
)

_FIELD_RE = re.compile(
    r"(?m)^\s*(?P<mods>(?:(?:public|protected|private|static|final|volatile|transient)\s+)*)"
    r"(?P<type>[A-Za-z_][A-Za-z0-9_<>\[\]\.]*?)\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?:=[^;]*)?;"
)

_KEYWORD_NAMES = {
    "if",
    "for",
    "while",
    "switch",
    "catch",
    "return",
    "new",
    "throw",
    "case",
    "else",
    "do",
    "try",
    "finally",
}


@dataclass
class JavaField:
    name: str
    field_type: str
    modifiers: set[str] = field(default_factory=set)


@dataclass
class JavaMethod:
    name: str
    owner: str
    return_type: str | None
    param_types: list[str]
    param_names: list[str]
    modifiers: set[str]
    body: str
    is_constructor: bool
    # True when the declaration carried a brace body ("{ ... }"); False for a `;`-terminated
    # declaration (an abstract-class abstract method or a bodyless interface method). This is
    # the ONLY reliable way to tell an abstract primitive (`void step();`) from an
    # empty-bodied concrete method (`void step() {}`) -- both leave `body == ""`. Template
    # Method (T1/T2/T3) needs this distinction; the five original patterns never read it.
    has_body: bool = True


@dataclass
class JavaType:
    name: str
    kind: str
    is_abstract: bool
    extends: str | None
    implements: list[str] = field(default_factory=list)
    content: str = ""
    body: str = ""
    methods: list[JavaMethod] = field(default_factory=list)
    fields: list[JavaField] = field(default_factory=list)


class PIQSService:
    def evaluate(self, pattern_name: str, java_files: dict[str, str]) -> dict:
        normalized = pattern_name.strip().lower()
        if normalized not in _PATTERN_WEIGHTS:
            raise ValueError(
                "Unsupported pattern_name. Use one of: factory-method, strategy, "
                "composite, observer, singleton, builder, decorator, template-method."
            )

        types = self._extract_types(java_files)

        if normalized == "factory-method":
            base, derived, assessments = self._evaluate_factory_method(types)
        elif normalized == "strategy":
            base, derived, assessments = self._evaluate_strategy(types)
        elif normalized == "composite":
            base, derived, assessments = self._evaluate_composite(types)
        elif normalized == "observer":
            base, derived, assessments = self._evaluate_observer(types)
        elif normalized == "singleton":
            base, derived, assessments = self._evaluate_singleton(types)
        elif normalized == "builder":
            base, derived, assessments = self._evaluate_builder(types)
        elif normalized == "decorator":
            base, derived, assessments = self._evaluate_decorator(types)
        else:
            base, derived, assessments = self._evaluate_template_method(types)

        weights = _PATTERN_WEIGHTS[normalized]
        total_properties = len(assessments)
        satisfied = sum(1 for row in assessments if row["satisfaction"] == 1)
        weighted_earned = sum(row["weight"] * row["satisfaction"] for row in assessments)
        weighted_total = sum(weights.values())

        psr = (satisfied / total_properties) * 100 if total_properties else 0.0
        cpc = (weighted_earned / weighted_total) * 100 if weighted_total else 0.0
        piqs = (psr * 0.6) + (cpc * 0.4)

        return {
            "pattern_name": normalized,
            "files_analyzed": sorted(java_files.keys()),
            "base_predicates": base,
            "derived_predicates": derived,
            "logical_assessment": assessments,
            "breadth_calculation_psr": {
                "formula": f"({satisfied}/{total_properties})*100",
                "result_percent": round(psr, 2),
            },
            "depth_calculation_cpc": {
                "formula": f"({weighted_earned}/{weighted_total})*100",
                "result_percent": round(cpc, 2),
            },
            "final_quality_result_piqs": {
                "formula": f"({round(psr, 2)}*0.6)+({round(cpc, 2)}*0.4)",
                "result_percent": round(piqs, 2),
            },
            "grade": self._grade(piqs),
        }

    def _extract_types(self, java_files: dict[str, str]) -> dict[str, JavaType]:
        types: dict[str, JavaType] = {}

        for content in java_files.values():
            for match in _DECL_RE.finditer(content):
                name = match.group("name")
                kind = match.group("kind")
                extends_name = self._base_name(match.group("extends") or "") or None
                impl_raw = match.group("implements") or ""
                impl = [
                    self._base_name(part.strip().split()[-1])
                    for part in impl_raw.split(",")
                    if part.strip()
                ]
                is_abs = bool(match.group("abs")) or kind == "interface"
                body = self._extract_block(content, match.end() - 1)

                t = JavaType(
                    name=name,
                    kind=kind,
                    is_abstract=is_abs,
                    extends=extends_name,
                    implements=[x for x in impl if x],
                    content=content,
                    body=body,
                )
                t.methods = self._extract_methods(name, body)
                t.fields = self._extract_fields(body)
                types[name] = t

        return types

    def _extract_methods(self, owner: str, body: str) -> list[JavaMethod]:
        methods: list[JavaMethod] = []

        for m in _METHOD_SIG_RE.finditer(body):
            name = m.group("name")
            if name in _KEYWORD_NAMES:
                continue

            mods = {x for x in (m.group("mods") or "").split() if x}
            ret = self._base_name(m.group("ret") or "") or None
            is_ctor = ret is None and name == owner

            params = m.group("params") or ""
            param_types, param_names = self._parse_params(params)

            method_body = ""
            has_body = m.group("tail") == "{"
            if has_body:
                method_body = self._extract_block(body, m.end() - 1)

            methods.append(
                JavaMethod(
                    name=name,
                    owner=owner,
                    return_type=ret,
                    param_types=param_types,
                    param_names=param_names,
                    modifiers=mods,
                    body=method_body,
                    is_constructor=is_ctor,
                    has_body=has_body,
                )
            )

        return methods

    @staticmethod
    def _class_scope_only(body: str) -> str:
        """Fix F: return only the class-body text at brace-depth 0 -- every method,
        constructor, initialiser and nested-type body (and anything deeper) is stripped.
        Fields are declared at class scope; anything inside those removed blocks is a
        local variable and must not be captured as a field."""
        out: list[str] = []
        depth = 0
        for ch in body:
            if ch == "{":
                depth += 1
                continue
            if ch == "}":
                if depth > 0:
                    depth -= 1
                continue
            if depth == 0:
                out.append(ch)
        return "".join(out)

    @staticmethod
    def _calls_method(body: str, name: str) -> bool:
        """Fix G: True if `body` invokes a method named exactly `name` -- a whole
        identifier followed by '(' (so `pay` does not match inside `payment`)."""
        return re.search(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"\s*\(", body) is not None

    @staticmethod
    def _mentions_token(body: str, name: str) -> bool:
        """Fix G: True if `name` occurs in `body` as a whole identifier, not a substring."""
        return re.search(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])", body) is not None

    @staticmethod
    def _has_verb_prefix(name: str, verb: str) -> bool:
        """Fix G: True if `name` is exactly `verb`, or a camelCase method that begins with
        it (add -> add, addChild, addObserver, add_child) -- but NOT a word that merely
        starts with those letters (add -> address is False)."""
        if name == verb:
            return True
        if name.startswith(verb):
            rest = name[len(verb):]
            return bool(rest) and (rest[0].isupper() or rest[0].isdigit() or rest[0] == "_")
        return False

    @staticmethod
    def _enum_constant_count(body: str) -> int:
        """Count an enum's constants -- the comma-separated identifiers before the first
        top-level ';' (or the whole body if there is none). Nested parens/braces
        (constant arguments or bodies) are flattened so they don't inflate the count.
        A single-constant enum is the canonical enum-singleton (one instance)."""
        depth = 0
        seg: list[str] = []
        for ch in body:
            if ch in "{(":
                depth += 1
            elif ch in "})":
                if depth > 0:
                    depth -= 1
            elif ch == ";" and depth == 0:
                break
            else:
                seg.append(ch if depth == 0 else " ")
        count = 0
        for part in "".join(seg).split(","):
            part = part.strip()
            if not part:
                continue
            first = part.split()[0]
            if re.match(r"[A-Za-z_][A-Za-z0-9_]*$", first):
                count += 1
        return count

    # ------------------------------------------------------------------ #
    # New AST helpers (RULE 1): the only two base predicates the codebase lacked.
    # ------------------------------------------------------------------ #
    @classmethod
    def _calls_within(cls, method: "JavaMethod", target: str) -> bool:
        """callsWithin(method, target): does `method`'s body invoke a method named exactly
        `target`? Whole-token match (reuses the pass-3 precision rule via _calls_method), so
        `read` never matches inside `readLine`. Used by D3 (delegation) and T3 (inversion of
        control)."""
        return cls._calls_method(method.body, target)

    @staticmethod
    def _field_of_type(jtype: "JavaType", type_name: str) -> bool:
        """fieldOfType(class, type): does `jtype` hold a class-scope field whose (base) type is
        `type_name`? Reuses the pass-3 class-scope-only field extraction (no method-local
        variables). Used by D2 (decorator holds a component-typed reference)."""
        return any(f.field_type == type_name for f in jtype.fields)

    @staticmethod
    def _delegates_to_field(body: str, field_name: str) -> bool:
        """True if `body` invokes a method on the reference `field_name` -- `field.op(...)` or
        `this.field.op(...)` as a whole token. The structural signature of delegation (D3)."""
        return re.search(
            r"(?<![A-Za-z0-9_])(?:this\s*\.\s*)?" + re.escape(field_name) + r"\s*\.\s*[A-Za-z_]\w*\s*\(",
            body,
        ) is not None

    @staticmethod
    def _assigns_field(body: str, field_name: str) -> bool:
        """True if `body` assigns to the field `field_name` (`field = ...` or `this.field = ...`),
        not an equality test. Signals a configuration/build-part step that populates state."""
        return re.search(
            r"(?<![A-Za-z0-9_])(?:this\s*\.\s*)?" + re.escape(field_name) + r"\s*=(?!=)",
            body,
        ) is not None

    def _effective_methods(self, t: "JavaType", types: dict[str, "JavaType"]) -> list["JavaMethod"]:
        """`t`'s own methods plus those inherited from its project-defined `extends` ancestors.
        The Builder role is frequently split across an abstract Builder (declares the terminal
        getResult()) and a ConcreteBuilder (defines the void build-part steps); reasoning over
        the effective method set lets one detection see the whole builder family."""
        methods = list(t.methods)
        seen = {t.name}
        cur = t
        while cur.extends and cur.extends in types and cur.extends not in seen:
            parent = types[cur.extends]
            methods.extend(parent.methods)
            seen.add(parent.name)
            cur = parent
        return methods

    def _effective_fields(self, t: "JavaType", types: dict[str, "JavaType"]) -> list["JavaField"]:
        """`t`'s own class-scope fields plus those inherited from project-defined ancestors."""
        fields = list(t.fields)
        seen = {t.name}
        cur = t
        while cur.extends and cur.extends in types and cur.extends not in seen:
            parent = types[cur.extends]
            fields.extend(parent.fields)
            seen.add(parent.name)
            cur = parent
        return fields

    def _conforms_to(self, t: "JavaType", target: str, types: dict[str, "JavaType"]) -> bool:
        """True if `t` is-a `target` -- implements/extends it directly or transitively through
        project-defined supertypes. An interface parent counts exactly like an abstract-class
        parent (the interface-as-abstract-role rule already used by the five patterns)."""
        seen = set()
        stack = [t]
        while stack:
            cur = stack.pop()
            if cur.name in seen:
                continue
            seen.add(cur.name)
            supers = list(cur.implements) + ([cur.extends] if cur.extends else [])
            if target in supers:
                return True
            for s in supers:
                if s in types:
                    stack.append(types[s])
        return False

    @staticmethod
    def _component_type_names(types: dict[str, "JavaType"]) -> set[str]:
        """The abstract component types: every interface and every abstract class. A Decorator
        component and a Template-Method abstract type are both 'abstract types' in this sense
        (RULE 1: a Java interface counts as an abstract type)."""
        return {t.name for t in types.values() if t.is_abstract}

    def _extract_fields(self, body: str) -> list[JavaField]:
        fields: list[JavaField] = []
        # Fix F: parse field declarations only at class-body scope; local variables inside
        # method/constructor bodies must not be captured as fields.
        for m in _FIELD_RE.finditer(self._class_scope_only(body)):
            field_type = self._base_name(m.group("type") or "")
            if not field_type:
                continue
            mods = {x for x in (m.group("mods") or "").split() if x}
            fields.append(JavaField(name=m.group("name"), field_type=field_type, modifiers=mods))
        return fields

    def _evaluate_factory_method(self, types: dict[str, JavaType]) -> tuple[dict[str, bool], dict[str, bool], list[dict]]:
        abstract_types = [t for t in types.values() if t.is_abstract]
        concrete_types = [t for t in types.values() if not t.is_abstract and t.kind == "class"]
        known_type_names = set(types.keys())

        extends_exists = any(t.extends for t in concrete_types)
        implements_exists = any(t.implements for t in concrete_types)
        has_method_exists = any(t.methods for t in types.values())
        returns_exists = any(m.return_type for t in types.values() for m in t.methods if not m.is_constructor)

        # A concrete type's abstract parents are the project types it extends OR
        # implements. An interface parent counts exactly like an abstract-class parent:
        # implementing an interface establishes the same abstract-parent relationship
        # that extending an abstract class does.
        def _declared_parents(t):
            parents = []
            if t.extends and t.extends in types:
                parents.append(t.extends)
            for iface in t.implements:
                if iface in types:
                    parents.append(iface)
            return parents

        overrides_exists = False
        for t in concrete_types:
            parent_method_names = set()
            for parent in _declared_parents(t):
                parent_method_names |= {m.name for m in types[parent].methods}
            if parent_method_names & {m.name for m in t.methods}:
                overrides_exists = True
                break

        products = [t for t in abstract_types if t.kind in {"interface", "class"}]
        product_names = {t.name for t in products}

        creates_exists = False
        has_factory_exists = False
        is_product_exists = False
        is_creator_exists = False

        for t in types.values():
            for m in t.methods:
                if m.is_constructor:
                    continue
                if m.return_type in product_names:
                    has_factory_exists = has_factory_exists or (t.is_abstract or "abstract" in m.modifiers)
                    if re.search(r"\bnew\s+[A-Za-z_][A-Za-z0-9_]*\s*\(", m.body):
                        creates_exists = True

        # Fix C: a PRODUCT is the type RETURNED by a factory method (the creates/returns
        # relationship), not any type that merely implements some unrelated interface.
        # factory_product_types = return types of factory methods (declared by an abstract
        # creator, or a method that instantiates via `new`). F5 then fires only when a
        # concrete class implements/extends an ABSTRACT product interface that a factory
        # actually returns -- so Strategy/Observer implementers no longer count as products.
        factory_product_types = set()
        for t in types.values():
            for m in t.methods:
                if m.is_constructor:
                    continue
                if m.return_type in known_type_names and (
                    t.is_abstract or re.search(r"\bnew\s+[A-Za-z_]", m.body)
                ):
                    factory_product_types.add(m.return_type)
        is_product_exists = any(
            (not c.is_abstract)
            and c.kind == "class"
            and any(
                (p in c.implements or c.extends == p) and p in types and types[p].is_abstract
                for p in factory_product_types
            )
            for c in types.values()
        )

        for c in concrete_types:
            for parent in _declared_parents(c):
                parent_methods = {m.name: m for m in types[parent].methods}
                for m in c.methods:
                    if m.name in parent_methods and (m.return_type in product_names or parent_methods[m.name].return_type in product_names):
                        is_creator_exists = True

        base = {
            "isAbstract(x)": bool(abstract_types),
            "isConcrete(x)": bool(concrete_types),
            "hasMethod(c,m)": has_method_exists,
            "returns(m,t)": returns_exists,
            "implements(x,y)": implements_exists,
            "extends(x,y)": extends_exists,
            "overrides(m1,m2)": overrides_exists,
        }

        derived = {
            "creates(c,p)": creates_exists,
            "hasFactory(c,m)": has_factory_exists,
            "isProduct(x)": is_product_exists,
            "isCreator(c)": is_creator_exists,
        }

        # --- Abstract creator detection (Factory Method F1) ------------------------
        # An abstract creator is an abstract TYPE -- a Java `interface` OR an
        # `abstract class` -- that plays the creator role: it declares a factory method
        # (a non-constructor method whose return type is a project-defined product type)
        # and is implemented/extended by at least one concrete class.
        #
        # DESIGN DECISION (interface-as-abstract-role; see Kim replication study):
        #   * Interface creators ARE accepted as the abstract creator, exactly like an
        #     abstract class. A concrete class that `implements` the creator interface
        #     counts the same as one that `extends` an abstract creator class.
        #   * A static/switch "simple factory" -- a single CONCRETE class exposing a
        #     static create() method, with no abstract creator type -- is DELIBERATELY
        #     REJECTED as NOT GoF Factory Method: it has no abstract creator, so F1 is
        #     false by construction. This is an intentional, documented distinction, not
        #     an oversight.
        abstract_creators = []
        for t in types.values():
            if not t.is_abstract:
                continue
            declares_factory = any(
                (not m.is_constructor) and m.return_type in known_type_names
                for m in t.methods
            )
            has_concrete_impl = any(
                (not c.is_abstract) and c.kind == "class"
                and (c.extends == t.name or t.name in c.implements)
                for c in types.values()
            )
            if declares_factory and has_concrete_impl:
                abstract_creators.append(t)

        f1 = bool(abstract_creators)
        f2 = any(
            t.kind == "class" and not t.is_abstract and (
                (t.extends in types and types[t.extends].is_abstract)
                or any(i in types and types[i].is_abstract for i in t.implements)
            )
            for t in types.values()
        )
        f3 = overrides_exists

        # Change 2: F4 -- factory methods create products of the correct type.
        #   A factory method is a non-constructor method that instantiates via `new` and
        #   returns a project-defined type (the product).
        #   * in-hierarchy: the returned type is abstract, or implements/extends an abstract
        #     type -> F4 passes (unchanged, classic behaviour).
        #   * single concrete product: the returned type is a concrete standalone type AND the
        #     program has no abstract product hierarchy that the factory bypasses (no factory
        #     returns an abstract product, and no concrete type created inside a factory method
        #     implements/extends an abstract type) -> accept the concrete product (single-
        #     product domain, e.g. one concrete Wallet with no abstract wallet type).
        #   * if an abstract product hierarchy DOES exist but the factory returns a concrete
        #     type outside it -> F4 still fails.
        _new_call_re = re.compile(r"\bnew\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")

        def _returns_in_hierarchy(rname):
            rt = types.get(rname)
            if rt is None:
                return False
            if rt.is_abstract:
                return True
            for sup in list(rt.implements) + ([rt.extends] if rt.extends else []):
                st = types.get(sup)
                if st is not None and st.is_abstract:
                    return True
            return False

        factory_methods = [
            m
            for t in types.values()
            for m in t.methods
            if not m.is_constructor and m.return_type in known_type_names and _new_call_re.search(m.body)
        ]

        abstract_product_exists = False
        for m in factory_methods:
            if _returns_in_hierarchy(m.return_type) and types[m.return_type].is_abstract:
                abstract_product_exists = True
            for xname in _new_call_re.findall(m.body):
                xt = types.get(xname)
                if xt is None:
                    continue
                for sup in list(xt.implements) + ([xt.extends] if xt.extends else []):
                    st = types.get(sup)
                    if st is not None and st.is_abstract:
                        abstract_product_exists = True

        f4_in_hierarchy = any(_returns_in_hierarchy(m.return_type) for m in factory_methods)
        f4_concrete = (
            any(not _returns_in_hierarchy(m.return_type) for m in factory_methods)
            and not abstract_product_exists
        )
        f4 = f4_in_hierarchy or f4_concrete
        f5 = is_product_exists

        rows = [
            self._row("F1", 2, f1, "Abstract creator class exists."),
            self._row("F2", 3, f2, "Abstract creator has concrete implementation."),
            self._row("F3", 3, f3, "Concrete creator overrides factory method."),
            self._row("F4", 3, f4, "Factory method creates product of correct abstract type."),
            self._row("F5", 2, f5, "Concrete products implement abstract product interfaces."),
        ]
        return base, derived, rows

    def _evaluate_strategy(self, types: dict[str, JavaType]) -> tuple[dict[str, bool], dict[str, bool], list[dict]]:
        interfaces = [t for t in types.values() if t.kind == "interface"]
        concrete_classes = [t for t in types.values() if t.kind == "class" and not t.is_abstract]

        implemented_by: dict[str, list[JavaType]] = {
            i.name: [c for c in concrete_classes if i.name in c.implements] for i in interfaces
        }
        strategy_ifaces = [name for name, impls in implemented_by.items() if impls]

        strategy_method_names = set()
        for iface_name in strategy_ifaces:
            iface = types.get(iface_name)
            if iface:
                strategy_method_names.update(m.name for m in iface.methods)

        accepts_exists = any(
            any(pt in strategy_ifaces for pt in m.param_types)
            for t in types.values()
            for m in t.methods
        )

        calls_exists = any(
            re.search(r"\.[A-Za-z_][A-Za-z0-9_]*\s*\(", m.body) is not None
            for t in types.values()
            for m in t.methods
        )

        is_context = False
        is_set_strategy = False
        is_execute_strategy = False
        delegates = False
        has_strategy = False

        for c in concrete_classes:
            field_strategy = any(f.field_type in strategy_ifaces for f in c.fields)
            setter = any(self._has_verb_prefix(m.name, "set") and any(pt in strategy_ifaces for pt in m.param_types) for m in c.methods)
            # Fix G: invoke-by-whole-token, not `"pay" in body` (which matched "payment").
            execute = any(
                any(self._calls_method(m.body, name) for name in strategy_method_names)
                for m in c.methods
            )

            has_strategy = has_strategy or field_strategy or setter
            is_set_strategy = is_set_strategy or setter
            is_execute_strategy = is_execute_strategy or execute
            delegates = delegates or execute
            is_context = is_context or ((field_strategy or setter) and execute)

        is_algorithm = bool(strategy_method_names)
        algorithm_method = any(
            any(m.name in strategy_method_names for m in c.methods)
            for c in concrete_classes
            if any(i in strategy_ifaces for i in c.implements)
        )
        is_strategy = bool(strategy_ifaces)

        base = {
            "isAbstract(x)": bool(interfaces),
            "isConcrete(x)": bool(concrete_classes),
            "accepts(m,p)": accepts_exists,
            "hasMethod(c,m)": any(t.methods for t in types.values()),
            "calls(m1,m2)": calls_exists,
            "implements(x,y)": any(c.implements for c in concrete_classes),
        }

        derived = {
            "isAlgorithm(m)": is_algorithm,
            "algorithmMethod(m)": algorithm_method,
            "isStrategy(x)": is_strategy,
            "hasStrategy(c,s)": has_strategy,
            "isSetStrategy(m)": is_set_strategy,
            "isExecuteStrategy(m)": is_execute_strategy,
            "isContext(x)": is_context,
            "delegates(c,s)": delegates,
        }

        s1 = is_strategy
        s2 = bool(strategy_ifaces) and all(implemented_by.get(i) for i in strategy_ifaces)
        s3 = is_context
        s4 = algorithm_method

        rows = [
            self._row("S1", 3, s1, "Abstract strategy interface exists."),
            self._row("S2", 3, s2, "Every strategy interface has a concrete implementation."),
            self._row("S3", 2, s3, "Context class manages strategies."),
            self._row("S4", 3, s4, "Concrete strategies implement algorithm method."),
        ]
        return base, derived, rows

    def _evaluate_composite(self, types: dict[str, JavaType]) -> tuple[dict[str, bool], dict[str, bool], list[dict]]:
        abstract_components = [t for t in types.values() if t.kind == "interface" or t.is_abstract]
        component_names = {t.name for t in abstract_components}

        concrete_components = [
            t
            for t in types.values()
            if t.kind == "class" and not t.is_abstract and (t.extends in component_names or any(i in component_names for i in t.implements))
        ]

        # Fix G: recognise add/remove operations by whole-token camelCase verb prefix
        # (add, addChild, addComponent) -- not by substring ("add" also occurs in "address").
        is_add = any(self._has_verb_prefix(m.name, "add") for t in concrete_components for m in t.methods)
        is_remove = any(self._has_verb_prefix(m.name, "remove") for t in concrete_components for m in t.methods)

        accepts_exists = any(any(pt in component_names for pt in m.param_types) for t in concrete_components for m in t.methods)

        composites = [
            t
            for t in concrete_components
            if any(self._has_verb_prefix(m.name, "add") or self._has_verb_prefix(m.name, "remove") for m in t.methods)
        ]
        leaves = [t for t in concrete_components if t not in composites]

        has_children = any(re.search(r"\b(List|Set|Collection)<", t.body) for t in composites)
        contains_component = any(
            any(pt in component_names for m in t.methods for pt in m.param_types)
            for t in composites
        )
        is_add_child = any(any(self._has_verb_prefix(m.name, "add") for m in t.methods) for t in composites)
        is_remove_child = any(any(self._has_verb_prefix(m.name, "remove") for m in t.methods) for t in composites)

        base = {
            "isAbstract(x)": bool(abstract_components),
            "isConcrete(x)": bool(concrete_components),
            "accepts(m,p)": accepts_exists,
            "hasMethod(c,m)": any(t.methods for t in types.values()),
            "isAdd(m)": is_add,
            "isRemove(m)": is_remove,
            "implements(x,y)": any(t.implements for t in concrete_components),
        }

        derived = {
            "isComponent(x)": bool(component_names),
            "hasChildren(x)": has_children,
            "isAddChild(m)": is_add_child,
            "isRemoveChild(m)": is_remove_child,
            "containsComponent(x,y)": contains_component,
            "isComposite(x)": bool(composites),
            "isLeaf(x)": bool(leaves),
        }

        # Fix D: a REAL Composite requires an actual part-whole hierarchy, not merely the
        # presence of some interface. For each abstract component, a COMPOSITE is a concrete
        # implementor that HOLDS A COLLECTION of that component type; a LEAF is a concrete
        # implementor that does not. C1/C4/C5 fire only when such a real hierarchy exists,
        # so programs whose only interfaces are Strategy/Observer (no part-whole structure)
        # no longer produce spurious component/composite detections. C2/C3 keep their prior
        # (already-100%-agreeing) behaviour.
        elem_re = re.compile(
            r"\b(?:List|Set|Collection|ArrayList|LinkedList|HashSet|CopyOnWriteArrayList|Vector)"
            r"\s*<\s*([A-Za-z_][A-Za-z0-9_]*)\s*>"
        )
        real_components = []
        for comp in abstract_components:
            impls = [
                t
                for t in types.values()
                if t.kind == "class"
                and not t.is_abstract
                and (t.extends == comp.name or comp.name in t.implements)
            ]
            comp_composites = [t for t in impls if comp.name in elem_re.findall(t.body)]
            comp_leaves = [t for t in impls if t not in comp_composites]
            if comp_composites:
                real_components.append((comp, comp_composites, comp_leaves))

        real_c5 = False
        for comp, comp_composites, comp_leaves in real_components:
            if comp_composites and comp_leaves:
                api = {m.name for m in comp.methods}
                if api and all(api <= {m.name for m in x.methods} for x in comp_composites) and all(
                    api <= {m.name for m in x.methods} for x in comp_leaves
                ):
                    real_c5 = True
                    break

        c1 = bool(real_components)                                        # real abstract component
        c2 = bool(leaves)                                                 # unchanged
        c3 = bool(composites)                                             # unchanged
        c4 = any(cc and lv for (_, cc, lv) in real_components)            # real composite AND leaf
        c5 = real_c5                                                      # uniform over the ACTUAL component API

        rows = [
            self._row("C1", 3, c1, "Abstract component exists."),
            self._row("C2", 2, c2, "Leaf type exists."),
            self._row("C3", 3, c3, "Composite type exists."),
            self._row("C4", 3, c4, "Composite and leaf implement component."),
            self._row("C5", 3, c5, "Uniform composite/leaf treatment is possible."),
        ]
        return base, derived, rows

    def _evaluate_observer(self, types: dict[str, JavaType]) -> tuple[dict[str, bool], dict[str, bool], list[dict]]:
        class_types = [t for t in types.values() if t.kind == "class"]

        # --- Fix B: JDK Observer framework (java.util.Observable / java.util.Observer).
        # These are abstract framework types not declared in the project. A class that
        # `extends Observable` fills the (abstract) subject role; a class that
        # `implements Observer` fills the (abstract) observer role. Keyed off the framework
        # type names, never off the user's class names.
        jdk_subjects = [t for t in class_types if t.extends == "Observable"]
        jdk_observers = [t for t in class_types if "Observer" in t.implements]

        # --- Fix A: detect the observer callback by STRUCTURE, not by the name `update`.
        # A subject notifies either (a) by iterating a collection of observers and invoking
        # a method on each element, or (b) by invoking a method on a single held observer
        # reference. The invoked method is the callback (ANY name -- update, notify,
        # onLogEvent, ...); the element/field type is the observer type.
        elem_field_re = re.compile(
            r"\b(?:List|Set|Collection|ArrayList|LinkedList|HashSet|CopyOnWriteArrayList|Vector)"
            r"\s*<\s*([A-Za-z_][A-Za-z0-9_]*)\s*>\s+([A-Za-z_][A-Za-z0-9_]*)"
        )
        foreach_re = re.compile(
            r"for\s*\(\s*(?:final\s+)?[A-Za-z_][A-Za-z0-9_<>\[\]]*\s+"
            r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)"
        )

        observer_type_names = set()
        callback_names = set()
        notifies_loop = False
        notifies_single = False

        for t in class_types:
            coll_fields = {name: elem for (elem, name) in elem_field_re.findall(t.body)}
            single_obs_fields = {
                f.name: f.field_type
                for f in t.fields
                if f.field_type in types and types[f.field_type].is_abstract
            }
            for m in t.methods:
                body = m.body
                # (a) loop-based notification: for (X v : coll) { v.callback(...) }
                for (var, coll) in foreach_re.findall(body):
                    elem = coll_fields.get(coll)
                    if not elem or elem not in types:
                        continue
                    calls = re.findall(r"\b" + re.escape(var) + r"\.([A-Za-z_][A-Za-z0-9_]*)\s*\(", body)
                    if calls:
                        observer_type_names.add(elem)
                        callback_names.update(calls)
                        notifies_loop = True
                # (b) single held observer of an abstract type that has a concrete impl
                for fname, ftype in single_obs_fields.items():
                    has_impl = any(
                        (not c.is_abstract) and c.kind == "class"
                        and (c.extends == ftype or ftype in c.implements)
                        for c in class_types
                    )
                    if not has_impl:
                        continue
                    calls = re.findall(r"\b" + re.escape(fname) + r"\.([A-Za-z_][A-Za-z0-9_]*)\s*\(", body)
                    if calls:
                        observer_type_names.add(ftype)
                        callback_names.update(calls)
                        notifies_single = True

        observer_type_objs = [types[n] for n in observer_type_names if n in types]
        observer_names = set(observer_type_names) | {o.name for o in jdk_observers}

        # Subject candidates (registration/notification role): interface or class declaring
        # registration/notification methods (unchanged from prior behaviour), augmented with
        # JDK Observable subclasses.
        subject_candidates = [
            t
            for t in types.values()
            if t.kind in {"class", "interface"}
            and any(
                m.name in {"attach", "detach", "notifyObservers", "register", "remove", "notify"}
                for m in t.methods
            )
        ]

        reads = any(re.search(r"\bget[A-Z][A-Za-z0-9_]*\s*\(", m.body) for t in types.values() for m in t.methods)
        modifies = any(re.search(r"\bset[A-Z][A-Za-z0-9_]*\s*\(", m.body) for t in types.values() for m in t.methods)
        modifies_collection = any(
            re.search(r"\.(add|remove|clear)\s*\(", m.body)
            for t in subject_candidates
            for m in t.methods
        )
        traverses_collection = notifies_loop
        increases = any(re.search(r"\.add\s*\(", m.body) for t in subject_candidates for m in t.methods)
        decreases = any(re.search(r"\.remove\s*\(", m.body) for t in subject_candidates for m in t.methods)

        calls_exists = any(re.search(r"\.[A-Za-z_][A-Za-z0-9_]*\s*\(", m.body) for t in types.values() for m in t.methods)

        is_register = any(m.name in {"attach", "register"} for t in subject_candidates for m in t.methods)
        is_unregister = any(m.name in {"detach", "remove"} for t in subject_candidates for m in t.methods)
        is_notify = any(m.name in {"notifyObservers", "notify"} for t in subject_candidates for m in t.methods)

        notifies_observers = notifies_loop or notifies_single

        concrete_observers = [
            t
            for t in class_types
            if any(obs == t.extends or obs in t.implements for obs in observer_names)
        ]

        # O4: every concrete observer implements the callback (ANY name), or the JDK Observer.
        observers_update = bool(concrete_observers) and all(
            bool(callback_names & {m.name for m in t.methods}) or ("Observer" in t.implements)
            for t in concrete_observers
        )

        base = {
            "isAbstract(x)": any(t.is_abstract for t in types.values()),
            "isConcrete(x)": any(t.kind == "class" and not t.is_abstract for t in types.values()),
            "reads(m,p)": reads,
            "modifies(m,p)": modifies,
            "modifiesCollection(m,c,p)": modifies_collection,
            "traversesCollection(m,c)": traverses_collection,
            "increases(m,c)": increases,
            "decreases(m,c)": decreases,
            "hasMethod(c,m)": any(t.methods for t in types.values()),
            "calls(m1,m2)": calls_exists,
            "implements(x,y)": any(t.implements for t in types.values() if t.kind == "class"),
        }

        derived = {
            "isObserver(x)": bool(observer_type_objs) or bool(jdk_observers),
            "isUpdate(m)": bool(callback_names),
            "isSubject(x)": bool(subject_candidates) or bool(jdk_subjects),
            "isRegisterObserver(m)": is_register,
            "isUnregisterObserver(m)": is_unregister,
            "isNotify(m)": is_notify,
            "notifies(s,o)": notifies_observers,
            "updates(o,s)": observers_update,
        }

        # O1: an ABSTRACT subject exists -- an interface/abstract-class subject, OR a class
        #     extending the abstract JDK Observable (Fix B).
        o1 = any(t.is_abstract for t in subject_candidates) or bool(jdk_subjects)
        # O2: an ABSTRACT observer exists -- a structurally-detected observer interface/
        #     abstract class, OR a class implementing the abstract JDK Observer (Fix B).
        o2 = any(t.is_abstract for t in observer_type_objs) or bool(jdk_observers)
        # O3: the subject actually notifies observers -- collection loop or single held
        #     observer -- regardless of the callback's name (Fix A).
        o3 = notifies_observers
        # O4: concrete observers implement the callback (any name) / the JDK Observer.
        o4 = observers_update

        rows = [
            self._row("O1", 2, o1, "At least one abstract subject exists."),
            self._row("O2", 3, o2, "At least one abstract observer exists."),
            self._row("O3", 3, o3, "Subject notifies all registered observers."),
            self._row("O4", 3, o4, "Observers implement update behavior."),
        ]
        return base, derived, rows

    def _evaluate_singleton(self, types: dict[str, JavaType]) -> tuple[dict[str, bool], dict[str, bool], list[dict]]:
        classes = [t for t in types.values() if t.kind == "class"]
        enums = [t for t in types.values() if t.kind == "enum"]

        has_private_ctor = False
        has_static_instance = False
        has_instance_method = False
        has_singleton = False

        is_private = False
        is_static = False
        field_type = False
        belongs_to = False
        has_constructor = False
        accesses_field = False
        returns = False
        calls = False

        # A static instance of `cname` may be declared in the singleton class itself OR in a
        # nested static holder class (Bill Pugh idiom) -- so look across ALL classes for a
        # static field whose type is the singleton's type.
        def static_instance_of(cname: str) -> bool:
            return any(
                "static" in f.modifiers and f.field_type == cname
                for other in classes
                for f in other.fields
            )

        for c in classes:
            ctors = [m for m in c.methods if m.is_constructor]
            has_constructor = has_constructor or bool(ctors)
            priv_ctor = bool(ctors) and all("private" in m.modifiers for m in ctors)
            # Accessor: a static method returning the class's own type (a private ctor makes
            # any such method the single access point). Name-independent.
            accessor = [
                m for m in c.methods
                if not m.is_constructor and "static" in m.modifiers and m.return_type == c.name
            ]
            has_inst = static_instance_of(c.name)

            if priv_ctor:
                has_private_ctor = True
                is_private = True
            if has_inst:
                has_static_instance = True
                is_static = True
                field_type = True
                belongs_to = True
            if accessor:
                has_instance_method = True
                returns = True
                for m in accessor:
                    if any(self._mentions_token(m.body, f.name) for c2 in classes for f in c2.fields
                           if "static" in f.modifiers and f.field_type == c.name):
                        accesses_field = True
                    if re.search(rf"\bnew\s+{c.name}\s*\(", m.body):
                        calls = True

            # Change 1 (idiom i & ii): classic in-class field singleton AND Bill Pugh holder
            # idiom -- both require a private ctor, a static accessor returning the type, and a
            # static instance of the type (in the class or a nested static holder).
            if priv_ctor and accessor and has_inst:
                has_singleton = True

        # Change 1 (idiom iii): an enum with exactly ONE constant is a singleton -- the single
        # constant is the sole instance, and an enum's constructor is implicitly private.
        enum_singleton = any(self._enum_constant_count(e.body) == 1 for e in enums)
        if enum_singleton:
            has_singleton = True
            has_private_ctor = True
            has_static_instance = True
            has_instance_method = True
            is_private = is_static = True

        base = {
            "isPrivate(x)": is_private,
            "isStatic(x)": is_static,
            "fieldType(f,t)": field_type,
            "belongsTo(f,c)": belongs_to,
            "hasConstructor(c,m)": has_constructor,
            "accessesField(m,f)": accesses_field,
            "returns(m,t)": returns,
            "calls(m1,m2)": calls,
        }

        derived = {
            "isSingleton(x)": has_singleton,
            "hasPrivateConstructor(x)": has_private_ctor,
            "hasInstanceMethod(x)": has_instance_method,
            "hasStaticInstance(x,f)": has_static_instance,
        }

        rows = [
            self._row(
                "G1",
                3,
                has_singleton,
                "Singleton exists (classic in-class field, Bill Pugh holder, or single-constant enum).",
            )
        ]
        return base, derived, rows

    # ================================================================== #
    # Builder
    # ================================================================== #
    def _evaluate_builder(self, types: dict[str, JavaType]) -> tuple[dict[str, bool], dict[str, bool], list[dict]]:
        """Builder: a builder object assembles a distinct product through step/configuration
        methods, replacing a telescoping constructor.

        Derived roles (structural, never name-keyed):
          isBuilder(T)        -- T has configuration step methods (fluent return-this OR
                                 void build-part) over its effective (inherited) method set.
          isTerminalMethod(m) -- a concrete instance method of a builder whose return type is a
                                 type DISTINCT from the builder (the built product).
          isProduct(P)        -- the return type of a terminal method.
          isStepMethod(m)     -- fluent step (returns the builder type) OR void build-part
                                 (a void method that populates state: assigns a field or mutates
                                 a held field via a method call).

        Accepted variants (RULE 3): interface / abstract-class / concrete static-nested builder;
        builder() static factory OR public constructor; mutable OR immutable product (B5 weight
        handles the difference); fluent chaining OR Director orchestration.
        """
        classes = [t for t in types.values() if t.kind in {"class", "enum"}]

        # Per-candidate role analysis over the EFFECTIVE (inherited) method/field set, so a
        # classic GoF builder -- abstract Builder.getResult() + ConcreteBuilder void steps -- is
        # seen as one builder family.
        builder_infos = []  # (type, fluent_steps, void_steps, terminals, step_names)
        for t in classes:
            em = self._effective_methods(t, types)
            ef = self._effective_fields(t, types)
            field_names = {f.name for f in ef}

            fluent_steps, void_steps, terminals = [], [], []
            for m in em:
                if m.is_constructor:
                    continue
                # Fluent step: "return this;" chaining. The returned type is the builder's own
                # concrete type OR an ABSTRACTION the builder conforms to -- an interface/superclass
                # Builder that the concrete implementor returns `this` as (idiomatic fluent
                # *interface* builders). Keying only on the own concrete type would miss those.
                if m.return_type == t.name or (
                    m.return_type not in (None, "void")
                    and self._conforms_to(t, m.return_type, types)
                ):
                    fluent_steps.append(m)
                    continue
                # Void build-part: a void concrete method that populates the product's state
                # (assigns a field, or mutates a held field through a call on it).
                if m.return_type == "void" and m.has_body:
                    if any(self._assigns_field(m.body, fn) or self._delegates_to_field(m.body, fn) for fn in field_names):
                        void_steps.append(m)
                    continue
                # Terminal: a concrete method returning a type distinct from the builder (and not
                # void / not a constructor) -- this is the build() output, the product. It must
                # actually CONSUME the builder's configured state -- its body references a builder
                # (effective) field OR passes `this` to the product constructor. Without this, a
                # method that returns some distinct type while IGNORING every configured field
                # (a hollow builder: `build() { return new Gadget(); }` with defaults) would be
                # mistaken for a genuine terminal.
                if (
                    m.has_body
                    and m.return_type not in (None, "void", t.name)
                    and (self._mentions_token(m.body, "this")
                         or any(self._mentions_token(m.body, fn) for fn in field_names))
                ):
                    terminals.append(m)

            if fluent_steps or void_steps or terminals:
                step_names = {m.name for m in fluent_steps + void_steps}
                builder_infos.append((t, fluent_steps, void_steps, terminals, step_names))

        # A builder is a candidate that has configuration steps AND a terminal producing a
        # distinct product. (isBuilder ∧ isTerminalMethod)
        real_builders = [
            info for info in builder_infos
            if (info[1] or info[2]) and info[3]
        ]

        # B1 -- build() returns a product distinct from the builder (the enabling behaviour).
        b1 = bool(real_builders)

        # B2 -- step/configuration methods assemble the product: fluent-return-this, XOR
        # void-build-part paired with a terminal getResult(). (The two idiomatic assembly forms.)
        b2 = any(
            bool(info[1]) or (bool(info[2]) and bool(info[3]))
            for info in builder_infos
        )

        # Product = the return type of a real builder's terminal method.
        product_names = {m.return_type for info in real_builders for m in info[3]}
        builder_names = {info[0].name for info in real_builders}

        # B3 -- builder type and product type are distinct (true by construction of a terminal).
        b3 = any(
            m.return_type != info[0].name
            for info in real_builders for m in info[3]
        )

        # B4 -- telescoping-constructor avoidance / staged construction: a fluent chain, or >= 2
        # discrete configuration step methods (build the product incrementally, not in one ctor).
        b4 = any(
            bool(info[1]) or (len(info[1]) + len(info[2]) >= 2)
            for info in real_builders
        )

        # B5 -- product effectively immutable: the product type exposes no public mutator for a
        # built field. A product that is a JDK/non-project type (e.g. String) is treated as
        # immutable. (Weight 1: mutable products still score, just lower.)
        def _product_immutable(pname: str) -> bool:
            pt = types.get(pname)
            if pt is None:
                return True  # non-project product (e.g. String) -- treat as immutable
            for m in pt.methods:
                if m.is_constructor:
                    continue
                if "public" in m.modifiers and self._has_verb_prefix(m.name, "set"):
                    return False
            return True

        b5 = bool(product_names) and any(_product_immutable(p) for p in product_names)

        # B6 -- Director orchestrates XOR client drives the fluent chain. Fluent steps => the
        # client drives the chain; else look for a Director: a non-builder/non-product type whose
        # method invokes a builder's step method (callsWithin a step name).
        all_step_names = {n for info in real_builders for n in info[4]}
        fluent_exists = any(info[1] for info in real_builders)
        director_exists = False
        for t in types.values():
            if t.name in builder_names or t.name in product_names:
                continue
            for m in t.methods:
                if any(self._calls_within(m, sn) for sn in all_step_names):
                    director_exists = True
                    break
            if director_exists:
                break
        b6 = fluent_exists or director_exists

        base = {
            "isAbstract(x)": any(t.is_abstract for t in types.values()),
            "isConcrete(x)": any(t.kind == "class" and not t.is_abstract for t in types.values()),
            "hasMethod(c,m)": any(t.methods for t in types.values()),
            "returns(m,t)": any(m.return_type for t in types.values() for m in t.methods if not m.is_constructor),
            "modifies(m,f)": any(
                self._assigns_field(m.body, f.name)
                for t in types.values() for m in t.methods for f in t.fields
            ),
            "callsWithin(m,t)": bool(all_step_names) and director_exists,
        }

        derived = {
            "isBuilder(x)": bool(real_builders),
            "isProduct(x)": bool(product_names),
            "isTerminalMethod(m)": any(info[3] for info in real_builders),
            "isStepMethod(m)": any(info[1] or info[2] for info in builder_infos),
            "hasFluentChain(x)": fluent_exists,
            "hasDirector(x)": director_exists,
        }

        rows = [
            self._row("B1", 3, b1, "build() returns a product distinct from the builder."),
            self._row("B2", 3, b2, "Step/configuration methods assemble the product (fluent-return-this XOR void build-part + getResult)."),
            self._row("B3", 2, b3, "Builder type and product type are distinct."),
            self._row("B4", 2, b4, "Telescoping-constructor avoidance / staged construction."),
            self._row("B5", 1, b5, "Product effectively immutable (no public mutators for built fields)."),
            self._row("B6", 1, b6, "Director orchestrates XOR client drives the fluent chain."),
        ]
        return base, derived, rows

    # ================================================================== #
    # Decorator
    # ================================================================== #
    def _evaluate_decorator(self, types: dict[str, JavaType]) -> tuple[dict[str, bool], dict[str, bool], list[dict]]:
        """Decorator: a wrapper that IS-A component and HAS-A component, forwarding the
        component's operations to the wrapped instance while adding behaviour.

        KNOWN LIMITATION (RULE 4 -- encoded, NOT fixed): Decorator and Proxy are STRUCTURALLY
        IDENTICAL under static analysis -- both conform to the component interface, hold a
        component-typed reference, and delegate to it. "Adds behaviour" (Decorator) vs "controls
        access" (Proxy) is a semantic intent that is NOT statically decidable. This checker does
        NOT attempt to distinguish them: any structurally-conforming wrapper is accepted as a
        Decorator. This is disclosed in the paper's threats to validity.

        Derived roles (structural, never name-keyed):
          isComponent(C) -- an abstract type (interface or abstract class).
          isDecorator(W) -- a class that conforms to a component C AND holds a field of type C.
          wraps(W,C)     -- W's held reference is of the component type C it conforms to.
          delegatesTo(W) -- a method of W invokes an operation on the wrapped reference.
        """
        component_names = self._component_type_names(types)
        classes = [t for t in types.values() if t.kind == "class"]

        # A decorator conforms to a component AND holds a field of a component type.
        # decorators: list of (W, conformed_components, wrapped_fields[(field, comp_type)])
        decorators = []
        for w in classes:
            conformed = {c for c in component_names if self._conforms_to(w, c, types)}
            if not conformed:
                continue
            wrapped_fields = [
                (f, f.field_type)
                for f in w.fields
                if f.field_type in component_names
            ]
            if wrapped_fields:
                decorators.append((w, conformed, wrapped_fields))

        # D2 -- decorator holds a component-typed reference (composition). CRITICAL.
        d2 = bool(decorators)

        # D3 -- decorator delegates to the wrapped reference in its component methods. CRITICAL.
        d3 = any(
            any(
                self._delegates_to_field(m.body, f.name)
                for m in w.methods
                for (f, _c) in wrapped_fields
            )
            for (w, _conf, wrapped_fields) in decorators
        )

        # D1 -- decorator conforms to the SAME component type it wraps (is-a matches has-a).
        d1 = any(
            any(ctype in conformed for (_f, ctype) in wrapped_fields)
            for (w, conformed, wrapped_fields) in decorators
        )

        # D4 -- transparent enhancement, no interface conversion (distinguishes from Adapter):
        # the decorator exposes the wrapped component's whole operation set (its method names are
        # a subset of the decorator's effective methods) -- calls pass straight through, no
        # conversion to a different interface. (An Adapter would expose a DIFFERENT interface.)
        def _transparent(w, wrapped_fields):
            wnames = {m.name for m in self._effective_methods(w, types) if not m.is_constructor}
            for (_f, ctype) in wrapped_fields:
                comp = types.get(ctype)
                if comp is None:
                    continue
                comp_ops = {m.name for m in comp.methods if not m.is_constructor}
                if comp_ops and comp_ops <= wnames:
                    return True
            return False

        d4 = any(_transparent(w, wf) for (w, _conf, wf) in decorators)

        # D5 -- abstract decorator base / recursive composability. An abstract decorator base is
        # an ABSTRACT decorator (abstract class that conforms-to and holds the component). Failing
        # that, a collapsed single decorator is still ACCEPTED (RULE 3): because it wraps the
        # component type itself, it can wrap another decorator -> recursive composability holds.
        abstract_decorator_base = any(w.is_abstract for (w, _c, _wf) in decorators)
        d5 = abstract_decorator_base or d2

        # D6 -- full/transparent delegation (NON-CRITICAL diagnostic, weight 1). D3 (critical)
        # only requires that AT LEAST ONE component method delegates -- this is deliberate:
        # a legitimate method-suppressing decorator (a read-only view whose mutators throw)
        # forwards some operations and not others, and must still be accepted. D6 adds VISIBILITY
        # without changing recognition: it is satisfied only when the decorator forwards EVERY
        # component operation it implements to the wrapped reference. A partial-delegation wrapper
        # (delegates some methods, hard-codes others) keeps D2=D3=1 (still recognised) but D6=0,
        # flagging the incomplete forwarding. Recognition stays keyed to the critical {D2,D3} set.
        def _fully_delegates(w, wrapped_fields):
            # Consider only REAL bodied methods of the wrapper (skip the bodyless pseudo-methods the
            # signature regex harvests from call expressions inside other bodies -- e.g. `inner.add(s)`
            # yields a spurious bodyless `add`; without this guard it would overwrite the real `add`
            # and hide its delegation).
            w_ops = {}
            for m in w.methods:
                if m.is_constructor or not m.has_body:
                    continue
                w_ops.setdefault(m.name, m)
            for (f, ctype) in wrapped_fields:
                comp = types.get(ctype)
                if comp is None:
                    continue
                comp_ops = {m.name for m in comp.methods if not m.is_constructor and m.return_type is not None}
                implemented = [op for op in comp_ops if op in w_ops]
                if implemented and all(
                    self._delegates_to_field(w_ops[op].body, f.name) for op in implemented
                ):
                    return True
            return False

        d6 = any(_fully_delegates(w, wf) for (w, _conf, wf) in decorators)

        base = {
            "isAbstract(x)": bool(component_names),
            "isConcrete(x)": any(t.kind == "class" and not t.is_abstract for t in types.values()),
            "hasMethod(c,m)": any(t.methods for t in types.values()),
            "implements(x,y)": any(t.implements for t in classes),
            "extends(x,y)": any(t.extends for t in classes),
            "fieldOfType(c,t)": any(
                self._field_of_type(w, c) for w in classes for c in component_names
            ),
            "callsWithin(m,t)": d3,
        }

        derived = {
            "isComponent(x)": bool(component_names),
            "isDecorator(x)": bool(decorators),
            "wraps(d,c)": d1,
            "delegatesTo(d,c)": d3,
            "isTransparent(d)": d4,
            "hasAbstractDecoratorBase(x)": abstract_decorator_base,
            "fullyDelegates(d)": d6,
        }

        rows = [
            self._row("D1", 2, d1, "Decorator conforms to the same component type as what it wraps."),
            self._row("D2", 3, d2, "Decorator holds a component-typed reference (composition)."),
            self._row("D3", 3, d3, "Decorator delegates to the wrapped reference in its component methods."),
            self._row("D4", 2, d4, "Transparent enhancement -- no interface conversion (distinguishes from Adapter; NOT from Proxy)."),
            self._row("D5", 1, d5, "Abstract decorator base / recursive composability (collapsed single decorator accepted)."),
            self._row("D6", 1, d6, "Full delegation -- every implemented component operation forwards to the wrapped reference (non-critical diagnostic; partial delegation still recognised)."),
        ]
        return base, derived, rows

    # ================================================================== #
    # Template Method
    # ================================================================== #
    def _evaluate_template_method(self, types: dict[str, JavaType]) -> tuple[dict[str, bool], dict[str, bool], list[dict]]:
        """Template Method: an abstract type fixes an algorithm skeleton in a concrete method
        that calls primitive/hook operations deferred to subclasses (inversion of control).

        Derived roles (structural, never name-keyed):
          isAbstractClassType(A) -- an abstract type (abstract class or interface).
          isTemplateMethod(m)    -- a CONCRETE method of A that invokes >=1 deferred operation.
          isPrimitiveOp(m)       -- an abstract method of A (no body) implemented by subclasses.
          isHook(m)              -- a concrete overridable method of A that a subclass overrides
                                    and the template invokes (a default-body extension point).
        """
        abstract_types = [t for t in types.values() if t.is_abstract]
        concrete_classes = [t for t in types.values() if t.kind == "class" and not t.is_abstract]

        t1 = t2 = t3 = t4 = t5 = False
        any_primitive = any_template = any_hook = False

        for a in abstract_types:
            concrete_methods = [m for m in a.methods if m.has_body and not m.is_constructor]
            # A genuine abstract primitive is a bodyless, non-constructor method that declares a
            # return type. The `return_type is not None` guard rejects spurious "methods" the
            # signature regex harvests from CALL EXPRESSIONS inside other method bodies (e.g.
            # `System.out.println(...)` -> a bodyless, return-type-less pseudo-method) -- those
            # must never be counted as deferred primitives (they would fake inversion of control).
            abstract_methods = [
                m for m in a.methods
                if (not m.has_body) and not m.is_constructor and m.return_type is not None
            ]
            primitive_names = {m.name for m in abstract_methods}

            subclasses = [
                s for s in concrete_classes
                if s.extends == a.name or a.name in s.implements or self._conforms_to(s, a.name, types)
            ]

            # Hooks: concrete, overridable methods of A that a subclass actually overrides
            # (proving they are extension points), not internal/final helpers.
            hook_names = set()
            for m in concrete_methods:
                if {"final", "private", "static"} & m.modifiers:
                    continue
                if any(
                    m.name in {sm.name for sm in s.methods if sm.has_body}
                    for s in subclasses
                ):
                    hook_names.add(m.name)

            deferred = primitive_names | hook_names

            # Template methods: concrete methods that invoke >= 1 deferred operation (IoC).
            templates = [
                m for m in concrete_methods
                if any(self._calls_within(m, op) for op in deferred)
            ]
            template_names = {m.name for m in templates}

            if concrete_methods:
                t1 = True  # a concrete skeleton method exists in an abstract type
            if abstract_methods or hook_names:
                t2 = True  # >=1 deferred primitive/hook
            if templates:
                t3 = True  # the skeleton invokes the deferred operations (inversion of control)
                any_template = True
            if any("final" in m.modifiers for m in templates):
                t4 = True  # template is final / non-overridable
            for s in subclasses:
                s_bodies = {sm.name for sm in s.methods if sm.has_body}
                if (s_bodies & deferred) and not (s_bodies & template_names):
                    t5 = True  # subclass overrides the primitives, not the template

            any_primitive = any_primitive or bool(abstract_methods)
            any_hook = any_hook or bool(hook_names)

        base = {
            "isAbstract(x)": bool(abstract_types),
            "isConcrete(x)": bool(concrete_classes),
            "hasMethod(c,m)": any(t.methods for t in types.values()),
            "overrides(m1,m2)": t5,
            "extends(x,y)": any(t.extends for t in types.values() if t.kind == "class"),
            "callsWithin(m,t)": any_template,
        }

        derived = {
            "isAbstractClassType(x)": bool(abstract_types),
            "isTemplateMethod(m)": any_template,
            "isPrimitiveOp(m)": any_primitive,
            "isHook(m)": any_hook,
        }

        rows = [
            self._row("T1", 2, t1, "A concrete template method exists in an abstract type."),
            self._row("T2", 2, t2, ">=1 abstract primitive and/or hook deferred to subclasses."),
            self._row("T3", 3, t3, "The template body invokes the primitive/hook operations (inversion of control)."),
            self._row("T4", 2, t4, "Template method is final / non-overridable (non-final accepted, lower-scoring)."),
            self._row("T5", 2, t5, "Subclass overrides the primitives, not the template method."),
        ]
        return base, derived, rows

    @staticmethod
    def _extract_block(text: str, open_brace_idx: int) -> str:
        if open_brace_idx < 0 or open_brace_idx >= len(text) or text[open_brace_idx] != "{":
            return ""
        depth = 0
        for i in range(open_brace_idx, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[open_brace_idx + 1 : i]
        return text[open_brace_idx + 1 :]

    @staticmethod
    def _parse_params(params: str) -> tuple[list[str], list[str]]:
        if not params.strip():
            return [], []
        param_types: list[str] = []
        param_names: list[str] = []
        for raw in params.split(","):
            part = raw.strip()
            if not part:
                continue
            tokens = part.split()
            if len(tokens) == 1:
                param_types.append(PIQSService._base_name(tokens[0]) or tokens[0])
                param_names.append("")
                continue
            param_types.append(PIQSService._base_name(" ".join(tokens[:-1])) or tokens[0])
            param_names.append(tokens[-1])
        return param_types, param_names

    @staticmethod
    def _base_name(name: str) -> str:
        if not name:
            return ""
        cleaned = re.sub(r"<.*>", "", name).strip()
        cleaned = cleaned.split(".")[-1]
        cleaned = cleaned.replace("[]", "").strip()
        return cleaned

    @staticmethod
    def _row(property_id: str, weight: int, satisfaction: bool, justification: str) -> dict:
        return {
            "property_id": property_id,
            "weight": weight,
            "satisfaction": 1 if satisfaction else 0,
            "justification": justification,
        }

    @staticmethod
    def _grade(score: float) -> str:
        if score > 90:
            return "Excellent"
        if score >= 70:
            return "Good"
        if score >= 50:
            return "Moderate"
        return "Poor"
