import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from jarvis_core.api.adapter import RuntimeApiAdapter
from jarvis_core.api.projections import ApiProjectionBuilder
from jarvis_core.api.server import make_server, validate_host
from jarvis_core.bootstrap import build_runtime_from_config, build_simulated_runtime
from jarvis_core.domain import CapabilityResult
from jarvis_core.http_driver import HttpJsonResponse


class FakeHttpTransport:
    def __init__(self, success=True):
        self.success = success
        self.calls = []

    def post_json(self, url, payload, timeout_seconds, max_response_bytes):
        self.calls.append((url, payload, timeout_seconds, max_response_bytes))
        if not self.success:
            raise TimeoutError("timeout")
        return HttpJsonResponse(
            200,
            "application/json",
            {"success": True, "observations": {"power": True}},
        )


class RuntimeApiProjectionTests(unittest.TestCase):
    def test_health_projection_is_safe(self):
        with runtime_fixture() as fixture:
            body = fixture.adapter.handle_request("GET", "/api/v1/health").body

        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["prototype"], "AVP-001")
        self.assertEqual(body["device_count"], 1)
        self.assertTrue(body["persistence_enabled"])
        self.assertEqual(body["profile_name"], "http-lab")
        self.assertNotIn("state_store_path", str(body))
        self.assertNotIn("192.168.1.50", str(body))

    def test_device_list_projection_is_ordered_and_safe(self):
        with runtime_fixture() as fixture:
            body = fixture.adapter.handle_request("GET", "/api/v1/devices").body

        self.assertEqual(len(body["devices"]), 1)
        self.assertEqual(body["devices"][0]["device_id"], "lamp_1")
        self.assertEqual(body["devices"][0]["status"], "unknown")
        self.assertFalse(body["devices"][0]["is_current"])
        self.assertEqual(body["devices"][0]["capability_count"], 2)
        self.assertNotIn("metadata", str(body))
        self.assertNotIn("http://", str(body))

    def test_device_detail_capabilities_and_state_are_safe(self):
        with runtime_fixture() as fixture:
            device = fixture.runtime.context.device_registry.get("lamp_1")
            device.metadata["url"] = "http://192.168.1.50"
            device.state.properties.update(
                {
                    "power": False,
                    "url": "http://192.168.1.50",
                    "stack_trace": "boom",
                    "nested": {"raw": "payload"},
                }
            )

            detail = fixture.adapter.handle_request(
                "GET", "/api/v1/devices/lamp_1"
            ).body
            capabilities = fixture.adapter.handle_request(
                "GET", "/api/v1/devices/lamp_1/capabilities"
            ).body
            state = fixture.adapter.handle_request(
                "GET", "/api/v1/devices/lamp_1/state"
            ).body

        self.assertEqual(detail["semantic_properties"], {"power": False})
        self.assertEqual(capabilities["capabilities"][0]["name"], "power.switch")
        self.assertEqual(
            capabilities["capabilities"][0]["parameters"],
            {"state": {"type": "string", "required": True}},
        )
        self.assertEqual(state["semantic_properties"], {"power": False})
        self.assertNotIn("availability_policy", str(capabilities))
        self.assertNotIn("192.168.1.50", str(detail))
        self.assertNotIn("stack", str(state))

    def test_state_current_mapping(self):
        with runtime_fixture() as fixture:
            device = fixture.runtime.context.device_registry.get("lamp_1")
            for status, expected in (
                ("unknown", False),
                ("stale", False),
                ("known", True),
            ):
                device.state.status = status
                body = fixture.adapter.handle_request(
                    "GET", "/api/v1/devices/lamp_1/state"
                ).body
                self.assertEqual(body["status"], status)
                self.assertEqual(body["is_current"], expected)

    def test_unknown_device_is_safe_404(self):
        with runtime_fixture() as fixture:
            response = fixture.adapter.handle_request(
                "GET", "/api/v1/devices/missing"
            )

        self.assertEqual(response.status, 404)
        self.assertEqual(response.body["error"], "api_route_not_found")
        self.assertNotIn("KeyError", str(response.body))


