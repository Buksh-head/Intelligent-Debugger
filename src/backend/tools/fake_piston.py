"""A stand-in for the Piston sandbox, for tests and for running the stack where
the real Piston image is not available. It speaks the part of Piston's API the
backend uses (POST /api/v2/execute) and runs the code with the local runner.

    python -m tools.fake_piston 2000   (from src/backend)
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from debugger.runner import run_locally


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/api/v2/runtimes":
            self._send(200, [{"language": "python", "version": "3.12.0", "aliases": ["py"]}])
        else:
            self._send(404, {"message": "not found"})

    def do_POST(self):  # noqa: N802
        if self.path != "/api/v2/execute":
            return self._send(404, {"message": "not found"})
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        code = body["files"][0]["content"]
        result = run_locally(code, body.get("stdin", ""), timeout_s=3)
        run = {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "output": result.stdout + result.stderr,
            "code": result.returncode,
            "signal": "SIGKILL" if result.timed_out else None,
            "status": "TO" if result.timed_out else ("RE" if result.returncode else None),
        }
        self._send(200, {"language": "python", "version": body.get("version"), "run": run})

    def _send(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def start(port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


if __name__ == "__main__":
    srv, url = start(int(sys.argv[1]) if len(sys.argv) > 1 else 2000)
    print(f"fake Piston listening on {url}", flush=True)
    srv.serve_forever()
