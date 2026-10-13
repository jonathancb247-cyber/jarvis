"""Standard-library HTTP server for the optional Runtime API."""

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import BoundedSemaphore

from jarvis_core.api import errors
from jarvis_core.api.adapter import RuntimeApiAdapter
from jarvis_core.api.validation import MAX_REQUEST_BYTES


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}

# Global admission bound on concurrent open connections/worker threads. A
# connection is admitted before any request byte is read; over-capacity sockets
# are rejected with a bounded 503 and closed instead of queuing unbounded threads.
DEFAULT_MAX_CONNECTIONS = 16
# Absolute wall-clock budget for reading one request (headers and body). Unlike a
# per-operation socket timeout this cannot be extended by a slow client that
# trickles bytes, so it bounds slow-header and slow-body stalls.
DEFAULT_REQUEST_TOTAL_BUDGET_SECONDS = 5.0
MAX_BODY_CHUNK = 64 * 1024


class RuntimeApiServer(ThreadingHTTPServer):
    """HTTP server carrying one injected RuntimeApiAdapter."""

    daemon_threads = True

    def __init__(
        self,
        server_address,
        api_adapter,
        *,
        max_connections=DEFAULT_MAX_CONNECTIONS,
        request_total_budget_seconds=DEFAULT_REQUEST_TOTAL_BUDGET_SECONDS,
    ):
        if not isinstance(api_adapter, RuntimeApiAdapter):
            raise TypeError("RuntimeApiServer requires RuntimeApiAdapter")
        if not isinstance(max_connections, int) or max_connections < 1:
            raise ValueError("max_connections must be a positive int")
        self.api_adapter = api_adapter
        self.request_total_budget_seconds = float(request_total_budget_seconds)
        self._admission = BoundedSemaphore(max_connections)
        super().__init__(server_address, RuntimeApiRequestHandler)

    def process_request(self, request, client_address):
        """Admit a connection only while a global slot is available.

        Admission happens before the connection thread consumes any request
        bytes. When capacity is exhausted the connection is rejected immediately.
        """
        if not self._admission.acquire(blocking=False):
            self._reject_over_capacity(request)
            return
        super().process_request(request, client_address)

    def shutdown_request(self, request):
        try:
            super().shutdown_request(request)
        finally:
            self._admission.release()

    def _reject_over_capacity(self, request):
        body = json.dumps(
            errors.error_response(errors.server_busy()), sort_keys=True
        ).encode("utf-8")
        response = (
            b"HTTP/1.1 503 Service Unavailable\r\n"
            b"Content-Type: application/json; charset=utf-8\r\n"
            b"Connection: close\r\n"
            b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body
        )
        try:
            request.settimeout(1.0)
            request.sendall(response)
        except OSError:
            pass
        finally:
            try:
                self.close_request(request)
            except OSError:
                pass


class _DeadlineReader:
    """Wrap a request stream so every read obeys one absolute deadline.

    The socket timeout is re-armed with the remaining budget before each read so
    a slow client cannot extend the total read time by trickling bytes.
    """

    def __init__(self, connection, stream, remaining):
        self._connection = connection
        self._stream = stream
        self._remaining = remaining

    def _arm(self):
        remaining = self._remaining()
        if remaining <= 0:
            raise TimeoutError("request read deadline exceeded")
        self._connection.settimeout(remaining)

    def readline(self, *args):
        self._arm()
        return self._stream.readline(*args)

    def read(self, *args):
        self._arm()
        return self._stream.read(*args)

    def read1(self, *args):
        self._arm()
        return self._stream.read1(*args)

    def __getattr__(self, name):
        return getattr(self._stream, name)


