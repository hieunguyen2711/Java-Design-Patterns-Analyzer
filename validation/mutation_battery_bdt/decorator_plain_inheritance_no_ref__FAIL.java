// Degenerate: a subclass that extends the concrete component and adds a method, with NO
// wrapped reference (plain inheritance, not composition) -> D2 fails.
interface Coffee { double cost(); }
class SimpleCoffee implements Coffee { public double cost() { return 2.0; } }
class MilkCoffee extends SimpleCoffee {
    public double cost() { return 2.5; }
    public String extra() { return "milk"; }
}
