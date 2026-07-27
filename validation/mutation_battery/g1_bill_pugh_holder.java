class Bill {
    private Bill() {}
    public static Bill getInstance() { return Holder.INSTANCE; }
    private static class Holder {
        private static final Bill INSTANCE = new Bill();
    }
}
