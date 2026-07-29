abstract class Processor {
    public final void process() { helper(); }
    private void helper() { System.out.println("internal work"); }
    public abstract void onComplete();
}
class RealProcessor extends Processor {
    public void onComplete() {}
}
