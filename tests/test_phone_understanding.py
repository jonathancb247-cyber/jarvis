"""Phone diagnostic acceptance scenarios, with no native inference or execution."""

import ast
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from jarvis_core.ai.gemma_android_bridge import GemmaAndroidBridgeConfig, GemmaAndroidBridgeTransport
from jarvis_core.ai.gemma_local import GemmaLocalResponse
from tools.phone_understanding import MODEL_ID, PhoneUnderstandingSession, main, present


def proposal(**changes):
    data = {
        "intent": "read", "referenced_device_id": "lamp_1",
        "capability_hint": "status.read", "operation_hint": "read",
    }
    data.update(changes)
    return data


class Transport:
    def __init__(self, body=None, error=None):
        self.body = body if body is not None else proposal()
        self.error = error
        self.requests = []

    def generate(self, request, timeout_seconds, max_response_bytes):
        self.requests.append(request)
        if self.error:
            raise self.error
        return GemmaLocalResponse(self.body)


class PhoneUnderstandingTests(unittest.TestCase):
    def diagnose(self, request, transport=None):
        payload = PhoneUnderstandingSession(transport=transport or Transport()).diagnose("request-1", request)
        self.assertIs(payload["commands_executed"], False)
        self.assertIs(payload["decision"]["commands_executed"], False)
        self.assertTrue(all(value is False for value in payload["execution"].values()))
        self.assertNotIn("canonical_command_text", payload["decision"])
        return payload

    def test_explicit_supported_instruction_is_candidate_without_runtime(self):
        with patch("jarvis_core.runtime.Runtime.execute", side_effect=AssertionError("execution forbidden")):
            payload = self.diagnose("Lee status.read del dispositivo lamp_1.")
        self.assertEqual(payload["decision"]["status"], "executable_candidate")

    def test_explicit_mutation_is_only_candidate_requiring_confirmation(self):
        payload = self.diagnose(
            "Enciende power.switch del dispositivo lamp_1 con state true.",
            Transport(proposal(intent="mutate", capability_hint="power.switch",
                               operation_hint="apply", raw_arguments=[["state", "true"]])),
        )
        self.assertEqual(payload["decision"]["status"], "executable_candidate")
        self.assertTrue(payload["decision"]["confirmation_required"])

    def test_ambiguous_instruction_clarifies_even_with_fabricated_valid_id(self):
        payload = self.diagnose("Enciende la luz.", Transport(proposal(
            intent="mutate", referenced_device_text="light", capability_hint="power.switch",
            operation_hint="apply", raw_arguments=[["state", "true"]],
        )))
        self.assertEqual(payload["decision"]["status"], "needs_clarification")

    def test_destructive_instruction_refuses_even_with_invalid_output_or_host_loss(self):
        for transport in (Transport({"kind": "execute"}), Transport(error=OSError("unavailable"))):
            with self.subTest(transport=transport):
                payload = self.diagnose("Borra todos los dispositivos.", transport)
                self.assertEqual(payload["decision"]["status"], "refused")

    def test_unsupported_instruction_cannot_be_candidate(self):
        payload = self.diagnose("Lee battery.level del dispositivo lamp_1.",
                                Transport(proposal(capability_hint="battery.level")))
        self.assertEqual(payload["decision"]["status"], "needs_clarification")

    def test_host_unavailable(self):
        payload = self.diagnose("Lee status.read del dispositivo lamp_1.", Transport(error=OSError()))
        self.assertEqual(payload["decision"]["status"], "local_ai_unavailable")

    def test_invalid_model_response_fails_closed(self):
        for invalid in ({"intent": "read", "unexpected": True}, "not JSON", {"kind": "execute"}):
            with self.subTest(invalid=invalid):
                payload = self.diagnose("Lee status.read del dispositivo lamp_1.", Transport(invalid))
                self.assertEqual(payload["decision"]["status"], "understanding_failed")

    def test_duplicate_diagnostic_does_not_rerun_inference(self):
        transport = Transport()
        session = PhoneUnderstandingSession(transport=transport)
        first = session.diagnose("repeat-id", "Lee status.read del dispositivo lamp_1.")
        repeated = session.diagnose("repeat-id", "Lee status.read del dispositivo lamp_1.")
        self.assertEqual(len(transport.requests), 1)
        self.assertTrue(repeated["duplicate"])
        self.assertEqual(first["decision"], repeated["decision"])
        self.assertIs(repeated["commands_executed"], False)
        repeated["decision"]["status"] = "tampered"
        self.assertEqual(session.diagnose("repeat-id", "Lee status.read del dispositivo lamp_1.")["decision"], first["decision"])

    def test_duplicate_id_with_changed_request_rejected(self):
        transport = Transport()
        session = PhoneUnderstandingSession(transport=transport)
        session.diagnose("same", "Lee status.read del dispositivo lamp_1.")
        result = session.diagnose("same", "Borra todos los dispositivos.")
        self.assertEqual(result["error"], "request_id_conflict")
        self.assertEqual(len(transport.requests), 1)
        self.assertIs(result["commands_executed"], False)

    def test_invalid_and_full_session_reject_before_inference(self):
        transport = Transport()
        session = PhoneUnderstandingSession(transport=transport)
        for request_id, request in (("../bad", "read"), ("ok", ""), ("ok", "x" * 1025)):
            self.assertIs(session.diagnose(request_id, request)["commands_executed"], False)
        self.assertEqual(len(transport.requests), 0)
        with patch("tools.phone_understanding.MAX_SESSION_REQUESTS", 1):
            session.diagnose("first", "Lee status.read del dispositivo lamp_1.")
            self.assertEqual(session.diagnose("second", "read")["error"], "session_full")
        self.assertEqual(len(transport.requests), 1)

    def test_hint_only_model_contract_and_safe_presentation(self):
        transport = Transport()
        payload = self.diagnose("Lee status.read del dispositivo lamp_1.", transport)
        request = transport.requests[0]
        self.assertEqual(request["model"], MODEL_ID)
        self.assertTrue(request["output_contract"]["no_ai_action_plan"])
        self.assertEqual(request["execution"], {"tools": False, "runtime": False, "drivers": False})
        self.assertIn("commands_executed=false", present(payload))
        self.assertIn("executable_candidate", present(payload))
        self.assertNotIn("user_request", json.loads(present(payload, as_json=True)))

    def test_unexpected_diagnostic_failure_is_bounded_and_cached(self):
        session = PhoneUnderstandingSession(transport=Transport())
        with patch("tools.phone_understanding.run_ai_understanding_decision", side_effect=RuntimeError("private error")) as run:
            payload = session.diagnose("failed", "read")
            repeated = session.diagnose("failed", "read")
        self.assertEqual(run.call_count, 1)
        self.assertEqual(payload["error"], "diagnostic_failed")
        self.assertIs(payload["commands_executed"], False)
        self.assertTrue(repeated["duplicate"])
        self.assertNotIn("private error", present(payload))

    def test_interactive_repeat_uses_same_session(self):
        outputs = []
        inputs = iter(["Lee status.read del dispositivo lamp_1.", ":repeat", ":quit"])
        transport = Transport()
        with patch("tools.phone_understanding.PhoneUnderstandingSession",
                   return_value=PhoneUnderstandingSession(transport=transport)):
            self.assertEqual(main([], input_fn=lambda _: next(inputs), output_fn=outputs.append), 0)
        self.assertEqual(len(transport.requests), 1)
        self.assertIn("duplicate: true", outputs[-1])

    def test_client_has_no_execution_imports_or_external_host_flags(self):
        source = Path("tools/phone_understanding.py").read_text()
        tree = ast.parse(source)
        imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        for forbidden in ("jarvis_core.runtime", "jarvis_core.drivers", "jarvis_core.ai.execution_gate",
                          "jarvis_core.ai.adapter", "jarvis_core.api", "jarvis_core.mqtt_driver"):
            self.assertNotIn(forbidden, imports)
        for flag in ("--execute", "--confirm", "--host", "--port", "--cloud-fallback"):
            self.assertNotIn(flag, source)


