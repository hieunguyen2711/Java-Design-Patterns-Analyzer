// java.util.AbstractList analogue: concrete (final) template calling abstract
// get/size primitives.
abstract class AbstractList {
    public abstract Object get(int index);
    public abstract int size();
    public final boolean contains(Object o) {
        for (int i = 0; i < size(); i++) {
            if (get(i).equals(o)) { return true; }
        }
        return false;
    }
}
class MyList extends AbstractList {
    private Object[] data = new Object[] { "a", "b" };
    public Object get(int index) { return data[index]; }
    public int size() { return data.length; }
}
