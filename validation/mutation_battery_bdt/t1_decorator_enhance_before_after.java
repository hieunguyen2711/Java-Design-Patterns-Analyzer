interface Coffee { double cost(); String desc(); }
class Espresso implements Coffee {
    public double cost() { return 2.0; }
    public String desc() { return "espresso"; }
}
class MilkDecorator implements Coffee {
    private final Coffee inner;
    public MilkDecorator(Coffee inner) { this.inner = inner; }
    public double cost() { double base = inner.cost(); return base + 0.5; }
    public String desc() { return inner.desc() + " + milk"; }
}
