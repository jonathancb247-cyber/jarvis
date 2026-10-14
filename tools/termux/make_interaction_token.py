#!/usr/bin/env python3
"""Generate the local JarvisOS interaction bearer token.

The token is generated locally with the standard library only, written outside
the repository, and never printed. The default location is
``$HOME/.jarvisos/interaction.token`` (mode 0600) so it can never be committed.

The generated token satisfies every constraint enforced by
``jarvis_core.api.interaction_service.InteractionAuth``: printable ASCII, no
whitespace, and at least 16 characters long.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

MIN_INTERACTION_TOKEN_LENGTH = 16
DEFAULT_TOKEN_PATH = Path.home() / ".jarvisos" / "interaction.token"


def _validate_token(token: str) -> None:
    if len(token) < MIN_INTERACTION_TOKEN_LENGTH:
        raise SystemExit("error: generated token is too short.")
    if not token.isascii() or not token.isprintable():
        raise SystemExit("error: generated token must be printable ASCII.")
    if any(character.isspace() for character in token):
        raise SystemExit("error: generated token must not contain whitespace.")


def _chmod_best_effort(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        # Some filesystems do not support POSIX permissions; the file still
        # lives outside the repository and is never logged.
        pass


def _token_path(value: str) -> Path:
    return Path(value).expanduser()


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
        print(f"token already exists at {path} (use --force to replace)")
        return 0

    token = secrets.token_urlsafe(32)
    _validate_token(token)

    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(token, encoding="ascii")
    _chmod_best_effort(temporary, 0o600)
    os.replace(temporary, path)

    print(f"wrote interaction token to {path} (length={len(token)})")
    print("the token value is intentionally not printed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
