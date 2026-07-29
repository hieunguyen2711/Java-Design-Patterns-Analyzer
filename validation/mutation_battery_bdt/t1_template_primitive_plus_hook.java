abstract class Game {
    protected abstract void initialize();
    protected void finish() { System.out.println("default done"); }
    public final void play() { initialize(); finish(); }
}
class Chess extends Game {
    protected void initialize() { System.out.println("setup"); }
    protected void finish() { System.out.println("checkmate"); }
}
