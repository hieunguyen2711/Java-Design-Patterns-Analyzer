class Gadget {
    private final String part;
    public Gadget() { this.part = "default"; }
    public String getPart() { return part; }
}
class GadgetBuilder {
    private String part;
    public GadgetBuilder setPart(String part) { this.part = part; return this; }
    public Gadget build() { return new Gadget(); }
}
