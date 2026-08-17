import json
import tempfile
import unittest
from pathlib import Path

from jarvis_core.api.adapter import RuntimeApiAdapter
from jarvis_core.api.projections import ApiProjectionBuilder
from jarvis_core.bootstrap import build_runtime_from_config
from jarvis_core.dashboard.server import make_dashboard_server
from jarvis_core.http_driver import HttpJsonResponse
from tests.test_runtime_api import request_json, stop_server, write_profile


class DashboardHardwareValidationFlowTests(unittest.TestCase):
    def test_dashboard_profile_flow_updates_persists_restores_and_recovers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = write_profile(root, "state/http-lab.state.json")
            state_path = root / "state" / "http-lab.state.json"
            transport = ProfileFlowTransport()
            runtime = build_runtime_from_config(config_path, http_transport=transport)
            adapter = _adapter_for(runtime)
            server, thread = _start_dashboard_server(adapter)
            try:
                index_status, _index = _request_text(server, "GET", "/")
                devices_status, devices = request_json(server, "GET", "/api/v1/devices")
                state_status, initial_state = request_json(
                    server,
                    "GET",
                    "/api/v1/devices/lamp_1/state",
                )

                self.assertEqual(index_status, 200)
                self.assertEqual(devices_status, 200)
                self.assertEqual(state_status, 200)
                self.assertEqual(devices["devices"][0]["device_id"], "lamp_1")
                self.assertEqual(initial_state["status"], "unknown")
                self.assertFalse(initial_state["is_current"])
                self.assertEqual(transport.calls, [])

                read_status, read_result = request_json(
                    server,
                    "POST",
                    "/api/v1/commands",
                    body=json.dumps(
                        {"input": "device read lamp_1 status.read"}
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                known_status, known_state = request_json(
                    server,
                    "GET",
                    "/api/v1/devices/lamp_1/state",
                )

                self.assertEqual(read_status, 200)
                self.assertTrue(read_result["success"])
                self.assertEqual(known_status, 200)
                self.assertEqual(known_state["status"], "known")
                self.assertTrue(known_state["is_current"])
                self.assertEqual(known_state["semantic_properties"], {"power": False})
                self.assertEqual(transport.calls[-1]["payload"], {"capability": "status.read"})

                on_status, on_result = request_json(
                    server,
                    "POST",
                    "/api/v1/commands",
                    body=json.dumps(
                        {"input": "device apply lamp_1 power.switch state=true"}
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                after_on_status, after_on_state = request_json(
                    server,
                    "GET",
                    "/api/v1/devices/lamp_1/state",
                )

                self.assertEqual(on_status, 200)
                self.assertTrue(on_result["success"])
                self.assertEqual(after_on_status, 200)
                self.assertEqual(after_on_state["semantic_properties"], {"power": True})

                runtime.shutdown()
                self.assertTrue(state_path.is_file())
                snapshot = json.loads(state_path.read_text(encoding="utf-8"))
                self.assertEqual(snapshot["schema_version"], 1)
                self.assertEqual(
                    snapshot["states"]["lamp_1"]["properties"],
                    {"power": True},
                )
                self.assertNotIn("error", str(snapshot).lower())
                self.assertNotIn("http://", str(snapshot).lower())
            finally:
                stop_server(server, thread)

            restored_transport = ProfileFlowTransport()
            restored_runtime = build_runtime_from_config(
                config_path,
                http_transport=restored_transport,
            )
            restored_adapter = _adapter_for(restored_runtime)
            try:
                restored_response = restored_adapter.handle_request(
                    "GET",
                    "/api/v1/devices/lamp_1/state",
                )
                restored_state = restored_response.body
                self.assertEqual(restored_response.status, 200)
                self.assertEqual(restored_state["status"], "stale")
                self.assertFalse(restored_state["is_current"])
                self.assertEqual(restored_state["semantic_properties"], {"power": True})

                stale_read_response = restored_adapter.handle_request(
                    "POST",
                    "/api/v1/commands",
                    {"Content-Type": "application/json"},
                    json.dumps({"input": "device read lamp_1 status.read"}).encode(
                        "utf-8"
                    ),
                )
                current_response = restored_adapter.handle_request(
                    "GET",
                    "/api/v1/devices/lamp_1/state",
                )
                self.assertEqual(stale_read_response.status, 200)
                self.assertTrue(stale_read_response.body["success"])
                current_state = current_response.body
                self.assertEqual(current_response.status, 200)
                self.assertEqual(current_state["status"], "known")
                self.assertTrue(current_state["is_current"])
                self.assertEqual(current_state["semantic_properties"], {"power": False})

                restored_transport.fail = True
                failure_response = restored_adapter.handle_request(
                    "POST",
                    "/api/v1/commands",
                    {"Content-Type": "application/json"},
                    json.dumps({"input": "device read lamp_1 status.read"}).encode(
                        "utf-8"
                    ),
                )
                preserved_response = restored_adapter.handle_request(
                    "GET",
                    "/api/v1/devices/lamp_1/state",
                )

                failure_result = failure_response.body
                preserved_state = preserved_response.body
                self.assertEqual(failure_response.status, 400)
                self.assertFalse(failure_result["success"])
                self.assertEqual(failure_result["error"], "device_execution_failed")
                self.assertEqual(preserved_response.status, 200)
                self.assertEqual(preserved_state["status"], "stale")
                self.assertFalse(preserved_state["is_current"])
                self.assertEqual(preserved_state["semantic_properties"], {"power": False})
                self.assertNotIn("TimeoutError", str(failure_result))
                self.assertNotIn("http://", str(failure_result))

                restored_transport.fail = False
                recovery_response = restored_adapter.handle_request(
                    "POST",
                    "/api/v1/commands",
                    {"Content-Type": "application/json"},
                    json.dumps({"input": "device read lamp_1 status.read"}).encode(
                        "utf-8"
                    ),
                )
                recovered_response = restored_adapter.handle_request(
                    "GET",
                    "/api/v1/devices/lamp_1/state",
                )
                recovered_state = recovered_response.body
                self.assertEqual(recovery_response.status, 200)
                self.assertTrue(recovery_response.body["success"])
                self.assertEqual(recovered_state["status"], "known")
                self.assertTrue(recovered_state["is_current"])
                self.assertEqual(recovered_state["semantic_properties"], {"power": False})
            finally:
                restored_runtime.shutdown()


class ProfileFlowTransport:
    def __init__(self):
        self.calls = []
        self.power = False
        self.fail = False

    def post_json(self, url, payload, timeout_seconds, max_response_bytes):
        self.calls.append(
            {
                "payload": payload.copy(),
                "timeout_seconds": timeout_seconds,
                "max_response_bytes": max_response_bytes,
            }
        )
        if self.fail:
            raise TimeoutError("timeout")
        if payload.get("capability") == "power.switch":
            self.power = payload.get("parameters", {}).get("state") == "true"
        return HttpJsonResponse(
            200,
            "application/json",
            {"success": True, "observations": {"power": self.power}},
        )


def _adapter_for(runtime):
    return RuntimeApiAdapter(
        runtime,
        ApiProjectionBuilder(
            runtime.context.device_registry,
            profile_name="http-lab",
            persistence_enabled=True,
        ),
    )


def _start_dashboard_server(adapter):
    import threading

    server = make_dashboard_server(adapter, port=0)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    return server, thread


def _request_text(server, method, path):
    import http.client

    conn = http.client.HTTPConnection(*server.server_address, timeout=5)
    try:
        conn.request(method, path)
        response = conn.getresponse()
        return response.status, response.read().decode("utf-8")
    finally:
        conn.close()


if __name__ == "__main__":
    unittest.main()
