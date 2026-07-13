import json
import socket
import unittest
from urllib.error import HTTPError, URLError

from jarvis_core.http_driver import (
    HttpConnectionError,
    HttpInvalidJsonError,
    HttpResponseTooLargeError,
    HttpTimeoutError,
    NoRedirectHandler,
    UrllibHttpJsonTransport,
)


class FakeHeaders:
    def __init__(self, content_type="application/json"):
        self.content_type = content_type

    def get(self, name, default=None):
        if name.lower() == "content-type":
            return self.content_type
        return default


class FakeResponse:
    def __init__(self, status_code=200, body=None, content_type="application/json"):
        self.status_code = status_code
        self.body = body if body is not None else {"success": True}
        self.headers = FakeHeaders(content_type)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def getcode(self):
        return self.status_code

    def read(self, size=-1):
        return json.dumps(self.body).encode("utf-8")[:size]

    def close(self):
        pass


class FakeOpener:
    def __init__(self, response=None, error=None):
        self.response = response or FakeResponse()
        self.error = error
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        if self.error:
            raise self.error
        return self.response


class OversizedResponse(FakeResponse):
    def read(self, size=-1):
        return b"x" * (size + 1)


class InvalidJsonResponse(FakeResponse):
    def read(self, size=-1):
        return b"{not-json"


class UrllibHttpJsonTransportTests(unittest.TestCase):
    def test_post_json_returns_sanitized_response(self):
        opener = FakeOpener(
            FakeResponse(status_code=200, body={"success": True, "observations": {}})
        )
        transport = UrllibHttpJsonTransport(opener=opener)

        response = transport.post_json(
            "http://localhost/device/read",
            {"capability": "status.read"},
            2,
            1024,
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("application/json", response.content_type)
        self.assertEqual({"success": True, "observations": {}}, response.body)
        self.assertEqual(1, len(opener.requests))

    def test_timeout_is_normalized(self):
        transport = UrllibHttpJsonTransport(
            opener=FakeOpener(error=URLError(socket.timeout("timed out")))
        )

        with self.assertRaises(HttpTimeoutError):
            transport.post_json("http://localhost/device/read", {}, 2, 1024)

    def test_connection_error_is_normalized(self):
        transport = UrllibHttpJsonTransport(
            opener=FakeOpener(error=URLError(OSError("connection refused")))
        )

        with self.assertRaises(HttpConnectionError):
            transport.post_json("http://localhost/device/read", {}, 2, 1024)

    def test_response_limit_is_enforced(self):
        transport = UrllibHttpJsonTransport(opener=FakeOpener(OversizedResponse()))

        with self.assertRaises(HttpResponseTooLargeError):
            transport.post_json("http://localhost/device/read", {}, 2, 16)

    def test_invalid_json_is_normalized(self):
        transport = UrllibHttpJsonTransport(opener=FakeOpener(InvalidJsonResponse()))

        with self.assertRaises(HttpInvalidJsonError):
            transport.post_json("http://localhost/device/read", {}, 2, 1024)

    def test_redirects_are_rejected(self):
        handler = NoRedirectHandler()

        self.assertIsNone(handler.redirect_request(None, None, 302, "Found", {}, "x"))

    def test_http_error_response_is_returned_without_following_redirect(self):
        fp = FakeResponse(status_code=302, body={"success": False, "error": "redirect"})
        error = HTTPError(
            "http://localhost/device/read",
            302,
            "Found",
            FakeHeaders("application/json"),
            fp,
        )
        transport = UrllibHttpJsonTransport(opener=FakeOpener(error=error))

        response = transport.post_json("http://localhost/device/read", {}, 2, 1024)

        self.assertEqual(302, response.status_code)
        self.assertEqual({"success": False, "error": "redirect"}, response.body)


if __name__ == "__main__":
    unittest.main()
