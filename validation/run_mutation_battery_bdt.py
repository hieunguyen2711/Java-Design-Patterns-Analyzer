"""JDK-exemplar + mutation battery -- the ORACLE for the three NEW patterns
(Builder, Decorator, Template Method). Kim (2025) never covered these three, so there is no
Kim ground truth; this hand-built battery is the ground truth instead.

Each case is a small, self-contained Java program labelled MUST-PASS (a valid, idiomatic
implementation -- often a JDK-exemplar analogue) or MUST-FAIL (a degenerate form that omits the
enabling behaviour). A case's *verdict* is decided the same way the scorer recognises a pattern:
a program IS the pattern iff ALL of its CRITICAL (weight-3) properties are satisfied
(app.services.piqs_service._CRITICAL_PROPERTIES). Builder {B1,B2}; Decorator {D2,D3};
Template Method {T3}.

Running this materialises each case under validation/mutation_battery_bdt/, scores it in-memory
with the UNMODIFIED-elsewhere PIQSService, checks the verdict against the label, and (if javac is
on PATH) records whether the case compiles.

Structure:
  * CONFIRMED_CASES -- every case must match its label; these gate the exit code. Includes the
    original 13, the pass-5 coverage additions, and the three pass-5 probes that were RESOLVED
    after review (two Builder discrimination gaps FIXED, the Decorator D3 semantics DECIDED).
  * D6_DIAGNOSTICS -- demonstrates the non-critical Decorator D6 property added for Finding 2
    (keep critical D3 = 'any'; D6 flags partial delegation for visibility, recognition unchanged).

History (pass-5): the three probes began as OPEN FINDINGS (a probe whose actual verdict != intended
was reported for a human decision, with NO predicate changed to force it green). After approval:
  - Builder B2 hollow-steps gap  -> FIXED (terminal must consume builder state).
  - Builder fluent-interface gap -> FIXED (fluent step may return a conforming abstraction).
  - Decorator partial delegation -> DECIDED: keep D3 'any' (accept), add non-critical D6 flag.
"""
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, "/Users/hieunguyen/Documents/Coding Projects/DP Recognition Backend")
from app.services.piqs_service import PIQSService, _CRITICAL_PROPERTIES  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(HERE, "mutation_battery_bdt")
os.makedirs(OUTDIR, exist_ok=True)
svc = PIQSService()

