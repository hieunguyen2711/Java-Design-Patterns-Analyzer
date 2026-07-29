interface CarBuilder {
    void setColor(String c);
    void setWheels(int w);
    Car assemble();
}
class Car {
    private final String color;
    private final int wheels;
    public Car(String color, int wheels) { this.color = color; this.wheels = wheels; }
}
class StandardCarBuilder implements CarBuilder {
    private String color;
    private int wheels;
    public void setColor(String c) { this.color = c; }
    public void setWheels(int w) { this.wheels = w; }
    public Car assemble() { return new Car(color, wheels); }
}
