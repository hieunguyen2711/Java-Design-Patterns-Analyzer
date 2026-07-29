// Degenerate: the 'template' method is itself abstract -- there is no fixed skeleton
// (no concrete algorithm) -> T1/T3 fail.
abstract class ReportGenerator {
    public abstract void generate();
    public abstract void writeHeader();
    public abstract void writeBody();
}
class PdfReport extends ReportGenerator {
    public void generate() { writeHeader(); writeBody(); }
    public void writeHeader() {}
    public void writeBody() {}
}
