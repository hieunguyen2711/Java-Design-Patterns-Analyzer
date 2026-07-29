interface Report {
    String header();
    String body();
    default String render() { return header() + "\n" + body(); }
}
class SalesReport implements Report {
    public String header() { return "SALES"; }
    public String body() { return "..."; }
}
