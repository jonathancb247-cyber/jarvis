#!/usr/bin/env python3
"""Strict, root-level validation of a JarvisOS interaction HTTP response.

Only the root object's ``commands_executed`` is authoritative. It MUST be the
JSON boolean ``false``:

- a nested ``commands_executed: false`` (for example inside ``decision``) does
  not satisfy the check;
- a root ``true``, a missing field, a string (``"false"``), a number (``0``) or
  malformed JSON are all rejected.

The checker is intentionally small and dependency-free so the smoke test can
rely on real JSON parsing instead of substring matching. It never prints the
response body, so it cannot leak captured content into logs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _read_body(path_value: str) -> str:
    if path_value == "-":
        return sys.stdin.read()
    return Path(path_value).read_text(encoding="utf-8")


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
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_interaction_response.py",
        description=(
            "Validate that a JarvisOS interaction response has root-level "
            "commands_executed === false."
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
        payload = json.loads(raw)
    except json.JSONDecodeError:
        print("invalid: response is not valid JSON", file=sys.stderr)
        return 1

    problem = _validate(payload, args.type, args.expect_success)
    if problem is not None:
        print(f"invalid: {problem}", file=sys.stderr)
        return 1

    print("ok: root commands_executed is the JSON boolean false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
