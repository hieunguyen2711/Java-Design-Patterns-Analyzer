// Bloch fluent static-nested builder: immutable product, private product ctor.
// (package-private so the single-file case compiles under any file name)
class Pizza {
    private final String size;
    private final boolean cheese;
    private Pizza(Builder b) { this.size = b.size; this.cheese = b.cheese; }
    public String getSize() { return size; }
    public boolean hasCheese() { return cheese; }
    public static class Builder {
        private String size;
        private boolean cheese;
        public Builder size(String size) { this.size = size; return this; }
        public Builder cheese(boolean cheese) { this.cheese = cheese; return this; }
        public Pizza build() { return new Pizza(this); }
    }
}
