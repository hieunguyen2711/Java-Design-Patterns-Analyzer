// Partial delegation is ACCEPTED as Decorator under the D3='any' policy; the non-critical
// D6 diagnostic (=0 here) flags that not all component operations forward. See bdt spec.
interface Service { int foo(); int bar(); }
class RealService implements Service {
    public int foo() { return 1; }
    public int bar() { return 2; }
}
class PartialDecorator implements Service {
    private final Service inner;
    public PartialDecorator(Service inner) { this.inner = inner; }
    public int foo() { return inner.foo(); }
    public int bar() { return 99; }
}
