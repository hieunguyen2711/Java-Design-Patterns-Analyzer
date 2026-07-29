interface HouseBuilder {
    HouseBuilder walls(int n);
    HouseBuilder roof(String type);
    House build();
}
class House {
    private final int walls;
    private final String roof;
    public House(int walls, String roof) { this.walls = walls; this.roof = roof; }
}
class ConcreteHouseBuilder implements HouseBuilder {
    private int walls;
    private String roof;
    public HouseBuilder walls(int n) { this.walls = n; return this; }
    public HouseBuilder roof(String type) { this.roof = type; return this; }
    public House build() { return new House(walls, roof); }
}
