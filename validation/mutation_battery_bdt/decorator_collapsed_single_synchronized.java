// Collapsed single decorator implementing the interface + delegating, no abstract base
// (Collections.synchronizedList style).
interface MyList {
    void add(String s);
    int size();
}
class ArrayMyList implements MyList {
    private String[] data = new String[16];
    private int n = 0;
    public void add(String s) { data[n++] = s; }
    public int size() { return n; }
}
class SynchronizedMyList implements MyList {
    private final MyList inner;
    public SynchronizedMyList(MyList inner) { this.inner = inner; }
    public void add(String s) { synchronized (this) { inner.add(s); } }
    public int size() { synchronized (this) { return inner.size(); } }
}
