#!/usr/bin/env python3
"""Strict validation of a JarvisOS interaction HTTP response.

Only the root object's ``commands_executed`` is authoritative for the
non-execution guarantee: it MUST be the JSON boolean ``false``. In addition,
when the response is asserted to be a conversation (``--type conversation``),
the full documented greeting contract from ``docs/api/ROUTES.md`` is enforced:

    {
      "schema_version": 1,
      "type": "conversation",
      "response_text": "Hola. ¿En qué puedo ayudarte?",
      "commands_executed": false,
      "decision": null,
      "success": true,
      "error": null
    }

So a conversation response is accepted only when:

- ``schema_version`` is the integer ``1`` (``true`` and ``1.0`` are rejected);
- ``type`` is ``"conversation"``;
- ``success`` is the boolean ``true``;
- ``commands_executed`` is the boolean ``false``;
- ``decision`` is ``null`` (missing is rejected);
- ``error`` is ``null`` (missing is rejected);
- ``response_text`` is a non-empty string.

Duplicate keys are rejected in **every** object (root and nested), even when the
last value would otherwise pass, because a duplicate key means the response is
ambiguous.

The checker is intentionally small and dependency-free so the smoke test can
rely on real JSON parsing instead of substring matching. It never prints the
response body (or any key/value from it), so it cannot leak captured content.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


class DuplicateKeyError(ValueError):
    """Raised when a JSON object contains the same key more than once."""


def _reject_duplicate_keys(pairs):
    """``object_pairs_hook`` applied by ``json`` to every JSON object."""
    seen = set()
    for key, _value in pairs:
        if key in seen:
            raise DuplicateKeyError
        seen.add(key)
    return dict(pairs)


def _read_body(path_value: str) -> str:
    if path_value == "-":
        return sys.stdin.read()
    return Path(path_value).read_text(encoding="utf-8")


def _is_strict_int(value) -> bool:
    """True only for a real integer, never for a bool (bool is an int subclass)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_conversation(payload):
    schema_version = payload.get("schema_version")
    if not _is_strict_int(schema_version) or schema_version != 1:
        return "root 'schema_version' is not the integer 1"
    if payload.get("type") != "conversation":
        return "root 'type' is not 'conversation'"
    if payload.get("success") is not True:
        return "root 'success' is not the JSON boolean true"
    if payload.get("decision", "missing") is not None:
        return "root 'decision' is not null"
    if payload.get("error", "missing") is not None:
        return "root 'error' is not null"
    text = payload.get("response_text")
    if not isinstance(text, str) or text == "":
        return "root 'response_text' is not a non-empty string"
    return None


def _validate(payload, expect_type, expect_success):
    if not isinstance(payload, dict):
        return "response root is not a JSON object"
    if "commands_executed" not in payload:
        return "root 'commands_executed' is missing"
    if payload["commands_executed"] is not False:
        return "root 'commands_executed' is not the JSON boolean false"
    if expect_type is not None and payload.get("type") != expect_type:
        return f"root 'type' is not '{expect_type}'"
    if expect_success is not None:
        wanted = expect_success == "true"
        if payload.get("success") is not wanted:
            return f"root 'success' is not {str(wanted).lower()}"
    if expect_type == "conversation":
        return _validate_conversation(payload)
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_interaction_response.py",
        description=(
            "Validate a JarvisOS interaction response: root commands_executed "
            "must be the JSON boolean false, no duplicate keys are allowed and a "
            "'conversation' response must match the documented contract."
        ),
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Path to a captured response body, or '-' to read standard input.",
    )
    parser.add_argument(
        "--type",
        default=None,
        help="Require this root-level 'type' value (for example: conversation).",
    )
    parser.add_argument(
        "--expect-success",
        choices=("true", "false"),
        default=None,
        help="Require this root-level 'success' boolean.",
    )
    args = parser.parse_args(argv)

    try:
        raw = _read_body(args.file)
    except OSError:
        print("invalid: response body could not be read", file=sys.stderr)
        return 1

    try:
        payload = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except DuplicateKeyError:
        # Do not echo the offending key: it is response content.
        print("invalid: response contains a duplicate JSON key", file=sys.stderr)
        return 1
    except json.JSONDecodeError:
        print("invalid: response is not valid JSON", file=sys.stderr)
        return 1

    problem = _validate(payload, args.type, args.expect_success)
    if problem is not None:
        print(f"invalid: {problem}", file=sys.stderr)
        return 1

    if args.type == "conversation":
        print("ok: conversation response matches the documented contract")
    else:
        print("ok: root commands_executed is the JSON boolean false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
