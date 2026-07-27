interface Strategy { void run(); }
class Impl implements Strategy { public void run() {} }
class Context {
    private Strategy s;
    public Context(Strategy s) { this.s = s; }
    public void go() { s.run(); }
}