@contextmanager
def bridge(body):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.server.requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class PhoneLoopbackTests(unittest.TestCase):
    def test_real_loopback_http_to_existing_validation_and_duplicate_cache(self):
        with bridge(proposal()) as server:
            transport = GemmaAndroidBridgeTransport(GemmaAndroidBridgeConfig("127.0.0.1", server.server_port))
            session = PhoneUnderstandingSession(transport=transport)
            result = session.diagnose("http-id", "Lee status.read del dispositivo lamp_1.")
            duplicate = session.diagnose("http-id", "Lee status.read del dispositivo lamp_1.")
            self.assertEqual(result["decision"]["status"], "executable_candidate")
            self.assertIs(result["commands_executed"], False)
            self.assertTrue(duplicate["duplicate"])
            self.assertEqual(len(server.requests), 1)

    def test_real_loopback_invalid_model_response_fails_closed(self):
        with bridge({"intent": "read", "invented": "field"}) as server:
            transport = GemmaAndroidBridgeTransport(GemmaAndroidBridgeConfig("127.0.0.1", server.server_port))
            result = PhoneUnderstandingSession(transport=transport).diagnose("invalid", "Lee status.read del dispositivo lamp_1.")
            self.assertEqual(result["decision"]["status"], "understanding_failed")
            self.assertIs(result["commands_executed"], False)


if __name__ == "__main__":
    unittest.main()
