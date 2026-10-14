#!/usr/bin/env python3
"""Generate the local JarvisOS interaction bearer token.

The token is generated locally with the standard library only, written outside
the repository, and never printed. The default location is
``$HOME/.jarvisos/interaction.token`` (mode 0600) so it can never be committed.

The generated token satisfies every constraint enforced by
``jarvis_core.api.interaction_service.InteractionAuth``: printable ASCII, no
whitespace, and at least 16 characters long.

An existing token is validated before it is reused: a stale or corrupted file is
reported as an error instead of being silently trusted. New tokens are written
through a securely created temporary file and atomically replaced into place.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
import tempfile
from pathlib import Path

MIN_INTERACTION_TOKEN_LENGTH = 16
DEFAULT_TOKEN_PATH = Path.home() / ".jarvisos" / "interaction.token"


def _token_problem(token: str) -> str | None:
    """Return a reason string when the token is unusable, else ``None``."""
    if not token:
        return "empty"
    if len(token) < MIN_INTERACTION_TOKEN_LENGTH:
        return f"shorter than {MIN_INTERACTION_TOKEN_LENGTH} characters"
    if not token.isascii() or not token.isprintable():
        return "not printable ASCII"
    if any(character.isspace() for character in token):
        return "contains whitespace"
    return None


def _chmod_best_effort(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        # Some filesystems do not support POSIX permissions; the file still
        # lives outside the repository and is never logged.
        pass


def _token_path(value: str) -> Path:
    return Path(value).expanduser()


def _write_token_atomically(path: Path, token: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=path.name + ".",
        suffix=".tmp",
    )
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as handle:
            handle.write(token)
            handle.flush()
            os.fsync(handle.fileno())
        _chmod_best_effort(Path(temporary_name), 0o600)
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="make_interaction_token.py",
        description=(
            "Create the local JarvisOS interaction bearer token outside the "
            "repository. The token value is never printed."
        ),
    )
    parser.add_argument(
        "--path",
        default=str(DEFAULT_TOKEN_PATH),
        help="Token file path (default: ~/.jarvisos/interaction.token).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing token file.",
    )
    args = parser.parse_args(argv)

    path = _token_path(args.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _chmod_best_effort(path.parent, 0o700)

    if path.exists() and not args.force:
        try:
            existing = path.read_text(encoding="ascii").strip()
        except (OSError, UnicodeDecodeError):
            existing = ""
        problem = _token_problem(existing)
        if problem is not None:
            print(
                f"error: existing token at {path} is unusable ({problem}).",
                file=sys.stderr,
            )
            print("re-run with --force to replace it.", file=sys.stderr)
            return 1
        print(f"existing token at {path} is valid; leaving it unchanged")
        print("use --force to rotate it")
        return 0

    token = secrets.token_urlsafe(32)
    problem = _token_problem(token)
    if problem is not None:
        # Defence in depth: never write a token that the endpoint would reject.
        print(f"error: generated token is unusable ({problem}).", file=sys.stderr)
        return 1

    _write_token_atomically(path, token)

    print(f"wrote interaction token to {path} (length={len(token)})")
    print("the token value is intentionally not printed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