# (case_name, pattern, expected_label, java_source)
CONFIRMED_CASES = [
    # ================================================================== #
    # Original 13 (pass-1): obvious pass/fail forms.
    # ================================================================== #
    # ============================= Builder =============================
    ("builder_bloch_fluent_static_nested", "builder", "PASS",
     "// Bloch fluent static-nested builder: immutable product, private product ctor.\n"
     "// (package-private so the single-file case compiles under any file name)\n"
     "class Pizza {\n"
     "    private final String size;\n"
     "    private final boolean cheese;\n"
     "    private Pizza(Builder b) { this.size = b.size; this.cheese = b.cheese; }\n"
     "    public String getSize() { return size; }\n"
     "    public boolean hasCheese() { return cheese; }\n"
     "    public static class Builder {\n"
     "        private String size;\n"
     "        private boolean cheese;\n"
     "        public Builder size(String size) { this.size = size; return this; }\n"
     "        public Builder cheese(boolean cheese) { this.cheese = cheese; return this; }\n"
     "        public Pizza build() { return new Pizza(this); }\n"
     "    }\n"
     "}\n"),

    ("builder_classic_gof_director", "builder", "PASS",
     "// Classic GoF Builder: Director + abstract Builder + ConcreteBuilder + Product,\n"
     "// void buildPart steps + getResult() terminal.\n"
     "class Product {\n"
     "    private String partA;\n"
     "    private String partB;\n"
     "    public void setPartA(String a) { this.partA = a; }\n"
     "    public void setPartB(String b) { this.partB = b; }\n"
     "    public String describe() { return partA + partB; }\n"
     "}\n"
     "abstract class Builder {\n"
     "    protected Product product = new Product();\n"
     "    public abstract void buildPartA();\n"
     "    public abstract void buildPartB();\n"
     "    public Product getResult() { return product; }\n"
     "}\n"
     "class ConcreteBuilder extends Builder {\n"
     "    public void buildPartA() { product.setPartA(\"A\"); }\n"
     "    public void buildPartB() { product.setPartB(\"B\"); }\n"
     "}\n"
     "class Director {\n"
     "    private Builder builder;\n"
     "    public Director(Builder builder) { this.builder = builder; }\n"
     "    public void construct() { builder.buildPartA(); builder.buildPartB(); }\n"
     "}\n"),

    ("builder_stringbuilder_like_chained", "builder", "PASS",
     "// JDK-style StringBuilder analogue: chained fluent appends + toString() terminal.\n"
     "// Modelled, NOT imported from the JDK.\n"
     "class TextBuilder {\n"
     "    private String value = \"\";\n"
     "    public TextBuilder append(String s) { value = value + s; return this; }\n"
     "    public TextBuilder appendLine(String s) { value = value + s + \"\\n\"; return this; }\n"
     "    public String toString() { return value; }\n"
     "}\n"),

    ("builder_pojo_setters_only__FAIL", "builder", "FAIL",
     "// Degenerate: a POJO with only setters and NO terminal / build method -> B1 fails.\n"
     "class UserPojo {\n"
     "    private String name;\n"
     "    private int age;\n"
     "    public void setName(String name) { this.name = name; }\n"
     "    public void setAge(int age) { this.age = age; }\n"
     "}\n"),

    ("builder_build_returns_this__FAIL", "builder", "FAIL",
     "// Degenerate: build() returns the builder (this), not a distinct product -> B1 fails.\n"
     "class FluentThing {\n"
     "    private String name;\n"
     "    public FluentThing setName(String name) { this.name = name; return this; }\n"
     "    public FluentThing build() { return this; }\n"
     "}\n"),

    # ============================ Decorator ============================
    ("decorator_filterinputstream_analogue", "decorator", "PASS",
     "// java.io FilterInputStream analogue: abstract component, concrete component,\n"
     "// abstract decorator holding the component, concrete decorator delegating.\n"
     "abstract class InputStream {\n"
     "    public abstract int read();\n"
     "}\n"
     "class FileInputStream extends InputStream {\n"
     "    private int pos = 0;\n"
     "    public int read() { return pos < 5 ? pos++ : -1; }\n"
     "}\n"
     "abstract class FilterInputStream extends InputStream {\n"
     "    protected InputStream in;\n"
     "    public FilterInputStream(InputStream in) { this.in = in; }\n"
     "    public int read() { return in.read(); }\n"
     "}\n"
     "class BufferedInputStream extends FilterInputStream {\n"
     "    public BufferedInputStream(InputStream in) { super(in); }\n"
     "    public int read() { int b = super.read(); return b; }\n"
     "}\n"),

    ("decorator_collapsed_single_synchronized", "decorator", "PASS",
     "// Collapsed single decorator implementing the interface + delegating, no abstract base\n"
     "// (Collections.synchronizedList style).\n"
     "interface MyList {\n"
     "    void add(String s);\n"
     "    int size();\n"
     "}\n"
     "class ArrayMyList implements MyList {\n"
     "    private String[] data = new String[16];\n"
     "    private int n = 0;\n"
     "    public void add(String s) { data[n++] = s; }\n"
     "    public int size() { return n; }\n"
     "}\n"
     "class SynchronizedMyList implements MyList {\n"
     "    private final MyList inner;\n"
     "    public SynchronizedMyList(MyList inner) { this.inner = inner; }\n"
     "    public void add(String s) { synchronized (this) { inner.add(s); } }\n"
     "    public int size() { synchronized (this) { return inner.size(); } }\n"
     "}\n"),

    ("decorator_plain_inheritance_no_ref__FAIL", "decorator", "FAIL",
     "// Degenerate: a subclass that extends the concrete component and adds a method, with NO\n"
     "// wrapped reference (plain inheritance, not composition) -> D2 fails.\n"
     "interface Coffee { double cost(); }\n"
     "class SimpleCoffee implements Coffee { public double cost() { return 2.0; } }\n"
     "class MilkCoffee extends SimpleCoffee {\n"
     "    public double cost() { return 2.5; }\n"
     "    public String extra() { return \"milk\"; }\n"
     "}\n"),

    ("decorator_no_delegation__FAIL", "decorator", "FAIL",
     "// Degenerate: a wrapper implementing the component interface but whose methods ignore the\n"
     "// wrapped object (no delegation) -> D3 fails.\n"
     "interface Logger { void log(String m); }\n"
     "class ConsoleLogger implements Logger { public void log(String m) { System.out.println(m); } }\n"
     "class FakeDecorator implements Logger {\n"
     "    private final Logger wrapped;\n"
     "    public FakeDecorator(Logger wrapped) { this.wrapped = wrapped; }\n"
     "    public void log(String m) { System.out.println(\"ignored\"); }\n"
     "}\n"),

    # ========================= Template Method =========================
    ("template_abstractlist_analogue", "template-method", "PASS",
     "// java.util.AbstractList analogue: concrete (final) template calling abstract\n"
     "// get/size primitives.\n"
     "abstract class AbstractList {\n"
     "    public abstract Object get(int index);\n"
     "    public abstract int size();\n"
     "    public final boolean contains(Object o) {\n"
     "        for (int i = 0; i < size(); i++) {\n"
     "            if (get(i).equals(o)) { return true; }\n"
     "        }\n"
     "        return false;\n"
     "    }\n"
     "}\n"
     "class MyList extends AbstractList {\n"
     "    private Object[] data = new Object[] { \"a\", \"b\" };\n"
     "    public Object get(int index) { return data[index]; }\n"
     "    public int size() { return data.length; }\n"
     "}\n"),

    ("template_httpservlet_analogue", "template-method", "PASS",
     "// javax.servlet HttpServlet analogue: non-final concrete template service() dispatching\n"
     "// to hook methods (doGet/doPost) with default bodies.\n"
     "class Request { String method; }\n"
     "class Response { void send(String s) {} }\n"
     "abstract class HttpServlet {\n"
     "    protected void doGet(Request req, Response res) { res.send(\"405\"); }\n"
     "    protected void doPost(Request req, Response res) { res.send(\"405\"); }\n"
     "    public void service(Request req, Response res) {\n"
     "        if (req.method.equals(\"GET\")) { doGet(req, res); }\n"
     "        else if (req.method.equals(\"POST\")) { doPost(req, res); }\n"
     "    }\n"
     "}\n"
     "class MyServlet extends HttpServlet {\n"
     "    protected void doGet(Request req, Response res) { res.send(\"hello\"); }\n"
     "}\n"),

    ("template_abstract_template_method__FAIL", "template-method", "FAIL",
     "// Degenerate: the 'template' method is itself abstract -- there is no fixed skeleton\n"
     "// (no concrete algorithm) -> T1/T3 fail.\n"
     "abstract class ReportGenerator {\n"
     "    public abstract void generate();\n"
     "    public abstract void writeHeader();\n"
     "    public abstract void writeBody();\n"
     "}\n"
     "class PdfReport extends ReportGenerator {\n"
     "    public void generate() { writeHeader(); writeBody(); }\n"
     "    public void writeHeader() {}\n"
     "    public void writeBody() {}\n"
     "}\n"),

    ("template_no_inversion_of_control__FAIL", "template-method", "FAIL",
     "// Degenerate: an abstract class with a concrete method and abstract methods that the\n"
     "// concrete method NEVER calls (no inversion of control) -> T3 fails.\n"
     "abstract class Task {\n"
     "    public abstract void step1();\n"
     "    public abstract void step2();\n"
     "    public void run() { System.out.println(\"running\"); }\n"
     "}\n"
     "class RealTask extends Task {\n"
     "    public void step1() {}\n"
     "    public void step2() {}\n"
     "}\n"),

    # ================================================================== #
    # pass-5 additions -- cases the checker handles correctly as-is.
    # ================================================================== #

    # ---- TASK 1: behaviorally-hollow / genuine-enhance (the discriminating middle) ----

    # TASK 1 (Builder): fluent this-returning setters with NO terminal method at all --
    # fluent setters masquerading as a builder. B1 fails (no distinct product returned).
    ("t1_builder_fluent_setters_no_terminal__FAIL", "builder", "FAIL",
     "class Config {\n"
     "    private String host;\n"
     "    private int port;\n"
     "    public Config host(String host) { this.host = host; return this; }\n"
     "    public Config port(int port) { this.port = port; return this; }\n"
     "}\n"),

    # TASK 1 (Decorator): a decorator that delegates AND adds real work before/after the
    # delegate call (the genuine 'enhance' case). Confirms added behaviour does not break D3.
    ("t1_decorator_enhance_before_after", "decorator", "PASS",
     "interface Coffee { double cost(); String desc(); }\n"
     "class Espresso implements Coffee {\n"
     "    public double cost() { return 2.0; }\n"
     "    public String desc() { return \"espresso\"; }\n"
     "}\n"
     "class MilkDecorator implements Coffee {\n"
     "    private final Coffee inner;\n"
     "    public MilkDecorator(Coffee inner) { this.inner = inner; }\n"
     "    public double cost() { double base = inner.cost(); return base + 0.5; }\n"
     "    public String desc() { return inner.desc() + \" + milk\"; }\n"
     "}\n"),

    # TASK 1 (Template): an abstract class whose concrete 'template' calls only a PRIVATE helper
    # of its own and never any abstract primitive or overridable hook -- no genuine inversion of
    # control, nothing deferred to a subclass. T3 must fail (private helper is not a deferred op).
    ("t1_template_private_helper_no_ioc__FAIL", "template-method", "FAIL",
     "abstract class Processor {\n"
     "    public final void process() { helper(); }\n"
     "    private void helper() { System.out.println(\"internal work\"); }\n"
     "    public abstract void onComplete();\n"
     "}\n"
     "class RealProcessor extends Processor {\n"
     "    public void onComplete() {}\n"
     "}\n"),

    # TASK 1 (Template): a template that calls one abstract primitive AND one default-body hook,
    # confirming both kinds of deferred step satisfy T2/T3 together.
    ("t1_template_primitive_plus_hook", "template-method", "PASS",
     "abstract class Game {\n"
     "    protected abstract void initialize();\n"
     "    protected void finish() { System.out.println(\"default done\"); }\n"
     "    public final void play() { initialize(); finish(); }\n"
     "}\n"
     "class Chess extends Game {\n"
     "    protected void initialize() { System.out.println(\"setup\"); }\n"
     "    protected void finish() { System.out.println(\"checkmate\"); }\n"
     "}\n"),

    # ---- TASK 2: interface-vs-abstract-class axis (proves the reused rule) ----

    # TASK 2 (Decorator): the same valid decorator with the component as an INTERFACE.
    ("t2_decorator_component_interface", "decorator", "PASS",
     "interface Notifier { void send(String m); }\n"
     "class BaseNotifier implements Notifier { public void send(String m) {} }\n"
     "class LoggingNotifier implements Notifier {\n"
     "    private final Notifier inner;\n"
     "    public LoggingNotifier(Notifier inner) { this.inner = inner; }\n"
     "    public void send(String m) { System.out.println(\"log\"); inner.send(m); }\n"
     "}\n"),

    # TASK 2 (Decorator): the SAME valid decorator with the component as an ABSTRACT CLASS.
    # Must pass identically to the interface twin above.
    ("t2_decorator_component_abstract_class", "decorator", "PASS",
     "abstract class Notifier { public abstract void send(String m); }\n"
     "class BaseNotifier extends Notifier { public void send(String m) {} }\n"
     "class LoggingNotifier extends Notifier {\n"
     "    private final Notifier inner;\n"
     "    public LoggingNotifier(Notifier inner) { this.inner = inner; }\n"
     "    public void send(String m) { System.out.println(\"log\"); inner.send(m); }\n"
     "}\n"),

    # TASK 2 (Builder): a builder exposed via an INTERFACE Builder with a concrete implementor,
    # using void-setter steps (the interface-role form the checker detects). Confirms an
    # interface builder is recognised. (The FLUENT interface-builder form is a PROBE below.)
    ("t2_builder_interface_void_setters", "builder", "PASS",
     "interface CarBuilder {\n"
     "    void setColor(String c);\n"
     "    void setWheels(int w);\n"
     "    Car assemble();\n"
     "}\n"
     "class Car {\n"
     "    private final String color;\n"
     "    private final int wheels;\n"
     "    public Car(String color, int wheels) { this.color = color; this.wheels = wheels; }\n"
     "}\n"
     "class StandardCarBuilder implements CarBuilder {\n"
     "    private String color;\n"
     "    private int wheels;\n"
     "    public void setColor(String c) { this.color = c; }\n"
     "    public void setWheels(int w) { this.wheels = w; }\n"
     "    public Car assemble() { return new Car(color, wheels); }\n"
     "}\n"),

    # ---- TASK 3: Decorator-vs-Proxy limitation, DEMONSTRATED ----

    # TASK 3 (Decorator): a genuine virtual/lazy-init PROXY -- holds the component, delegates,
    # but its added logic is ACCESS CONTROL (creates the real subject on first use), not
    # enhancement. KNOWN LIMITATION: the checker cannot distinguish Proxy from Decorator and
    # accepts it. Labelled PASS on purpose (see threats to validity).
    ("t3_decorator_lazy_proxy_KNOWN_LIMITATION", "decorator", "PASS",
     "// KNOWN LIMITATION: this is a Proxy (lazy-init / virtual proxy), NOT a Decorator. The\n"
     "// checker cannot statically distinguish 'controls access' from 'adds behaviour' and\n"
     "// accepts any structurally-conforming wrapper as Decorator (see threats to validity).\n"
     "interface Image { void display(); }\n"
     "class RealImage implements Image {\n"
     "    private final String file;\n"
     "    public RealImage(String file) { this.file = file; }\n"
     "    public void display() { System.out.println(\"render \" + file); }\n"
     "}\n"
     "class ProxyImage implements Image {\n"
     "    private final String file;\n"
     "    private Image real;\n"
     "    public ProxyImage(String file) { this.file = file; }\n"
     "    public void display() { if (real == null) { real = new RealImage(file); } real.display(); }\n"
     "}\n"),

    # ---- TASK 4: Template Method in an interface (Java-8 default method) ----

    # TASK 4 (Template): an INTERFACE with a default-method template calling two abstract
    # interface primitives, plus an implementing class supplying them. Definitional decision:
    # a default-method template IS accepted as Template Method (see bdt_property_spec.md).
    ("t4_template_interface_default_method", "template-method", "PASS",
     "interface Report {\n"
     "    String header();\n"
     "    String body();\n"
     "    default String render() { return header() + \"\\n\" + body(); }\n"
     "}\n"
     "class SalesReport implements Report {\n"
     "    public String header() { return \"SALES\"; }\n"
     "    public String body() { return \"...\"; }\n"
     "}\n"),

    # ---- TASK 5: idiomatic MUST-PASS variants (confirm non-gating props score) ----

    # TASK 5 (Builder): a genuinely immutable product (all-final fields, no setters). Confirms
    # B5 scores; product immutability does not gate recognition.
    ("t5_builder_immutable_product", "builder", "PASS",
     "class Point {\n"
     "    private final int x;\n"
     "    private final int y;\n"
     "    private Point(Builder b) { this.x = b.x; this.y = b.y; }\n"
     "    public int getX() { return x; }\n"
     "    public int getY() { return y; }\n"
     "    public static class Builder {\n"
     "        private int x;\n"
     "        private int y;\n"
     "        public Builder x(int x) { this.x = x; return this; }\n"
     "        public Builder y(int y) { this.y = y; return this; }\n"
     "        public Point build() { return new Point(this); }\n"
     "    }\n"
     "}\n"),

    # TASK 5 (Template): a FINAL template method (vs. the non-final HttpServlet-style). Confirms
    # T4 scores.
    ("t5_template_final_template", "template-method", "PASS",
     "abstract class SortAlgorithm {\n"
     "    public final void sort(int[] data) { if (data.length > 1) { doSort(data); } }\n"
     "    protected abstract void doSort(int[] data);\n"
     "}\n"
     "class QuickSort extends SortAlgorithm {\n"
     "    protected void doSort(int[] data) { /* partition ... */ }\n"
     "}\n"),

    # ================================================================== #
    # pass-5 RESOLVED probes -- these three were the "discriminating middle" open findings;
    # after approval the two Builder gaps were FIXED (Finding 1 state-consuming terminal;
    # Finding 3 conforming fluent return) and the Decorator D3 semantics were DECIDED
    # (keep 'any', add non-critical D6 diagnostic). All three now match their (corrected) label.
    # ================================================================== #

    # Finding 1 (Builder B2 gap, FIXED): fluent step sets a builder field that build() IGNORES
    # (product built with defaults). The terminal is now required to consume builder state, so
    # build() `return new Gadget();` is no longer a terminal -> correctly NOT recognised.
    ("t1_builder_hollow_steps_ignored__FAIL", "builder", "FAIL",
     "class Gadget {\n"
     "    private final String part;\n"
     "    public Gadget() { this.part = \"default\"; }\n"
     "    public String getPart() { return part; }\n"
     "}\n"
     "class GadgetBuilder {\n"
     "    private String part;\n"
     "    public GadgetBuilder setPart(String part) { this.part = part; return this; }\n"
     "    public Gadget build() { return new Gadget(); }\n"
     "}\n"),

    # Finding 3 (Builder fluent-interface gap, FIXED): fluent steps return the INTERFACE type the
    # builder conforms to (return this typed as the abstraction). Fluent detection now accepts a
    # conforming return type, so this idiomatic interface builder is correctly recognised.
    ("t2_builder_interface_fluent", "builder", "PASS",
     "interface HouseBuilder {\n"
     "    HouseBuilder walls(int n);\n"
     "    HouseBuilder roof(String type);\n"
     "    House build();\n"
     "}\n"
     "class House {\n"
     "    private final int walls;\n"
     "    private final String roof;\n"
     "    public House(int walls, String roof) { this.walls = walls; this.roof = roof; }\n"
     "}\n"
     "class ConcreteHouseBuilder implements HouseBuilder {\n"
     "    private int walls;\n"
     "    private String roof;\n"
     "    public HouseBuilder walls(int n) { this.walls = n; return this; }\n"
     "    public HouseBuilder roof(String type) { this.roof = type; return this; }\n"
     "    public House build() { return new House(walls, roof); }\n"
     "}\n"),

    # Finding 2 (Decorator D3, DECIDED: keep 'any' + add non-critical D6): partial delegation --
    # foo() delegates to the wrapped ref, bar() hard-codes a value. Per the decision this is
    # ACCEPTED as a Decorator (D2=1, D3=1, recognised), matching the accept-any-conforming-wrapper
    # philosophy (a legitimate method-suppressing decorator looks identical). The new non-critical
    # D6 (full-delegation) = 0 flags that not every operation forwards. See DIAGNOSTIC CHECKS below.
    ("t1_decorator_partial_delegation_accepted", "decorator", "PASS",
     "// Partial delegation is ACCEPTED as Decorator under the D3='any' policy; the non-critical\n"
     "// D6 diagnostic (=0 here) flags that not all component operations forward. See bdt spec.\n"
     "interface Service { int foo(); int bar(); }\n"
     "class RealService implements Service {\n"
     "    public int foo() { return 1; }\n"
     "    public int bar() { return 2; }\n"
     "}\n"
     "class PartialDecorator implements Service {\n"
     "    private final Service inner;\n"
     "    public PartialDecorator(Service inner) { this.inner = inner; }\n"
     "    public int foo() { return inner.foo(); }\n"
     "    public int bar() { return 99; }\n"
     "}\n"),
]


