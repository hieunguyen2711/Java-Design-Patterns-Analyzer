// java.io FilterInputStream analogue: abstract component, concrete component,
// abstract decorator holding the component, concrete decorator delegating.
abstract class InputStream {
    public abstract int read();
}
class FileInputStream extends InputStream {
    private int pos = 0;
    public int read() { return pos < 5 ? pos++ : -1; }
}
abstract class FilterInputStream extends InputStream {
    protected InputStream in;
    public FilterInputStream(InputStream in) { this.in = in; }
    public int read() { return in.read(); }
}
class BufferedInputStream extends FilterInputStream {
    public BufferedInputStream(InputStream in) { super(in); }
    public int read() { int b = super.read(); return b; }
}
