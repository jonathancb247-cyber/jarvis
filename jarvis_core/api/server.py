"""Standard-library HTTP server for the optional Runtime API."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from jarvis_core.api import errors
from jarvis_core.api.adapter import RuntimeApiAdapter
from jarvis_core.api.validation import MAX_REQUEST_BYTES


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}


class RuntimeApiServer(ThreadingHTTPServer):
    """HTTP server carrying one injected RuntimeApiAdapter."""

    daemon_threads = True

    def __init__(self, server_address, api_adapter):
        if not isinstance(api_adapter, RuntimeApiAdapter):
            raise TypeError("RuntimeApiServer requires RuntimeApiAdapter")
        self.api_adapter = api_adapter
        super().__init__(server_address, RuntimeApiRequestHandler)


class RuntimeApiRequestHandler(BaseHTTPRequestHandler):
    """Route HTTP requests into RuntimeApiAdapter without serving files."""

    server_version = "JarvisRuntimeAPI/0.1"
    # Bound a single slow client socket operation (read/write). Provider request
    # timeouts remain the authority that bounds a local understanding call.
    timeout = 30

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._method_not_allowed()

    def do_PATCH(self):
        self._method_not_allowed()

    def do_DELETE(self):
        self._method_not_allowed()

    def do_OPTIONS(self):
        self._method_not_allowed()

    def log_message(self, format, *args):
        return

    def _handle(self, method):
        body = b""
        if method == "POST":
            if _has_header(self.headers, "Transfer-Encoding"):
                self.close_connection = True
                self._send_error(
                    errors.request_invalid("API request framing is invalid.")
                )
                return
            lengths = self.headers.get_all("Content-Length") or []
            if len(lengths) != 1:
                self._send_error(errors.request_invalid("Content length is invalid."))
                return
            try:
                content_length = int(lengths[0])
            except (TypeError, ValueError):
                self._send_error(errors.request_invalid("Content length is invalid."))
                return
            if content_length < 0:
                self._send_error(errors.request_invalid("Content length is invalid."))
                return
            if content_length > MAX_REQUEST_BYTES:
                self.rfile.read(min(content_length, MAX_REQUEST_BYTES + 1))
                self.close_connection = True
                self._send_error(errors.payload_too_large())
                return
            body = self.rfile.read(content_length)
        response = self.server.api_adapter.handle_request(
            method,
            self.path,
            dict(self.headers.items()),
            body,
        )
        self._send_json(response.status, response.body, response.headers)

    def _method_not_allowed(self):
        self._send_error(errors.method_not_allowed())

    def _send_error(self, error):
        self._send_json(error.status, errors.error_response(error))

    def _send_json(self, status, body, headers=None):
        payload = json.dumps(body, sort_keys=True).encode("utf-8")
        self.send_response(status)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        if not headers or "Content-Type" not in headers:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _has_header(headers, name):
    return headers.get(name) is not None


def validate_host(host):
    if host not in ALLOWED_HOSTS:
        raise ValueError("invalid_host")
    return DEFAULT_HOST if host == "localhost" else host


def make_server(api_adapter, host=DEFAULT_HOST, port=DEFAULT_PORT):
    return RuntimeApiServer((validate_host(host), int(port)), api_adapter)
