// Degenerate: build() returns the builder (this), not a distinct product -> B1 fails.
class FluentThing {
    private String name;
    public FluentThing setName(String name) { this.name = name; return this; }
    public FluentThing build() { return this; }
}
