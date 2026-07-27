class Classic {
    private static Classic instance;
    private Classic() {}
    public static Classic getInstance() {
        if (instance == null) instance = new Classic();
        return instance;
    }
}
