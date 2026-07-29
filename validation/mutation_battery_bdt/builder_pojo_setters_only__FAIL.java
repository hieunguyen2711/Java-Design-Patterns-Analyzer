// Degenerate: a POJO with only setters and NO terminal / build method -> B1 fails.
class UserPojo {
    private String name;
    private int age;
    public void setName(String name) { this.name = name; }
    public void setAge(int age) { this.age = age; }
}
