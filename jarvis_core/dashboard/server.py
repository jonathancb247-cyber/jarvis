"""Static Dashboard server composed with the existing Runtime API."""

from pathlib import Path

from jarvis_core.api import errors
from jarvis_core.api.server import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    RuntimeApiRequestHandler,
    RuntimeApiServer,
    validate_host,
)


STATIC_DIR = Path(__file__).resolve().parent / "static"

STATIC_ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
}


class DashboardServer(RuntimeApiServer):
    """HTTP server carrying one Runtime API adapter and fixed Dashboard assets."""

    def __init__(self, server_address, api_adapter):
        super().__init__(server_address, api_adapter)
        self.RequestHandlerClass = DashboardRequestHandler


class DashboardRequestHandler(RuntimeApiRequestHandler):
    """Serve a fixed local Dashboard plus the approved Runtime API routes."""

    def do_GET(self):
        if self.path.startswith("/api/"):
            self._handle("GET")
            return
        if self.path in STATIC_ASSETS:
            self._send_static(self.path)
            return
        self._send_error(errors.route_not_found())

    def _send_static(self, path):
        asset_name, content_type = STATIC_ASSETS[path]
        asset_path = STATIC_DIR / asset_name
        try:
            payload = asset_path.read_bytes()
        except OSError:
            self._send_error(errors.route_not_found())
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)


def make_dashboard_server(api_adapter, host=DEFAULT_HOST, port=DEFAULT_PORT):
    return DashboardServer((validate_host(host), int(port)), api_adapter)

