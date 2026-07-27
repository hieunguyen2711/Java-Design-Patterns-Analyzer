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
}

_DECL_RE = re.compile(
    r"\b(public\s+)?(?P<abs>abstract\s+)?(?P<kind>class|interface)\s+"
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
                "composite, observer, singleton."
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
        else:
            base, derived, assessments = self._evaluate_singleton(types)

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
            if m.group("tail") == "{":
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
        f4 = creates_exists
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

        for c in classes:
            ctors = [m for m in c.methods if m.is_constructor]
            has_constructor = has_constructor or bool(ctors)
            if ctors and all("private" in m.modifiers for m in ctors):
                has_private_ctor = True
                is_private = True

            static_fields = [f for f in c.fields if "static" in f.modifiers and f.field_type == c.name]
            if static_fields:
                has_static_instance = True
                is_static = True
                field_type = True
                belongs_to = True

            get_instance = [
                m for m in c.methods if m.name == "getInstance" and "static" in m.modifiers and m.return_type == c.name
            ]
            if get_instance:
                has_instance_method = True
                returns = True
                for m in get_instance:
                    # Fix G: whole-token field reference, not substring containment.
                    if any(self._mentions_token(m.body, f.name) for f in static_fields):
                        accesses_field = True
                    if re.search(rf"\bnew\s+{c.name}\s*\(", m.body):
                        calls = True

            if has_private_ctor and has_static_instance and has_instance_method:
                has_singleton = True

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
                has_private_ctor and has_static_instance and has_instance_method,
                "Singleton has private constructor with static instance and accessor method.",
            )
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
