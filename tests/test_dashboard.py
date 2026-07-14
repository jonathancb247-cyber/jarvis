import http.client
import json
import unittest
from pathlib import Path

from jarvis_core.api.server import make_server
from jarvis_core.dashboard.server import make_dashboard_server, STATIC_DIR
from tests.test_runtime_api import runtime_fixture, start_server, stop_server


REPO_ROOT = Path(__file__).resolve().parents[1]


class DashboardStaticServerTests(unittest.TestCase):
    def test_dashboard_serves_fixed_static_assets(self):
        with runtime_fixture() as fixture:
            dashboard_server, dashboard_thread = _start_dashboard_server(fixture.adapter)
            try:
                index = request(dashboard_server, "GET", "/")
                css = request(dashboard_server, "GET", "/styles.css")
                js = request(dashboard_server, "GET", "/app.js")
            finally:
                stop_server(dashboard_server, dashboard_thread)

        self.assertEqual(index.status, 200)
        self.assertIn("text/html", index.content_type)
        self.assertIn("JarvisOS Dashboard", index.text)
        self.assertEqual(css.status, 200)
        self.assertIn("text/css", css.content_type)
        self.assertIn("--primary", css.text)
        self.assertEqual(js.status, 200)
        self.assertIn("application/javascript", js.content_type)
        self.assertIn("getHealth", js.text)

    def test_dashboard_rejects_unknown_assets_and_traversal(self):
        with runtime_fixture() as fixture:
            server, thread = _start_dashboard_server(fixture.adapter)
            try:
                missing = request(server, "GET", "/missing.js")
                traversal = request(server, "GET", "/../docs/project/PROJECT_STATE.md")
            finally:
                stop_server(server, thread)

        self.assertEqual(missing.status, 404)
        self.assertEqual(traversal.status, 404)
        self.assertNotIn("Project State", missing.text + traversal.text)

    def test_dashboard_preserves_api_routes(self):
        with runtime_fixture() as fixture:
            server, thread = _start_dashboard_server(fixture.adapter)
            try:
                health = request_json(server, "GET", "/api/v1/health")
                devices = request_json(server, "GET", "/api/v1/devices")
                detail = request_json(server, "GET", "/api/v1/devices/lamp_1")
                capabilities = request_json(
                    server, "GET", "/api/v1/devices/lamp_1/capabilities"
                )
                state = request_json(server, "GET", "/api/v1/devices/lamp_1/state")
                command = request_json(
                    server,
                    "POST",
                    "/api/v1/commands",
                    body=json.dumps({"input": "device list"}),
                    headers={"Content-Type": "application/json"},
                )
            finally:
                stop_server(server, thread)

        self.assertEqual(health["status"], "ok")
        self.assertEqual(devices["devices"][0]["device_id"], "lamp_1")
        self.assertEqual(detail["device_id"], "lamp_1")
        self.assertEqual(capabilities["capabilities"][0]["name"], "power.switch")
        self.assertEqual(state["status"], "unknown")
        self.assertTrue(command["success"])

    def test_api_only_server_does_not_serve_dashboard_assets(self):
        with runtime_fixture() as fixture:
            server, thread = start_server(fixture.adapter)
            try:
                index = request(server, "GET", "/")
                css = request(server, "GET", "/styles.css")
            finally:
                stop_server(server, thread)

        self.assertEqual(index.status, 404)
        self.assertEqual(css.status, 404)
        self.assertIn("application/json", index.content_type)


class DashboardAssetTests(unittest.TestCase):
    def test_html_contains_stable_accessible_structure(self):
        html = _asset_text("index.html")

        for token in (
            "JarvisOS Dashboard",
            "Overview",
            "Devices",
            "Device Detail",
            "Command Console",
            "connectionStatus",
            "aria-live",
            "viewport",
            "commandInput",
        ):
            self.assertIn(token, html)

    def test_static_assets_are_offline_and_framework_free(self):
        combined = "\n".join(
            _asset_text(name) for name in ("index.html", "styles.css", "app.js")
        )

        forbidden = [
            "https://",
            "http://",
            "react",
            "vue",
            "svelte",
            "bootstrap",
            "tailwind",
            "cdn",
            "analytics",
        ]
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, combined.lower())

    def test_javascript_uses_safe_rendering_and_relative_api(self):
        script = _asset_text("app.js")

        self.assertNotIn("innerHTML", script)
        self.assertNotIn("eval(", script)
        self.assertNotIn("new Function", script)
        self.assertIn("textContent", script)
        self.assertIn("AbortController", script)
        self.assertIn('"/api/v1/health"', script)
        self.assertIn("encodeURIComponent(validateDeviceId(id))", script)

    def test_generated_controls_use_canonical_commands(self):
        script = _asset_text("app.js")

        self.assertIn("device apply ${deviceId} ${capability.name} state=${stateValue}", script)
        self.assertIn("device read ${deviceId} ${capability.name}", script)
        self.assertIn("window.confirm", script)
        self.assertIn("power.switch", script)
        self.assertIn("status.read", _asset_text("index.html") + script)

    def test_responsive_and_focus_styles_are_present(self):
        styles = _asset_text("styles.css")

        self.assertIn("@media (max-width: 900px)", styles)
        self.assertIn("@media (max-width: 520px)", styles)
        self.assertIn(":focus-visible", styles)
        self.assertIn("--success", styles)
        self.assertIn("--stale", styles)


class Response:
    def __init__(self, status, content_type, text):
        self.status = status
        self.content_type = content_type
        self.text = text


def _start_dashboard_server(adapter):
    server = make_dashboard_server(adapter, port=0)
    import threading

    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    return server, thread


def request(server, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection(*server.server_address, timeout=5)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        text = response.read().decode("utf-8")
        return Response(response.status, response.getheader("Content-Type", ""), text)
    finally:
        conn.close()


def request_json(server, method, path, body=None, headers=None):
    response = request(server, method, path, body=body, headers=headers)
    return json.loads(response.text)


def _asset_text(name):
    return (STATIC_DIR / name).read_text(encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
