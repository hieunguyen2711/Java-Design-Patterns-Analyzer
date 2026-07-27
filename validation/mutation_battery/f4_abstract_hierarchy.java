interface Product {}
class Real implements Product {}
class Factory {
    public Product make() { return new Real(); }
}
