"""Experimental synchronous HTTP local driver boundary for JarvisOS."""

from dataclasses import dataclass
import ipaddress
import json
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from jarvis_core.devices import Device
from jarvis_core.drivers import (
    AUTHENTICATION_FAILED,
    CONFIGURATION_INVALID,
    CONNECTION_FAILED,
    DRIVER_UNAVAILABLE,
    INVALID_DEVICE,
    INVALID_RESPONSE,
    OPERATION_NOT_SUPPORTED,
    PROTOCOL_ERROR,
    REQUEST_TIMEOUT,
    DriverResult,
)


DEFAULT_TIMEOUT_SECONDS = 2.0
MAX_TIMEOUT_SECONDS = 10.0
MAX_RESPONSE_BYTES = 16384
READ_PATH = "/device/read"
APPLY_PATH = "/device/apply"
JSON_CONTENT_TYPE = "application/json"
ALLOWED_REMOTE_ERRORS = {
    DRIVER_UNAVAILABLE,
    CONFIGURATION_INVALID,
    CONNECTION_FAILED,
    REQUEST_TIMEOUT,
    PROTOCOL_ERROR,
    INVALID_RESPONSE,
    AUTHENTICATION_FAILED,
    OPERATION_NOT_SUPPORTED,
}


@dataclass(frozen=True)
class HttpDeviceBinding:
    """In-memory HTTP reachability configuration for one Device."""

    device_id: str
    base_url: str
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    read_path: str = READ_PATH
    apply_path: str = APPLY_PATH

    def __post_init__(self):
        if not isinstance(self.device_id, str) or not self.device_id:
            raise ValueError("HttpDeviceBinding device_id must be a non-empty string")
        if not isinstance(self.base_url, str) or not self.base_url:
            raise ValueError("HttpDeviceBinding base_url must be a non-empty string")
        if not isinstance(self.timeout_seconds, (int, float)):
            raise ValueError("HttpDeviceBinding timeout_seconds must be numeric")
        if self.timeout_seconds <= 0 or self.timeout_seconds > MAX_TIMEOUT_SECONDS:
            raise ValueError("HttpDeviceBinding timeout_seconds is out of range")

        parsed = urlparse(self.base_url)
        if parsed.scheme != "http":
            raise ValueError("HttpDeviceBinding base_url must use http")
        if not parsed.hostname:
            raise ValueError("HttpDeviceBinding base_url must include a host")
        if parsed.username or parsed.password:
            raise ValueError("HttpDeviceBinding base_url must not include credentials")
        if parsed.query:
            raise ValueError("HttpDeviceBinding base_url must not include a query")
        if parsed.fragment:
            raise ValueError("HttpDeviceBinding base_url must not include a fragment")
        try:
            port = parsed.port
        except ValueError as error:
            raise ValueError("HttpDeviceBinding base_url port is invalid") from error
        if port is not None and not (1 <= port <= 65535):
            raise ValueError("HttpDeviceBinding base_url port is invalid")
        if not _is_allowed_local_host(parsed.hostname):
            raise ValueError("HttpDeviceBinding base_url host is not allowed")

        _validate_path(self.read_path, "read_path")
        _validate_path(self.apply_path, "apply_path")


class HttpDeviceBindingStore:
    """Experimental in-memory store for HTTP device bindings."""

    def __init__(self):
        self._bindings = {}

    def register(self, binding):
        if not isinstance(binding, HttpDeviceBinding):
            raise TypeError("HttpDeviceBindingStore.register expects HttpDeviceBinding")
        if binding.device_id in self._bindings:
            raise ValueError(f"HTTP binding already registered: {binding.device_id}")
        self._bindings[binding.device_id] = binding

    def get(self, device_id):
        if device_id not in self._bindings:
            raise KeyError(f"HTTP binding not found: {device_id}")
        return self._bindings[device_id]

    def has(self, device_id):
        return device_id in self._bindings

    def remove(self, device_id):
        if device_id not in self._bindings:
            raise KeyError(f"HTTP binding not found: {device_id}")
        return self._bindings.pop(device_id)

    def list(self):
        return list(self._bindings.values())


@dataclass(frozen=True)
class HttpJsonResponse:
    """Internal sanitized HTTP response for injected transports."""

    status_code: int
    content_type: str
    body: object


class UrllibHttpJsonTransport:
    """Small synchronous HTTP JSON transport using the Python standard library."""

    def __init__(self, opener=None):
        self._opener = opener or build_opener(NoRedirectHandler())

    def post_json(self, url, payload, timeout_seconds, max_response_bytes):
        data = json.dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=data,
            headers={"Content-Type": JSON_CONTENT_TYPE, "Accept": JSON_CONTENT_TYPE},
            method="POST",
        )
        try:
            response = self._opener.open(request, timeout=timeout_seconds)
            with response:
                status_code = response.getcode()
                content_type = response.headers.get("Content-Type", "")
                body = _read_limited_response(response, max_response_bytes)
        except HTTPError as error:
            content_type = error.headers.get("Content-Type", "")
            body = _read_limited_response(error, max_response_bytes)
            return HttpJsonResponse(error.code, content_type, _parse_json_bytes(body))
        except TimeoutError as error:
            raise HttpTimeoutError() from error
        except (socket.timeout, TimeoutError) as error:
            raise HttpTimeoutError() from error
        except URLError as error:
            if isinstance(error.reason, socket.timeout):
                raise HttpTimeoutError() from error
            raise HttpConnectionError() from error
        except OSError as error:
            raise HttpConnectionError() from error

        return HttpJsonResponse(status_code, content_type, _parse_json_bytes(body))


