class Config {
    private String host;
    private int port;
    public Config host(String host) { this.host = host; return this; }
    public Config port(int port) { this.port = port; return this; }
}