# ---------------------------------------------------------------------------------------------
# DIAGNOSTIC CHECKS -- demonstrate the NON-CRITICAL Decorator D6 property (Finding 2 decision:
# keep critical D3 = 'any', add D6 = 'every implemented component op forwards'). D6 gives
# visibility into partial delegation WITHOUT changing recognition. Each entry asserts the
# expected D6 value on an already-materialised confirmed decorator case.
# (name_of_confirmed_case, expected_D6, why)
D6_DIAGNOSTICS = [
    ("t1_decorator_partial_delegation_accepted", 0, "partial delegation: foo() forwards, bar() hard-codes -> D6=0 (still recognised via D2/D3)"),
    ("t1_decorator_enhance_before_after", 1, "genuine enhance: every op forwards + adds work -> D6=1"),
    ("decorator_collapsed_single_synchronized", 1, "all ops (add,size) forward -> D6=1"),
    ("decorator_filterinputstream_analogue", 1, "the sole op (read) forwards -> D6=1"),
    ("t3_decorator_lazy_proxy_KNOWN_LIMITATION", 1, "the sole op (display) forwards -> D6=1"),
]


def compile_case(path):
    """javac the single-file case into a temp dir. Returns 'OK' / 'FAIL' / 'n/a' (no javac)."""
    if shutil.which("javac") is None:
        return "n/a"
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(["javac", "-d", tmp, path], capture_output=True, text=True)
        return "OK" if proc.returncode == 0 else "FAIL"