class RuntimeApiRequestHandler(BaseHTTPRequestHandler):
    """Route HTTP requests into RuntimeApiAdapter without serving files."""

    server_version = "JarvisRuntimeAPI/0.1"
    # Coarse per-socket guard; the authoritative bound is the absolute request
    # deadline applied in ``handle_one_request``.
    timeout = 30
    _deadline = 0.0

    def handle_one_request(self):
        self._deadline = time.monotonic() + self._request_budget()
        original = self.rfile
        self.rfile = _DeadlineReader(self.connection, original, self._remaining)
        try:
            super().handle_one_request()
        except TimeoutError:
            self.close_connection = True
        finally:
            self.rfile = original

    def _request_budget(self):
        return getattr(
            self.server,
            "request_total_budget_seconds",
            DEFAULT_REQUEST_TOTAL_BUDGET_SECONDS,
        )

    def _remaining(self):
        return self._deadline - time.monotonic()

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
        headers = dict(self.headers.items())
        body = b""
        if method == "POST":
            # Authenticate body-carrying interaction requests before consuming
            # the body, then apply strict framing and read exactly once.
            pre = self.server.api_adapter.pre_authorize(method, self.path, headers)
            if pre is not None:
                self.close_connection = True
                self._send_json(pre.status, pre.body, pre.headers)
                return
            content_length = self._read_framing()
            if content_length is None:
                return
            body = self._read_body(content_length)
            if body is None:
                self.close_connection = True
                self._send_error(
                    errors.request_invalid("API request body is incomplete.")
                )
                return
        response = self.server.api_adapter.handle_request(
            method,
            self.path,
            headers,
            body,
        )
        self._send_json(response.status, response.body, response.headers)

    def _read_framing(self):
        """Validate framing without reading the body; return its exact length."""
        if _has_header(self.headers, "Transfer-Encoding"):
            self.close_connection = True
            self._send_error(errors.request_invalid("API request framing is invalid."))
            return None
        lengths = self.headers.get_all("Content-Length") or []
        if len(lengths) != 1:
            self.close_connection = True
            self._send_error(errors.request_invalid("Content length is invalid."))
            return None
        try:
            content_length = _parse_content_length(lengths[0])
        except errors.ApiError as error:
            self.close_connection = True
            self._send_error(error)
            return None
        if content_length > MAX_REQUEST_BYTES:
            # Reject oversized bodies without reading them.
            self.close_connection = True
            self._send_error(errors.payload_too_large())
            return None
        return content_length

    def _read_body(self, content_length):
        """Read exactly ``content_length`` bytes or fail within the deadline."""
        if content_length == 0:
            return b""
        chunks = []
        remaining = content_length
        while remaining > 0:
            if self._remaining() <= 0:
                return None
            try:
                chunk = self.rfile.read1(min(remaining, MAX_BODY_CHUNK))
            except (TimeoutError, OSError):
                return None
            if not chunk:
                return None
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _method_not_allowed(self):
        self._send_error(errors.method_not_allowed())

    def _send_error(self, error):
        self._send_json(error.status, errors.error_response(error))

    def _send_json(self, status, body, headers=None):
        payload = json.dumps(body, sort_keys=True).encode("utf-8")
        try:
            self.send_response(status)
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            if not headers or "Content-Type" not in headers:
                self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except OSError:
            self.close_connection = True


def _has_header(headers, name):
    return headers.get(name) is not None


def _parse_content_length(value):
    """Accept only a non-negative base-10 integer of ASCII digits.

    This rejects signs, underscores, whitespace, hex and non-ASCII digits that
    ``int()`` would otherwise tolerate (for example ``+18`` or ``1_8``).
    """
    if not isinstance(value, str) or not value.isascii() or not value.isdigit():
        raise errors.request_invalid("Content length is invalid.")
    return int(value)


def validate_host(host):
    if host not in ALLOWED_HOSTS:
        raise ValueError("invalid_host")
    return DEFAULT_HOST if host == "localhost" else host


def make_server(
    api_adapter,
    host=DEFAULT_HOST,
    port=DEFAULT_PORT,
    *,
    max_connections=DEFAULT_MAX_CONNECTIONS,
):
    return RuntimeApiServer(
        (validate_host(host), int(port)),
        api_adapter,
        max_connections=max_connections,
    )
