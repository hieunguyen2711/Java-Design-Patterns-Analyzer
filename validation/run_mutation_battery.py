"""Mutation / variant battery -- the ORACLE for pass-4 predicate-meaning changes
(G1 three idioms; F4 conditional concrete product). Each case is a small, self-contained
program labelled MUST-PASS (valid implementation) or MUST-FAIL (broken). None are from
Kim's corpus. Every case's verdict must match its label, or the pass is rejected.

Running this materialises each case as a .java file under validation/mutation_battery/ and
then scores it in-memory. Strategy cases are regression guards (S3 is intentionally unchanged).
"""
import os
import sys

sys.path.insert(0, "/Users/hieunguyen/Documents/Coding Projects/DP Recognition Backend")
from app.services.piqs_service import PIQSService

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(HERE, "mutation_battery")
os.makedirs(OUTDIR, exist_ok=True)
svc = PIQSService()

# (case_name, pattern, property, expected_label, java_source)
CASES = [
    # ---------------- Singleton (G1) ----------------
    ("g1_classic_field", "singleton", "G1", "PASS",
     "class Classic {\n"
     "    private static Classic instance;\n"
     "    private Classic() {}\n"
     "    public static Classic getInstance() {\n"
     "        if (instance == null) instance = new Classic();\n"
     "        return instance;\n"
     "    }\n"
     "}\n"),
    ("g1_bill_pugh_holder", "singleton", "G1", "PASS",
     "class Bill {\n"
     "    private Bill() {}\n"
     "    public static Bill getInstance() { return Holder.INSTANCE; }\n"
     "    private static class Holder {\n"
     "        private static final Bill INSTANCE = new Bill();\n"
     "    }\n"
     "}\n"),
    ("g1_enum_singleton", "singleton", "G1", "PASS",
     "enum Single {\n"
     "    INSTANCE;\n"
     "    public void doWork() {}\n"
     "}\n"),
    ("g1_public_ctor", "singleton", "G1", "FAIL",
     "class Pub {\n"
     "    private static Pub instance;\n"
     "    public Pub() {}\n"
     "    public static Pub getInstance() { if (instance == null) instance = new Pub(); return instance; }\n"
     "}\n"),
    ("g1_new_every_call", "singleton", "G1", "FAIL",
     "class NewEach {\n"
     "    private NewEach() {}\n"
     "    public static NewEach getInstance() { return new NewEach(); }\n"
     "}\n"),
    ("g1_enum_constant_group", "singleton", "G1", "FAIL",
     "enum Kind {\n"
     "    A, B;\n"
     "    public static Widget create() { return new Widget(); }\n"
     "}\n"
     "class Widget {}\n"),

    # ---------------- Factory Method (F4) ----------------
    ("f4_concrete_single_product", "factory-method", "F4", "PASS",
     "class Wallet {}\n"
     "class WalletFactory {\n"
     "    public Wallet create() { return new Wallet(); }\n"
     "}\n"),
    ("f4_abstract_hierarchy", "factory-method", "F4", "PASS",
     "interface Product {}\n"
     "class Real implements Product {}\n"
     "class Factory {\n"
     "    public Product make() { return new Real(); }\n"
     "}\n"),
    ("f4_abstract_exists_returns_outside", "factory-method", "F4", "FAIL",
     "interface Shape {}\n"
     "class Circle implements Shape {}\n"
     "class Report {}\n"
     "class ShapeFactory {\n"
     "    public Report make() { Circle c = new Circle(); return new Report(); }\n"
     "}\n"),
    ("f4_returns_unrelated_non_product", "factory-method", "F4", "FAIL",
     "class Thing {}\n"
     "class Fake {\n"
     "    public int compute() { Thing t = new Thing(); return 42; }\n"
     "}\n"),

    # ---------------- Strategy (S3) -- regression guards (S3 UNCHANGED) ----------------
    ("s3_stored_field_delegates", "strategy", "S3", "PASS",
     "interface Strategy { void run(); }\n"
     "class Impl implements Strategy { public void run() {} }\n"
     "class Context {\n"
     "    private Strategy s;\n"
     "    public Context(Strategy s) { this.s = s; }\n"
     "    public void go() { s.run(); }\n"
     "}\n"),
    ("s3_parameter_only", "strategy", "S3", "FAIL",
     "interface Strategy { void run(); }\n"
     "class Impl implements Strategy { public void run() {} }\n"
     "class Context {\n"
     "    public void go(Strategy s) { s.run(); }\n"
     "}\n"),
]


def main():
    rows = []
    all_ok = True
    for name, pattern, prop, label, src in CASES:
        path = os.path.join(OUTDIR, name + ".java")
        with open(path, "w") as fh:
            fh.write(src)
        res = svc.evaluate(pattern, {name + ".java": src})
        verdict = {x["property_id"]: x["satisfaction"] for x in res["logical_assessment"]}[prop]
        expected = 1 if label == "PASS" else 0
        ok = verdict == expected
        all_ok = all_ok and ok
        rows.append((name, prop, label, "satisfied" if verdict else "not satisfied", "OK" if ok else "MISMATCH"))

    w = max(len(r[0]) for r in rows)
    print(f"{'case'.ljust(w)}  prop  expected  actual         result")
    print("-" * (w + 40))
    for name, prop, label, actual, result in rows:
        print(f"{name.ljust(w)}  {prop:4}  {label:8}  {actual:13}  {result}")
    print()
    print("ALL", "MATCH THEIR LABEL" if all_ok else "-- MISMATCH(ES) PRESENT", f"({len(rows)} cases)")
    print(f"Java cases materialised under: {OUTDIR}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
