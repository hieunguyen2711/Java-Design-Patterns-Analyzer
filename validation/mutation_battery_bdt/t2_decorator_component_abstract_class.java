abstract class Notifier { public abstract void send(String m); }
class BaseNotifier extends Notifier { public void send(String m) {} }
class LoggingNotifier extends Notifier {
    private final Notifier inner;
    public LoggingNotifier(Notifier inner) { this.inner = inner; }
    public void send(String m) { System.out.println("log"); inner.send(m); }
}
