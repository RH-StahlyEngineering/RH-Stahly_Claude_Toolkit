"""The master session's panel: one page that shows the state file, served on this PC only.

    python -X utf8 -I panel.py [--state FILE] [--port 8791]

Open the printed address in the app's Browser pane or any browser. The server reads the
state file on every request and never writes; the page keeps nothing and asks again on a
timer. Stop it with Ctrl+C.
"""
import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # `-I` leaves the script folder out
import state as store  # noqa: E402

HOST = "127.0.0.1"
PAGE = Path(__file__).resolve().parent.parent / "panel" / "index.html"


class Handler(BaseHTTPRequestHandler):
    server_version = "MasterSessionPanel"

    def _send(self, status, content_type, body, head=False):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def do_GET(self, head=False):
        # Only a page opened at this PC's own address may read: a site elsewhere that
        # points its name at 127.0.0.1 sends its own name as Host.
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        if host not in (HOST, "localhost"):
            return self._send(403, "text/plain; charset=utf-8", b"this PC only\n", head)
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", PAGE.read_bytes(), head)
        elif path == "/state.json":
            body = json.dumps(read_state(self.server.state_path), ensure_ascii=False).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body, head)
        else:
            self._send(404, "text/plain; charset=utf-8", b"not found\n", head)

    def do_HEAD(self):
        self.do_GET(head=True)

    def _refuse(self):
        body = b"read-only\n"
        self.send_response(405)
        self.send_header("Allow", "GET, HEAD")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_POST = do_PUT = do_DELETE = do_PATCH = _refuse

    def log_message(self, *args):  # quiet: the page asks every few seconds
        pass


def read_state(path):
    """What the page shows: the state as the store reads it with the store's own counts, or why it can't be read."""
    try:
        state = store.load(path)
        return {"ok": True, "path": str(path), "state": state, "room": store.room(state)}
    except (OSError, ValueError, KeyError, TypeError) as err:
        return {"ok": False, "path": str(path),
                "message": f"State file {path} is missing or damaged ({err}). "
                           "The master creates it with `python -X utf8 -I scripts/state.py init`."}


class Server(ThreadingHTTPServer):
    allow_reuse_address = False  # on Windows, reuse would let a second panel share the port


def make_server(state_path, port):
    server = Server((HOST, port), Handler)
    server.state_path = Path(state_path) if state_path else store.default_state_path()
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state", help="state file (default: the state store's)")
    parser.add_argument("--port", type=int, default=8791, help="port on 127.0.0.1 (0: any free port)")
    args = parser.parse_args(argv)
    try:
        server = make_server(args.state, args.port)
    except OSError as err:
        print(f"panel: port {args.port} on {HOST} can't be used ({err}). A panel may already be running "
              "there: open it, or pass --port.", file=sys.stderr)
        return 1
    print(f"Panel: http://{HOST}:{server.server_address[1]}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
