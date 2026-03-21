"""PIQS evaluation service for selected GoF patterns from Java source files."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List


_PATTERN_WEIGHTS = {
    "factory-method": {
        "F1": 2,
        "F2": 3,
        "F3": 3,
        "F4": 3,
        "F5": 2,
    },
    "strategy": {
        "S1": 3,
        "S2": 3,
        "S3": 2,
        "S4": 3,
    },
    "composite": {
        "C1": 3,
        "C2": 2,
        "C3": 3,
        "C4": 3,
        "C5": 3,
    },
    "observer": {
        "O1": 2,
        "O2": 3,
        "O3": 3,
        "O4": 3,
    },
    "singleton": {
        "G1": 3,
    },
}

_DECL_RE = re.compile(
    r"\b(public\s+)?(?P<abs>abstract\s+)?(?P<kind>class|interface)\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?:\s+extends\s+(?P<extends>[A-Za-z_][A-Za-z0-9_]*))?"
    r"(?:\s+implements\s+(?P<implements>[^\{]+))?\s*\{",
    re.MULTILINE,
)

_METHOD_RE = re.compile(
    r"\b(?:public|protected|private)?\s*(?:static\s+)?(?:final\s+)?(?:abstract\s+)?"
    r"(?P<ret>[A-Za-z_][A-Za-z0-9_<>\[\]]*)\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\((?P<params>[^)]*)\)",
)


@dataclass
class JavaType:
    name: str
    kind: str
    is_abstract: bool
    extends: str | None
    implements: List[str] = field(default_factory=list)
    methods: Dict[str, str] = field(default_factory=dict)  # method_name -> return type
    content: str = ""


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
            assessments = self._evaluate_factory_method(types)
        elif normalized == "strategy":
            assessments = self._evaluate_strategy(types)
        elif normalized == "composite":
            assessments = self._evaluate_composite(types)
        elif normalized == "observer":
            assessments = self._evaluate_observer(types)
        else:
            assessments = self._evaluate_singleton(types)

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
                extends_name = match.group("extends")
                impl_raw = match.group("implements") or ""
                impl = [part.strip().split()[-1] for part in impl_raw.split(",") if part.strip()]
                is_abs = bool(match.group("abs")) or kind == "interface"

                t = JavaType(
                    name=name,
                    kind=kind,
                    is_abstract=is_abs,
                    extends=extends_name,
                    implements=impl,
                    content=content,
                )

                for m in _METHOD_RE.finditer(content):
                    method_name = m.group("name")
                    ret = m.group("ret")
                    if method_name != name:
                        t.methods[method_name] = ret

                types[name] = t

        return types

    def _evaluate_factory_method(self, types: dict[str, JavaType]) -> list[dict]:
        rows: list[dict] = []
        weights = _PATTERN_WEIGHTS["factory-method"]

        abstract_creators = [
            t for t in types.values() if t.kind == "class" and t.is_abstract
        ]
        creator_subclasses = [
            t for t in types.values() if t.kind == "class" and t.extends in {a.name for a in abstract_creators}
        ]

        has_override = False
        has_correct_create = False
        abstract_products = [t for t in types.values() if t.kind == "interface" or (t.kind == "class" and t.is_abstract)]
        abstract_product_names = {p.name for p in abstract_products}

        for sub in creator_subclasses:
            parent = types.get(sub.extends or "")
            if not parent:
                continue
            shared = set(parent.methods).intersection(sub.methods)
            if shared:
                has_override = True
            for method_name, return_type in sub.methods.items():
                if return_type in abstract_product_names and re.search(r"\bnew\s+[A-Za-z_][A-Za-z0-9_]*\s*\(", sub.content):
                    has_correct_create = True

        concrete_products = [
            t for t in types.values() if t.kind == "class" and not t.is_abstract and t.implements
        ]
        concrete_product_ok = any(any(i in abstract_product_names for i in p.implements) for p in concrete_products)

        rows.append(self._row("F1", weights["F1"], bool(abstract_creators), "Abstract creator class exists."))
        rows.append(
            self._row(
                "F2",
                weights["F2"],
                bool(creator_subclasses),
                "Abstract creator has at least one concrete subclass.",
            )
        )
        rows.append(
            self._row(
                "F3",
                weights["F3"],
                has_override,
                "Concrete creator overrides abstract factory method.",
            )
        )
        rows.append(
            self._row(
                "F4",
                weights["F4"],
                has_correct_create,
                "Factory method returns abstract product type and creates concrete product.",
            )
        )
        rows.append(
            self._row(
                "F5",
                weights["F5"],
                concrete_product_ok,
                "Concrete products implement abstract product interfaces.",
            )
        )

        return rows

    def _evaluate_strategy(self, types: dict[str, JavaType]) -> list[dict]:
        rows: list[dict] = []
        weights = _PATTERN_WEIGHTS["strategy"]

        interfaces = [t for t in types.values() if t.kind == "interface"]
        implemented_by = {
            iface.name: [
                c for c in types.values() if c.kind == "class" and iface.name in c.implements
            ]
            for iface in interfaces
        }

        strategy_ifaces = [name for name, impls in implemented_by.items() if impls]
        has_context = False
        concrete_algorithms = False

        if strategy_ifaces:
            iface_set = set(strategy_ifaces)
            for cls in (t for t in types.values() if t.kind == "class"):
                if any(re.search(rf"\b{iface}\b\s+[A-Za-z_][A-Za-z0-9_]*\s*;", cls.content) for iface in iface_set):
                    has_context = True
                if re.search(r"\bset[A-Z][A-Za-z0-9_]*\s*\(", cls.content) and any(
                    re.search(rf"\({iface}\s+[A-Za-z_][A-Za-z0-9_]*\)", cls.content) for iface in iface_set
                ):
                    has_context = True

            concrete_algorithms = all(
                any(set(types[iface].methods).intersection(impl.methods) for impl in implemented_by[iface])
                for iface in strategy_ifaces
            )

        all_have_impl = bool(strategy_ifaces) and all(implemented_by[iface] for iface in strategy_ifaces)

        rows.append(self._row("S1", weights["S1"], bool(strategy_ifaces), "Abstract strategy interface exists."))
        rows.append(
            self._row(
                "S2",
                weights["S2"],
                all_have_impl,
                "Every strategy interface has at least one concrete implementation.",
            )
        )
        rows.append(self._row("S3", weights["S3"], has_context, "Context class exists to manage strategies."))
        rows.append(
            self._row(
                "S4",
                weights["S4"],
                concrete_algorithms,
                "Concrete strategies implement algorithm methods from strategy interface.",
            )
        )

        return rows

    def _evaluate_composite(self, types: dict[str, JavaType]) -> list[dict]:
        rows: list[dict] = []
        weights = _PATTERN_WEIGHTS["composite"]

        components = [
            t for t in types.values() if t.kind == "interface" or (t.kind == "class" and t.is_abstract)
        ]
        component_names = {c.name for c in components}

        implementors = [
            t
            for t in types.values()
            if t.kind == "class" and (t.extends in component_names or any(i in component_names for i in t.implements))
        ]

        composite_candidates = [
            c
            for c in implementors
            if re.search(r"\bList<", c.content)
            or re.search(r"\badd\s*\(", c.content)
            or re.search(r"\bremove\s*\(", c.content)
        ]
        leaf_candidates = [c for c in implementors if c not in composite_candidates]

        has_uniform = False
        if components and composite_candidates and leaf_candidates:
            comp_methods = set()
            for comp in components:
                comp_methods.update(comp.methods.keys())
            for m in comp_methods:
                if all(m in c.methods for c in [composite_candidates[0], leaf_candidates[0]]):
                    has_uniform = True
                    break

        rows.append(self._row("C1", weights["C1"], bool(components), "Abstract component type exists."))
        rows.append(self._row("C2", weights["C2"], bool(leaf_candidates), "Leaf type exists."))
        rows.append(
            self._row(
                "C3",
                weights["C3"],
                bool(composite_candidates),
                "Composite type exists for hierarchy management.",
            )
        )
        rows.append(
            self._row(
                "C4",
                weights["C4"],
                bool(composite_candidates and leaf_candidates),
                "Composite and leaf implement/extend component.",
            )
        )
        rows.append(
            self._row(
                "C5",
                weights["C5"],
                has_uniform,
                "Uniform treatment of composite and leaf objects is possible.",
            )
        )

        return rows

    def _evaluate_observer(self, types: dict[str, JavaType]) -> list[dict]:
        rows: list[dict] = []
        weights = _PATTERN_WEIGHTS["observer"]

        observer_interfaces = [
            t for t in types.values() if t.kind == "interface" and "update" in t.methods
        ]
        observer_names = {o.name for o in observer_interfaces}

        abstract_subjects = [
            t
            for t in types.values()
            if t.is_abstract and (
                {"attach", "detach", "notifyObservers"}.intersection(t.methods)
                or {"register", "remove", "notify"}.intersection(t.methods)
            )
        ]

        concrete_subjects = [
            t
            for t in types.values()
            if t.kind == "class"
            and not t.is_abstract
            and any(
                re.search(rf"\bList<{obs}>", t.content) or re.search(rf"\b{obs}\b", t.content)
                for obs in observer_names
            )
        ]

        notifies = any(
            ("notifyObservers" in s.methods or "notify" in s.methods)
            and re.search(r"for\s*\(.*\)\s*\{[^}]*\.update\s*\(", s.content, re.DOTALL)
            for s in concrete_subjects
        )

        concrete_observers = [
            t
            for t in types.values()
            if t.kind == "class" and any(o in t.implements for o in observer_names)
        ]
        updates = bool(concrete_observers) and all("update" in o.methods for o in concrete_observers)

        rows.append(self._row("O1", weights["O1"], bool(abstract_subjects), "At least one abstract subject exists."))
        rows.append(self._row("O2", weights["O2"], bool(observer_interfaces), "At least one abstract observer exists."))
        rows.append(
            self._row(
                "O3",
                weights["O3"],
                notifies,
                "Subjects notify all registered observers on state change.",
            )
        )
        rows.append(
            self._row(
                "O4",
                weights["O4"],
                updates,
                "Observers update in response to subject notifications.",
            )
        )

        return rows

    def _evaluate_singleton(self, types: dict[str, JavaType]) -> list[dict]:
        rows: list[dict] = []
        w = _PATTERN_WEIGHTS["singleton"]["G1"]

        has_singleton = False
        for t in (x for x in types.values() if x.kind == "class"):
            private_ctor = re.search(rf"\bprivate\s+{t.name}\s*\(", t.content) is not None
            static_instance = re.search(rf"\bstatic\s+{t.name}\s+[A-Za-z_][A-Za-z0-9_]*\b", t.content) is not None
            accessor = re.search(rf"\bstatic\s+{t.name}\s+getInstance\s*\(", t.content) is not None
            if private_ctor and static_instance and accessor:
                has_singleton = True
                break

        rows.append(
            self._row(
                "G1",
                w,
                has_singleton,
                "Singleton class has private constructor and controlled static access.",
            )
        )
        return rows

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
