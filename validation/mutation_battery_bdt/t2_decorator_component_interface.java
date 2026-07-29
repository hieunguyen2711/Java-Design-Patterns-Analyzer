interface Notifier { void send(String m); }
class BaseNotifier implements Notifier { public void send(String m) {} }
class LoggingNotifier implements Notifier {
    private final Notifier inner;
    public LoggingNotifier(Notifier inner) { this.inner = inner; }
    public void send(String m) { System.out.println("log"); inner.send(m); }
}