class RuntimeApiCommandTests(unittest.TestCase):
    def test_command_submission_uses_runtime_owned_boundary(self):
        runtime = RecordingRuntime()
        adapter = RuntimeApiAdapter(
            runtime,
            ApiProjectionBuilder(build_simulated_runtime().context.device_registry),
        )

        response = adapter.handle_request(
            "POST",
            "/api/v1/commands",
            {"Content-Type": "application/json"},
            json.dumps({"input": "what time is it?"}).encode("utf-8"),
        )

        self.assertEqual(response.status, 200)
        self.assertTrue(response.body["success"])
        self.assertEqual(runtime.calls, [("what time is it?", "api")])
        self.assertNotIn("data", response.body)

    def test_runtime_failure_is_safely_mapped(self):
        with runtime_fixture(success=False) as fixture:
            response = fixture.adapter.handle_request(
                "POST",
                "/api/v1/commands",
                {"Content-Type": "application/json"},
                json.dumps({"input": "device read lamp_1 status.read"}).encode("utf-8"),
            )

        self.assertEqual(response.status, 400)
        self.assertFalse(response.body["success"])
        self.assertEqual(response.body["message"], "Device command failed.")
        self.assertEqual(response.body["error"], "device_execution_failed")
        self.assertNotIn("http://", str(response.body))
        self.assertNotIn("TimeoutError", str(response.body))

    def test_request_validation_rejects_unsafe_commands(self):
        unsafe_inputs = [
            "device list\ndevice list",
            "device list\r",
            "device list; rm x",
            "device list | cat",
            "device list > out",
            "device list # hidden",
            "device read http://example.test",
            "python -c print(1)",
            "C:\\temp\\file",
            "/tmp/file",
        ]
        with runtime_fixture() as fixture:
            for command in unsafe_inputs:
                with self.subTest(command=command):
                    response = fixture.adapter.handle_request(
                        "POST",
                        "/api/v1/commands",
                        {"Content-Type": "application/json"},
                        json.dumps({"input": command}).encode("utf-8"),
                    )
                    self.assertEqual(response.status, 400)
                    self.assertEqual(response.body["error"], "api_command_invalid")

    def test_request_validation_rejects_invalid_payloads(self):
        with runtime_fixture() as fixture:
            cases = [
                ({}, 400),
                ({"input": ""}, 400),
                ({"input": "device list", "extra": True}, 400),
                ({"input": "x" * 513}, 400),
            ]
            for payload, status in cases:
                with self.subTest(payload=payload):
                    response = fixture.adapter.handle_request(
                        "POST",
                        "/api/v1/commands",
                        {"Content-Type": "application/json"},
                        json.dumps(payload).encode("utf-8"),
                    )
                    self.assertEqual(response.status, status)

    def test_request_validation_rejects_json_issues(self):
        with runtime_fixture() as fixture:
            invalid_json = fixture.adapter.handle_request(
                "POST",
                "/api/v1/commands",
                {"Content-Type": "application/json"},
                b"{",
            )
            invalid_utf8 = fixture.adapter.handle_request(
                "POST",
                "/api/v1/commands",
                {"Content-Type": "application/json"},
                b"\xff",
            )
            duplicate_key = fixture.adapter.handle_request(
                "POST",
                "/api/v1/commands",
                {"Content-Type": "application/json"},
                b'{"input":"device list","input":"device list"}',
            )
            wrong_type = fixture.adapter.handle_request(
                "POST",
                "/api/v1/commands",
                {"Content-Type": "text/plain"},
                b'{"input":"device list"}',
            )

        self.assertEqual(invalid_json.status, 400)
        self.assertEqual(invalid_utf8.status, 400)
        self.assertEqual(duplicate_key.status, 400)
        self.assertEqual(wrong_type.status, 415)

    def test_route_and_method_errors_are_safe(self):
        with runtime_fixture() as fixture:
            missing = fixture.adapter.handle_request("GET", "/api/v1/missing")
            method = fixture.adapter.handle_request("DELETE", "/api/v1/devices")
            unsafe = fixture.adapter.handle_request("GET", "/api/v1/devices/../state")

        self.assertEqual(missing.status, 404)
        self.assertEqual(method.status, 405)
        self.assertIn(unsafe.status, {400, 404})
        self.assertNotIn("Traceback", str(missing.body) + str(method.body))


