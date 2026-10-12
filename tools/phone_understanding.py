"""Phone-local, report-only understanding client (Python stdlib; no execution)."""

from __future__ import annotations

import argparse
from collections import OrderedDict
from copy import deepcopy
import json
from pathlib import Path
import re
import sys
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.ai_understanding_decision import (  # noqa: E402
    format_decision_text_payload,
    run_ai_understanding_decision,
)

# Approval is provisional and understanding-only: docs/dev/checkpoints/AI_UNDERSTANDING.md.
MODEL_ID = "gemma-4-e2b-int4"
COMPANION_PORT = 8767
LAB_PORT = 8769
MAX_REQUEST_CHARS = 1024
MAX_SESSION_REQUESTS = 64


class PhoneUnderstandingSession:
    """Bounded process-local duplicate suppression; never persists request text.

    Cached IDs are not evicted: once full, new IDs fail closed. Restarting the
    diagnostic deliberately starts a new session. This is diagnostic caching,
    not durable automation idempotency.
    """

    def __init__(self, *, transport=None, timeout_seconds=120, lab=False):
        self.port = LAB_PORT if lab else COMPANION_PORT
        self.transport = transport
        self.timeout_seconds = timeout_seconds
        self._results = OrderedDict()

    def diagnose(self, request_id, request):
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id):
            return self._rejected("invalid_request_id")
        if not isinstance(request, str) or not request.strip() or len(request) > MAX_REQUEST_CHARS:
            return self._rejected("invalid_request")
        request = request.strip()
        previous = self._results.get(request_id)
        if previous is not None:
            if previous[0] != request:
                return self._rejected("request_id_conflict", request_id)
            payload = deepcopy(previous[1])
            payload["duplicate"] = True
            return payload
        if len(self._results) >= MAX_SESSION_REQUESTS:
            return self._rejected("session_full", request_id)
        # Fixed phone loopback only; no host override, ADB, fallback, or execution flags.
        try:
            payload = run_ai_understanding_decision(
                request, model=MODEL_ID, host="127.0.0.1", port=self.port,
                timeout_seconds=self.timeout_seconds, transport=self.transport,
            )
        except Exception:
            payload = self._rejected("diagnostic_failed", request_id)
        payload.update(request_id=request_id, duplicate=False, commands_executed=False)
        self._results[request_id] = (request, deepcopy(payload))
        return payload

    @staticmethod
    def _rejected(error, request_id=None):
        return {
            "request_id": request_id, "duplicate": False,
            "status": "diagnostic_rejected", "error": error,
            "commands_executed": False,
        }


def present(payload, *, as_json=False):
    if as_json:
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if "decision" not in payload:
        return f"Diagnostic rejected: {payload['error']}\ncommands_executed=false"
    label = {
        "executable_candidate": "Candidate (validated; no execution)",
        "needs_clarification": "Clarify", "refused": "Refuse",
        "local_ai_unavailable": "Local AI unavailable",
        "understanding_failed": "Understanding failed closed",
    }.get(payload["decision"]["status"], "Diagnostic failed closed")
    return (
        label + "\n" + f"request_id: {payload['request_id']}\n"
        f"duplicate: {str(payload['duplicate']).lower()}\n"
        + format_decision_text_payload(payload, show_canonical=False)
        + "\ncommands_executed=false"
    )


def main(argv=None, *, input_fn=input, output_fn=print):
    parser = argparse.ArgumentParser(description="Phone-local understanding; never executes")
    parser.add_argument("--request", help="One instruction; omit for interactive session")
    parser.add_argument("--request-id", help="Explicit diagnostic ID (one-shot mode)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--lab", action="store_true", help="Use Understanding Lab loopback (8769)")
    args = parser.parse_args(argv)
    if args.request_id and args.request is None:
        parser.error("--request-id requires --request")
    session = PhoneUnderstandingSession(lab=args.lab)
    if args.request is not None:
        payload = session.diagnose(args.request_id or uuid4().hex, args.request)
        output_fn(present(payload, as_json=args.json))
        return 0
    output_fn(
        "Phone-local understanding: two fixture lamps only; no physical devices.\n"
        "Enter an instruction, :repeat to replay the last ID without inference, or :quit.\n"
        "commands_executed=false"
    )
    last = None
    while True:
        try:
            request = input_fn("Instruction> ").strip()
        except (EOFError, KeyboardInterrupt):
            return 0
        if request == ":quit":
            return 0
        if request == ":repeat":
            if last is None:
                output_fn("No previous diagnostic. commands_executed=false")
                continue
            request_id, request = last
        else:
            request_id = uuid4().hex
            last = (request_id, request)
        output_fn(present(session.diagnose(request_id, request), as_json=args.json))


if __name__ == "__main__":
    raise SystemExit(main())
