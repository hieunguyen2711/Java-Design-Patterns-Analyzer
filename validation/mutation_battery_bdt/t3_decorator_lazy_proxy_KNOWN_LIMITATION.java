// KNOWN LIMITATION: this is a Proxy (lazy-init / virtual proxy), NOT a Decorator. The
// checker cannot statically distinguish 'controls access' from 'adds behaviour' and
// accepts any structurally-conforming wrapper as Decorator (see threats to validity).
interface Image { void display(); }
class RealImage implements Image {
    private final String file;
    public RealImage(String file) { this.file = file; }
    public void display() { System.out.println("render " + file); }
}
class ProxyImage implements Image {
    private final String file;
    private Image real;
    public ProxyImage(String file) { this.file = file; }
    public void display() { if (real == null) { real = new RealImage(file); } real.display(); }
}
