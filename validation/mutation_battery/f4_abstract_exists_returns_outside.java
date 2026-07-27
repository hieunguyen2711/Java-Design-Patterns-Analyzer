interface Shape {}
class Circle implements Shape {}
class Report {}
class ShapeFactory {
    public Report make() { Circle c = new Circle(); return new Report(); }
}