class NoRedirectHandler(HTTPRedirectHandler):
    """urllib handler that rejects redirects instead of following them."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HttpTimeoutError(Exception):
    """Internal timeout marker for HTTP transport."""


class HttpConnectionError(Exception):
    """Internal connection marker for HTTP transport."""


class HttpResponseTooLargeError(Exception):
    """Internal response-size marker for HTTP transport."""


class HttpInvalidJsonError(Exception):
    """Internal JSON marker for HTTP transport."""


class HttpDeviceDriver:
    """Experimental synchronous HTTP local driver."""

    def __init__(
        self,
        binding_store,
        transport=None,
        max_response_bytes=MAX_RESPONSE_BYTES,
    ):
        if not isinstance(binding_store, HttpDeviceBindingStore):
            raise TypeError("HttpDeviceDriver expects an HttpDeviceBindingStore")
        if transport is not None and not callable(getattr(transport, "post_json", None)):
            raise TypeError("HttpDeviceDriver transport must define post_json")
        if not isinstance(max_response_bytes, int) or max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be a positive integer")
        self.binding_store = binding_store
        self.transport = transport or UrllibHttpJsonTransport()
        self.max_response_bytes = max_response_bytes

    def read(self, device, capability_name):
        return self._execute(device, capability_name, None, "read")

    def apply(self, device, capability_name, parameters):
        if not isinstance(parameters, dict):
            return DriverResult(False, {}, CONFIGURATION_INVALID)
        return self._execute(device, capability_name, parameters, "apply")

    def _execute(self, device, capability_name, parameters, operation):
        if not isinstance(device, Device):
            return DriverResult(False, {}, INVALID_DEVICE)
        if not isinstance(capability_name, str) or not capability_name:
            return DriverResult(False, {}, CONFIGURATION_INVALID)

        try:
            binding = self.binding_store.get(device.id)
        except KeyError:
            return DriverResult(False, {}, DRIVER_UNAVAILABLE)

        if not isinstance(binding, HttpDeviceBinding):
            return DriverResult(False, {}, CONFIGURATION_INVALID)

        path = binding.read_path if operation == "read" else binding.apply_path
        payload = {"capability": capability_name}
        if operation == "apply":
            payload["parameters"] = parameters.copy()
        url = _join_url(binding.base_url, path)

        try:
            response = self.transport.post_json(
                url,
                payload,
                binding.timeout_seconds,
                self.max_response_bytes,
            )
        except HttpTimeoutError:
            return DriverResult(False, {}, REQUEST_TIMEOUT)
        except HttpResponseTooLargeError:
            return DriverResult(False, {}, INVALID_RESPONSE)
        except HttpInvalidJsonError:
            return DriverResult(False, {}, INVALID_RESPONSE)
        except HttpConnectionError:
            return DriverResult(False, {}, CONNECTION_FAILED)
        except Exception:
            return DriverResult(False, {}, CONNECTION_FAILED)

        return self._driver_result_from_response(response)

    def _driver_result_from_response(self, response):
        if not isinstance(response, HttpJsonResponse):
            return DriverResult(False, {}, INVALID_RESPONSE)
        if response.status_code == 401 or response.status_code == 403:
            return DriverResult(False, {}, AUTHENTICATION_FAILED)
        if response.status_code < 200 or response.status_code >= 300:
            return DriverResult(False, {}, PROTOCOL_ERROR)
        if not _is_json_content_type(response.content_type):
            return DriverResult(False, {}, INVALID_RESPONSE)
        if not isinstance(response.body, dict):
            return DriverResult(False, {}, INVALID_RESPONSE)

        success = response.body.get("success")
        observations = response.body.get("observations", {})
        error = response.body.get("error")
        if not isinstance(success, bool):
            return DriverResult(False, {}, INVALID_RESPONSE)
        if not isinstance(observations, dict):
            return DriverResult(False, {}, INVALID_RESPONSE)
        if error is not None and (not isinstance(error, str) or not error):
            return DriverResult(False, {}, INVALID_RESPONSE)

        if success:
            return DriverResult(True, observations.copy(), None)
        if error in ALLOWED_REMOTE_ERRORS:
            return DriverResult(False, {}, error)
        return DriverResult(False, {}, PROTOCOL_ERROR)


def _validate_path(path, field_name):
    if not isinstance(path, str) or not path:
        raise ValueError(f"HttpDeviceBinding {field_name} must be a non-empty string")
    parsed = urlparse(path)
    if parsed.scheme or parsed.netloc:
        raise ValueError(f"HttpDeviceBinding {field_name} must be relative")
    if not path.startswith("/"):
        raise ValueError(f"HttpDeviceBinding {field_name} must start with /")
    if ".." in path.split("/"):
        raise ValueError(f"HttpDeviceBinding {field_name} must not traverse paths")
    if parsed.query or parsed.fragment:
        raise ValueError(f"HttpDeviceBinding {field_name} must not include query or fragment")


def _is_allowed_local_host(host):
    normalized = host.lower().rstrip(".")
    if normalized in {"localhost"}:
        return True
    if normalized.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return "." not in normalized
    if address.is_multicast or address.is_unspecified:
        return False
    if address.version == 4 and address == ipaddress.ip_address("255.255.255.255"):
        return False
    return address.is_loopback or address.is_private


def _join_url(base_url, path):
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _is_json_content_type(content_type):
    return content_type.split(";", 1)[0].strip().lower() == JSON_CONTENT_TYPE


def _read_limited_response(response, max_response_bytes):
    body = response.read(max_response_bytes + 1)
    if len(body) > max_response_bytes:
        raise HttpResponseTooLargeError()
    return body


def _parse_json_bytes(body):
    try:
        return json.loads(body.decode("utf-8"))
    except Exception as error:
        raise HttpInvalidJsonError() from error
