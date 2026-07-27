"""Synthetic generality tests for the scorer fixes (passes 2 & 3). None of these programs
come from Kim's corpus; they exercise the STRUCTURAL rules, never class/method names."""
import sys, os
sys.path.insert(0, "/Users/hieunguyen/Documents/Coding Projects/DP Recognition Backend")
from app.services.piqs_service import PIQSService

svc = PIQSService()


def props(pattern, files):
    r = svc.evaluate(pattern, files)
    return {x["property_id"]: x["satisfaction"] for x in r["logical_assessment"]}


results = []

# ---------------- Pass 2 (A, B, D, E) ----------------
obs_named = {
    "Watcher.java": "interface Watcher { void ping(String msg); }",
    "LogWatcher.java": "class LogWatcher implements Watcher { public void ping(String msg){ System.out.println(msg); } }",
    "Bus.java": ("import java.util.*; class Bus { private List<Watcher> ws = new ArrayList<>();"
                 " public void sub(Watcher w){ ws.add(w); }"
                 " public void fire(String m){ for (Watcher w : ws){ w.ping(m); } } }"),
}
p = props("observer", obs_named)
results.append(("A: observer callback 'ping' in notify loop -> O2/O3/O4 pass", p, p["O2"] == 1 and p["O3"] == 1 and p["O4"] == 1))

obs_jdk = {
    "Sensor.java": "import java.util.Observable; class Sensor extends Observable { void tick(){ setChanged(); notifyObservers(); } }",
    "Display.java": "import java.util.Observer; import java.util.Observable; class Display implements Observer { public void update(Observable o, Object arg){} }",
}
p = props("observer", obs_jdk)
results.append(("B: extends Observable + implements Observer -> O1/O2 pass", p, p["O1"] == 1 and p["O2"] == 1))

no_comp = {
    "Sorter.java": "interface Sorter { void sort(int[] a); }",
    "QuickSort.java": "class QuickSort implements Sorter { public void sort(int[] a){} }",
    "BubbleSort.java": "class BubbleSort implements Sorter { public void sort(int[] a){} }",
}
p = props("composite", no_comp)
results.append(("D: Strategy-only, no part-whole -> C1/C4/C5 = 0", p, p["C1"] == 0 and p["C4"] == 0 and p["C5"] == 0))

real_comp = {
    "Node.java": "interface Node { int size(); }",
    "File.java": "class File implements Node { public int size(){ return 1; } }",
    "Dir.java": ("import java.util.*; class Dir implements Node { private List<Node> kids = new ArrayList<>();"
                 " public void add(Node n){ kids.add(n);} public int size(){ int s=0; for(Node k: kids){ s+=k.size(); } return s; } }"),
}
p = props("composite", real_comp)
results.append(("D: genuine part-whole -> C1/C4/C5 = 1", p, p["C1"] == 1 and p["C4"] == 1 and p["C5"] == 1))

throws_factory = {
    "Doc.java": "interface Doc { }",
    "PdfDoc.java": "class PdfDoc implements Doc { }",
    "DocFactory.java": "interface DocFactory { Doc create() throws Exception; }",
    "PdfFactory.java": "class PdfFactory implements DocFactory { public Doc create() throws Exception { return new PdfDoc(); } }",
}
p = props("factory-method", throws_factory)
results.append(("E: factory method with `throws` -> F1 & F4 pass", p, p["F1"] == 1 and p["F4"] == 1))

# ---------------- Pass 3 (F, G) ----------------
# F: a method-local variable must NOT be extracted as a class field.
local_only = {"C.java": "class C { void run(){ Foo f = new Foo(); f.bar(); } } class Foo { void bar(){} }"}
types = svc._extract_types(local_only)
c_foo_fields = [f for f in types["C"].fields if f.field_type == "Foo"]
results.append(("F: local var not a field -> C has 0 Foo fields", {"C.fields(Foo)": len(c_foo_fields)}, len(c_foo_fields) == 0))

# F: a genuine class-scope field is still captured.
real_field = {"C.java": "class C { private Foo f; void run(){ f.bar(); } } class Foo { void bar(){} }"}
types = svc._extract_types(real_field)
c_foo_fields = [f for f in types["C"].fields if f.field_type == "Foo"]
results.append(("F: genuine class-scope field kept -> C has 1 Foo field", {"C.fields(Foo)": len(c_foo_fields)}, len(c_foo_fields) == 1))

# G: identifier must match as a whole token, not a substring.
body_sub = "PaymentStrategy payment = PaymentFactory.get();"
g_sub = (svc._calls_method(body_sub, "pay") is False) and (svc._mentions_token(body_sub, "pay") is False)
results.append(("G: 'pay' does NOT match inside 'payment'/'PaymentFactory'",
                {"calls_pay": svc._calls_method(body_sub, "pay"), "mentions_pay": svc._mentions_token(body_sub, "pay")}, g_sub))

# G: an exact token / call DOES match; verb-prefix distinguishes addChild from address.
body_tok = "obj.pay(amount);"
g_tok = (svc._calls_method(body_tok, "pay")
         and svc._has_verb_prefix("addChild", "add")
         and not svc._has_verb_prefix("address", "add"))
results.append(("G: 'pay(' matches; add-prefix addChild yes / address no",
                {"calls_pay": svc._calls_method(body_tok, "pay"),
                 "addChild": svc._has_verb_prefix("addChild", "add"),
                 "address": svc._has_verb_prefix("address", "add")}, g_tok))

# Guard: Fix A must NOT be re-broken by Fix G -- differently-named callback still structural.
p = props("observer", obs_named)
results.append(("A-not-rebroken: 'ping' callback still detected after Fix G -> O2/O3/O4 pass",
                p, p["O2"] == 1 and p["O3"] == 1 and p["O4"] == 1))

ok = True
for label, detail, passed in results:
    ok = ok and passed
    print(("PASS" if passed else "FAIL"), "|", label)
    print("      ->", detail)
print("\nALL", "PASS" if ok else "FAIL", "(%d tests)" % len(results))
sys.exit(0 if ok else 1)
