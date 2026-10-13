"""Request and command validation for the Runtime API adapter."""

import json
import re

from jarvis_core.ai.contracts import MAX_USER_REQUEST_LENGTH
from jarvis_core.api import errors


MAX_REQUEST_BYTES = 16 * 1024
MAX_COMMAND_LENGTH = 512
MAX_PATH_LENGTH = 512
MAX_DEVICE_ID_LENGTH = 128
MAX_STRING_LENGTH = 512
MAX_JSON_DEPTH = 8
# The interaction endpoint reuses the existing understanding message bound so a
# message accepted here is always preservable by the deterministic boundary.
MAX_INTERACTION_MESSAGE_LENGTH = MAX_USER_REQUEST_LENGTH

COMMAND_FORBIDDEN_PATTERNS = (
    "\n",
    "\r",
    ";",
    "|",
    ">",
    "<",
    "`",
    "$(",
    "&&",
    "||",
    "#",
    "http://",
    "https://",
)

FILESYSTEM_PATTERN = re.compile(r"(^|[\s=])([A-Za-z]:\\|\\\\|/[^/])")
BACKGROUND_PATTERN = re.compile(r"(^|\s)(start|schtasks|at)\s", re.IGNORECASE)
PYTHON_PATTERN = re.compile(r"(^|\s)(python|python3|py)\s", re.IGNORECASE)


class DuplicateKeyError(ValueError):
    pass


def validate_path(path):
    if not isinstance(path, str) or not path.startswith("/"):
        raise errors.request_invalid()
    if len(path) > MAX_PATH_LENGTH:
        raise errors.request_invalid("API path is invalid.")
    if "\x00" in path or "\\" in path:
        raise errors.request_invalid("API path is invalid.")


def validate_device_id(device_id):
    if not isinstance(device_id, str) or not device_id:
        raise errors.request_invalid("Device id is invalid.")
    if len(device_id) > MAX_DEVICE_ID_LENGTH:
        raise errors.request_invalid("Device id is invalid.")
    if any(character in device_id for character in "/\\\x00\r\n"):
        raise errors.request_invalid("Device id is invalid.")


def parse_json_body(body):
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        raise errors.request_invalid("API request must be valid UTF-8.")
    try:
        payload = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except DuplicateKeyError:
        raise errors.request_invalid("JSON object contains duplicate fields.")
    except json.JSONDecodeError:
        raise errors.request_invalid("JSON payload is invalid.")
    _validate_json_depth(payload)
    return payload


def validate_command_payload(payload):
    if not isinstance(payload, dict):
        raise errors.request_invalid("Command payload must be a JSON object.")
    if set(payload.keys()) != {"input"}:
        raise errors.request_invalid("Command payload fields are invalid.")
    command = payload["input"]
    if not isinstance(command, str) or not command.strip():
        raise errors.command_invalid()
    if len(command) > MAX_COMMAND_LENGTH:
        raise errors.command_invalid("API command is too long.")
    validate_command_text(command)
    return command


def validate_interaction_payload(payload):
    """Validate a non-executing interaction payload and return its message.

    The message is preserved literally: it must be a printable, already-trimmed
    string so that ``SafeContextBuilder`` cannot alter it and the deterministic
    boundary receives exactly the validated text. Unknown or missing fields,
    non-strings, empty text and oversized messages are rejected.
    """
    if not isinstance(payload, dict):
        raise errors.request_invalid("Interaction payload must be a JSON object.")
    if set(payload.keys()) != {"message"}:
        raise errors.request_invalid("Interaction payload fields are invalid.")
    message = payload["message"]
    if not isinstance(message, str) or not message.strip():
        raise errors.request_invalid("Interaction message is invalid.")
    if len(message) > MAX_INTERACTION_MESSAGE_LENGTH:
        raise errors.request_invalid("Interaction message is too long.")
    if message != message.strip() or not message.isprintable():
        raise errors.request_invalid("Interaction message cannot be preserved.")
    return message


def validate_command_text(command):
    lowered = command.lower()
    for pattern in COMMAND_FORBIDDEN_PATTERNS:
        if pattern in lowered:
            raise errors.command_invalid()
    if FILESYSTEM_PATTERN.search(command):
        raise errors.command_invalid()
    if BACKGROUND_PATTERN.search(command):
        raise errors.command_invalid()
    if PYTHON_PATTERN.search(command):
        raise errors.command_invalid()
    if len(command.strip().splitlines()) != 1:
        raise errors.command_invalid()


def validate_content_type(content_type):
    if not content_type:
        raise errors.unsupported_media_type()
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        raise errors.unsupported_media_type()


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(key)
        result[key] = value
    return result


def _validate_json_depth(value, depth=0):
    if depth > MAX_JSON_DEPTH:
        raise errors.request_invalid("JSON payload is too deeply nested.")
    if isinstance(value, dict):
        for item in value.values():
            _validate_json_depth(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _validate_json_depth(item, depth + 1)


def safe_string(value, max_length=MAX_STRING_LENGTH):
    if not isinstance(value, str):
        return ""
    return "".join(character for character in value if character.isprintable())[:max_length]
