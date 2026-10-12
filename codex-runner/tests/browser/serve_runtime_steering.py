"""Serve the shared UI with a mock-only steering fixture; reject all actions."""
import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

class Handler(SimpleHTTPRequestHandler):
    def do_POST(self):
        self.send_error(405, "Fixture never submits actions")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            body = (ROOT / "static/hosted.html").read_text().replace(
                '<script src="/static/hosted.js" defer>',
                '<script src="/__fixture.js" defer></script><script src="/static/hosted.js" defer>').encode()
            kind = "text/html"
        elif path == "/__fixture.js":
            body = (ROOT / "tests/browser/runtime_steering.js").read_bytes()
            kind = "text/javascript"
        elif path.startswith("/static/") and ".." not in path and (ROOT / path.lstrip("/")).is_file():
            body = (ROOT / path.lstrip("/")).read_bytes()
            kind = self.guess_type(path)
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8897)
    args = parser.parse_args()
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