class RuntimeApiServerTests(unittest.TestCase):
    def test_server_handles_health_and_devices_on_localhost(self):
        with runtime_fixture() as fixture:
            server, thread = start_server(fixture.adapter)
            try:
                health_status, health = request_json(server, "GET", "/api/v1/health")
                devices_status, devices = request_json(server, "GET", "/api/v1/devices")
            finally:
                stop_server(server, thread)

        self.assertEqual(health_status, 200)
        self.assertEqual(health["status"], "ok")
        self.assertEqual(devices_status, 200)
        self.assertEqual(devices["devices"][0]["device_id"], "lamp_1")

    def test_server_rejects_oversized_body_before_adapter_parsing(self):
        with runtime_fixture() as fixture:
            server, thread = start_server(fixture.adapter)
            try:
                status, body = request_json(
                    server,
                    "POST",
                    "/api/v1/commands",
                    body=b"x" * (16 * 1024 + 1),
                    headers={"Content-Type": "application/json"},
                )
            finally:
                stop_server(server, thread)

        self.assertEqual(status, 413)
        self.assertEqual(body["error"], "api_payload_too_large")

    def test_localhost_security(self):
        self.assertEqual(validate_host("127.0.0.1"), "127.0.0.1")
        self.assertEqual(validate_host("localhost"), "127.0.0.1")
        with self.assertRaises(ValueError):
            validate_host("0.0.0.0")

        with runtime_fixture() as fixture:
            response = fixture.adapter.handle_request("GET", "/api/v1/health")

        self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    def test_command_execution_is_serialized(self):
        runtime = RecordingRuntime()
        adapter = RuntimeApiAdapter(
            runtime,
            ApiProjectionBuilder(build_simulated_runtime().context.device_registry),
        )

        first = adapter.handle_request(
            "POST",
            "/api/v1/commands",
            {"Content-Type": "application/json"},
            json.dumps({"input": "what time is it?"}).encode("utf-8"),
        )
        second = adapter.handle_request(
            "POST",
            "/api/v1/commands",
            {"Content-Type": "application/json"},
            json.dumps({"input": "device list"}).encode("utf-8"),
        )

        self.assertTrue(first.body["success"])
        self.assertTrue(second.body["success"])
        self.assertEqual(
            runtime.calls,
            [("what time is it?", "api"), ("device list", "api")],
        )


class RecordingRuntime:
    def __init__(self):
        self.calls = []

    def handle_adapter_input(self, text, source="cli"):
        self.calls.append((text, source))
        return CapabilityResult(True, "ok", {"secret": "not exposed"}, None)

    def shutdown(self):
        self.calls.append(("shutdown", "runtime"))


class RuntimeFixture:
    def __init__(self, success=True):
        self.success = success

    def __enter__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config_path = write_profile(self.root, "state/http-lab.state.json")
        self.transport = FakeHttpTransport(success=self.success)
        self.runtime = build_runtime_from_config(
            self.config_path,
            http_transport=self.transport,
        )
        self.adapter = RuntimeApiAdapter(
            self.runtime,
            ApiProjectionBuilder(
                self.runtime.context.device_registry,
                profile_name="http-lab",
                persistence_enabled=True,
            ),
        )
        return self

    def __exit__(self, exc_type, exc, tb):
        self.temp.cleanup()


def runtime_fixture(success=True):
    return RuntimeFixture(success=success)


def start_server(adapter):
    server = make_server(adapter, port=0)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    return server, thread


def stop_server(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def request_json(server, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection(*server.server_address, timeout=5)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        return response.status, payload
    finally:
        conn.close()


def write_profile(root, state_store_path):
    path = root / "profile.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profile": "http-lab",
                "devices": [
                    {
                        "id": "lamp_1",
                        "name": "ESP32 LED",
                        "type": "light",
                        "capabilities": [
                            {
                                "name": "power.switch",
                                "kind": "action",
                                "parameters": {
                                    "state": {"type": "string", "required": True}
                                },
                                "constraints": {},
                                "availability_policy": {},
                            },
                            {
                                "name": "status.read",
                                "kind": "reading",
                                "parameters": {},
                                "constraints": {},
                                "availability_policy": {},
                            },
                        ],
                        "metadata": {},
                    }
                ],
                "http_bindings": [
                    {
                        "device_id": "lamp_1",
                        "base_url": "http://192.168.1.50",
                        "timeout_seconds": 2.0,
                        "read_path": "/device/read",
                        "apply_path": "/device/apply",
                    }
                ],
                "runtime_options": {"state_store_path": state_store_path},
            }
        ),
        encoding="utf-8",
    )
    return path


if __name__ == "__main__":
    unittest.main()
