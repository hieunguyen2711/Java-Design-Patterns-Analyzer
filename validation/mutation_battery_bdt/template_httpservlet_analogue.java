// javax.servlet HttpServlet analogue: non-final concrete template service() dispatching
// to hook methods (doGet/doPost) with default bodies.
class Request { String method; }
class Response { void send(String s) {} }
abstract class HttpServlet {
    protected void doGet(Request req, Response res) { res.send("405"); }
    protected void doPost(Request req, Response res) { res.send("405"); }
    public void service(Request req, Response res) {
        if (req.method.equals("GET")) { doGet(req, res); }
        else if (req.method.equals("POST")) { doPost(req, res); }
    }
}
class MyServlet extends HttpServlet {
    protected void doGet(Request req, Response res) { res.send("hello"); }
}