SAT_BY_CASE = {}  # name -> {property_id: satisfaction}, populated by score()


def score(name, pattern, src):
    """Materialise the case and return (recognised, critical-string, piqs, javac)."""
    path = os.path.join(OUTDIR, name + ".java")
    with open(path, "w") as fh:
        fh.write(src)
    res = svc.evaluate(pattern, {name + ".java": src})
    sat = {x["property_id"]: x["satisfaction"] for x in res["logical_assessment"]}
    SAT_BY_CASE[name] = sat
    critical = _CRITICAL_PROPERTIES[pattern]
    recognised = all(sat.get(c, 0) == 1 for c in critical)
    crit_str = " ".join(f"{c}={sat.get(c, '?')}" for c in sorted(critical))
    piqs = res["final_quality_result_piqs"]["result_percent"]
    return recognised, crit_str, piqs, compile_case(path)


def main():
    # -------------------- CONFIRMED (gating) --------------------
    rows = []
    all_ok = True
    for name, pattern, label, src in CONFIRMED_CASES:
        recognised, crit_str, piqs, comp = score(name, pattern, src)
        ok = recognised == (label == "PASS")
        all_ok = all_ok and ok
        rows.append((name, pattern, label, "PATTERN" if recognised else "NOT-PATTERN",
                     crit_str, f"PIQS={piqs}", comp, "OK" if ok else "MISMATCH"))

    w = max(len(r[0]) for r in rows)
    hdr = f"{'case'.ljust(w)}  {'pattern':15}  expected  actual       critical(weight-3)         piqs        javac  result"
    print("=" * len(hdr))
    print("CONFIRMED CASES  (gate the exit code -- every one must match its label)")
    print("=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))
    for name, pattern, label, actual, crit_str, piqs, comp, result in rows:
        print(f"{name.ljust(w)}  {pattern:15}  {label:8}  {actual:11}  {crit_str:25}  {piqs:10}  {comp:5}  {result}")
    n_pass = sum(1 for r in rows if r[2] == "PASS")
    print(f"\n{len(rows)} confirmed cases ({n_pass} MUST-PASS, {len(rows) - n_pass} MUST-FAIL)")
    print("CONFIRMED:", "ALL MATCH THEIR LABEL" if all_ok else "-- MISMATCH(ES) PRESENT")

    # -------------------- DIAGNOSTIC: Decorator D6 (non-critical) --------------------
    # Demonstrates that D6 distinguishes partial from full delegation WITHOUT changing recognition
    # (every case below is still recognised via critical {D2,D3}). Finding-2 decision made visible.
    print()
    print("=" * len(hdr))
    print("DIAGNOSTIC: Decorator D6 (non-critical full-delegation flag; recognition unchanged)")
    print("=" * len(hdr))
    diag_ok = True
    for name, expected_d6, why in D6_DIAGNOSTICS:
        sat = SAT_BY_CASE.get(name, {})
        actual_d6 = sat.get("D6", "?")
        d2d3 = f"D2={sat.get('D2', '?')} D3={sat.get('D3', '?')}"
        ok = actual_d6 == expected_d6
        diag_ok = diag_ok and ok
        print(f"  {'OK' if ok else 'MISMATCH':8}  {name.ljust(w)}  D6={actual_d6} (want {expected_d6})  [{d2d3}]  {why}")
    all_ok = all_ok and diag_ok
    print("D6 DIAGNOSTIC:", "ALL AS EXPECTED" if diag_ok else "-- MISMATCH(ES) PRESENT")

    print()
    print(f"Java cases materialised under: {OUTDIR}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
