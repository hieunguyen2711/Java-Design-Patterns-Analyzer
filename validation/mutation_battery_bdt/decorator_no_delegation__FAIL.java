// Degenerate: a wrapper implementing the component interface but whose methods ignore the
// wrapped object (no delegation) -> D3 fails.
interface Logger { void log(String m); }
class ConsoleLogger implements Logger { public void log(String m) { System.out.println(m); } }
class FakeDecorator implements Logger {
    private final Logger wrapped;
    public FakeDecorator(Logger wrapped) { this.wrapped = wrapped; }
    public void log(String m) { System.out.println("ignored"); }
}
