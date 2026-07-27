class Pub {
    private static Pub instance;
    public Pub() {}
    public static Pub getInstance() { if (instance == null) instance = new Pub(); return instance; }
}
