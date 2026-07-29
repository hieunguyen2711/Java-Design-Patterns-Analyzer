// JDK-style StringBuilder analogue: chained fluent appends + toString() terminal.
// Modelled, NOT imported from the JDK.
class TextBuilder {
    private String value = "";
    public TextBuilder append(String s) { value = value + s; return this; }
    public TextBuilder appendLine(String s) { value = value + s + "\n"; return this; }
    public String toString() { return value; }
}
