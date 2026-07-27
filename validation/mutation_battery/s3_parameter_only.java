interface Strategy { void run(); }
class Impl implements Strategy { public void run() {} }
class Context {
    public void go(Strategy s) { s.run(); }
}
