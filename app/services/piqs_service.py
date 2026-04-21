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

_METHOD_SIG_RE = re.compile(
    r"(?P<mods>(?:(?:public|protected|private|static|final|abstract|synchronized)\s+)*)"
    r"(?:(?P<ret>[A-Za-z_][A-Za-z0-9_<>\[\]\.]*?)\s+)?"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\((?P<params>[^)]*)\)\s*(?P<tail>\{|;)",
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

    def _extract_fields(self, body: str) -> list[JavaField]:
        fields: list[JavaField] = []
        for m in _FIELD_RE.finditer(body):
            field_type = self._base_name(m.group("type") or "")
            if not field_type:
                continue
            mods = {x for x in (m.group("mods") or "").split() if x}
            fields.append(JavaField(name=m.group("name"), field_type=field_type, modifiers=mods))
        return fields

    def _evaluate_factory_method(self, types: dict[str, JavaType]) -> tuple[dict[str, bool], dict[str, bool], list[dict]]:
        abstract_types = [t for t in types.values() if t.is_abstract]
        concrete_types = [t for t in types.values() if not t.is_abstract and t.kind == "class"]

        extends_exists = any(t.extends for t in concrete_types)
        implements_exists = any(t.implements for t in concrete_types)
        has_method_exists = any(t.methods for t in types.values())
        returns_exists = any(m.return_type for t in types.values() for m in t.methods if not m.is_constructor)

        overrides_exists = False
        for t in concrete_types:
            if not t.extends or t.extends not in types:
                continue
            parent_methods = {m.name for m in types[t.extends].methods}
            if parent_methods.intersection({m.name for m in t.methods}):
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

        for c in concrete_types:
            if any(i in product_names for i in c.implements):
                is_product_exists = True

        for c in concrete_types:
            if c.extends and c.extends in types:
                parent_methods = {m.name: m for m in types[c.extends].methods}
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

        f1 = any(t.kind == "class" and t.is_abstract for t in types.values())
        f2 = any(t.kind == "class" and not t.is_abstract and t.extends for t in types.values())
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
            setter = any(m.name.lower().startswith("set") and any(pt in strategy_ifaces for pt in m.param_types) for m in c.methods)
            execute = any(
                any(name in m.body for name in strategy_method_names) and re.search(r"\.[A-Za-z_][A-Za-z0-9_]*\s*\(", m.body)
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

        is_add = any(m.name.lower().startswith("add") for t in concrete_components for m in t.methods)
        is_remove = any(m.name.lower().startswith("remove") for t in concrete_components for m in t.methods)

        accepts_exists = any(any(pt in component_names for pt in m.param_types) for t in concrete_components for m in t.methods)

        composites = [
            t for t in concrete_components if any("add" in m.name.lower() or "remove" in m.name.lower() for m in t.methods)
        ]
        leaves = [t for t in concrete_components if t not in composites]

        has_children = any(re.search(r"\b(List|Set|Collection)<", t.body) for t in composites)
        contains_component = any(
            any(pt in component_names for m in t.methods for pt in m.param_types)
            for t in composites
        )
        is_add_child = any(any(m.name.lower().startswith("add") for m in t.methods) for t in composites)
        is_remove_child = any(any(m.name.lower().startswith("remove") for m in t.methods) for t in composites)

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

        uniform = False
        if composites and leaves and abstract_components:
            api = set(m.name for m in abstract_components[0].methods)
            if api:
                uniform = all(name in {m.name for m in composites[0].methods} for name in api) and all(
                    name in {m.name for m in leaves[0].methods} for name in api
                )

        c1 = bool(component_names)
        c2 = bool(leaves)
        c3 = bool(composites)
        c4 = bool(composites and leaves)
        c5 = uniform

        rows = [
            self._row("C1", 3, c1, "Abstract component exists."),
            self._row("C2", 2, c2, "Leaf type exists."),
            self._row("C3", 3, c3, "Composite type exists."),
            self._row("C4", 3, c4, "Composite and leaf implement component."),
            self._row("C5", 3, c5, "Uniform composite/leaf treatment is possible."),
        ]
        return base, derived, rows

    def _evaluate_observer(self, types: dict[str, JavaType]) -> tuple[dict[str, bool], dict[str, bool], list[dict]]:
        observer_types = [t for t in types.values() if t.kind == "interface" and any(m.name == "update" for m in t.methods)]
        observer_names = {t.name for t in observer_types}

        subject_candidates = [
            t
            for t in types.values()
            if t.kind == "class"
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
        traverses_collection = any(
            re.search(r"for\s*\(.*:.*\)", m.body)
            for t in subject_candidates
            for m in t.methods
        )
        increases = any(re.search(r"\.add\s*\(", m.body) for t in subject_candidates for m in t.methods)
        decreases = any(re.search(r"\.remove\s*\(", m.body) for t in subject_candidates for m in t.methods)

        calls_exists = any(re.search(r"\.[A-Za-z_][A-Za-z0-9_]*\s*\(", m.body) for t in types.values() for m in t.methods)

        is_register = any(m.name in {"attach", "register"} for t in subject_candidates for m in t.methods)
        is_unregister = any(m.name in {"detach", "remove"} for t in subject_candidates for m in t.methods)
        is_notify = any(m.name in {"notifyObservers", "notify"} for t in subject_candidates for m in t.methods)

        notify_calls_update = any(
            m.name in {"notifyObservers", "notify"} and re.search(r"\.update\s*\(", m.body)
            for t in subject_candidates
            for m in t.methods
        )

        concrete_observers = [
            t
            for t in types.values()
            if t.kind == "class" and any(obs in t.implements for obs in observer_names)
        ]

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
            "isObserver(x)": bool(observer_types),
            "isUpdate(m)": any(m.name == "update" for t in types.values() for m in t.methods),
            "isSubject(x)": bool(subject_candidates),
            "isRegisterObserver(m)": is_register,
            "isUnregisterObserver(m)": is_unregister,
            "isNotify(m)": is_notify,
            "notifies(s,o)": notify_calls_update,
            "updates(o,s)": bool(concrete_observers) and all(any(m.name == "update" for m in t.methods) for t in concrete_observers),
        }

        o1 = any(t.is_abstract and t.kind in {"class", "interface"} for t in subject_candidates)
        o2 = bool(observer_types)
        o3 = notify_calls_update and traverses_collection
        o4 = derived["updates(o,s)"]

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
                    if any(f.name in m.body for f in static_fields):
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
