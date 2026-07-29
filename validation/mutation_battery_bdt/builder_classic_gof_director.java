// Classic GoF Builder: Director + abstract Builder + ConcreteBuilder + Product,
// void buildPart steps + getResult() terminal.
class Product {
    private String partA;
    private String partB;
    public void setPartA(String a) { this.partA = a; }
    public void setPartB(String b) { this.partB = b; }
    public String describe() { return partA + partB; }
}
abstract class Builder {
    protected Product product = new Product();
    public abstract void buildPartA();
    public abstract void buildPartB();
    public Product getResult() { return product; }
}
class ConcreteBuilder extends Builder {
    public void buildPartA() { product.setPartA("A"); }
    public void buildPartB() { product.setPartB("B"); }
}
class Director {
    private Builder builder;
    public Director(Builder builder) { this.builder = builder; }
    public void construct() { builder.buildPartA(); builder.buildPartB(); }
}
