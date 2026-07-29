// Degenerate: an abstract class with a concrete method and abstract methods that the
// concrete method NEVER calls (no inversion of control) -> T3 fails.
abstract class Task {
    public abstract void step1();
    public abstract void step2();
    public void run() { System.out.println("running"); }
}
class RealTask extends Task {
    public void step1() {}
    public void step2() {}
}
