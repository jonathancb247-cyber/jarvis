#!/usr/bin/env bash
#
# Launch the local, authenticated, strictly non-executing JarvisOS interaction
# endpoint on the Android device.
#
# The bearer token is read from a file outside the repository and exported under
# an environment variable name only: the token value never appears on a command
# line and is never echoed. The endpoint is forced to loopback and the command
# execution route is disabled (interaction-only mode). This script does not
# modify the device, install apps or expose any LAN/public listener.

set -euo pipefail
umask 077

TOKEN_FILE="${JARVISOS_TOKEN_FILE:-$HOME/.jarvisos/interaction.token}"
PROFILE="${JARVISOS_PROFILE:-profiles/android-termux.local.json}"
MODEL="${JARVISOS_MODEL:-}"
TOKEN_ENV="${JARVISOS_TOKEN_ENV:-JARVIS_API_INTERACTION_TOKEN}"
BIND_HOST="${JARVISOS_HOST:-127.0.0.1}"
BIND_PORT="${JARVISOS_PORT:-8765}"
PROVIDER_HOST="${JARVISOS_PROVIDER_HOST:-127.0.0.1}"
PROVIDER_PORT="${JARVISOS_PROVIDER_PORT:-8767}"

case "$BIND_HOST" in
  127.0.0.1 | localhost | ::1) ;;
  *)
    echo "error: refusing to bind the interaction endpoint to non-loopback host '$BIND_HOST'." >&2
    exit 1
    ;;
esac

if [ ! -f "$PROFILE" ]; then
  echo "error: profile '$PROFILE' not found." >&2
  echo "create it with: cp profiles/android-termux.example.json $PROFILE" >&2
  exit 1
fi

if [ ! -s "$TOKEN_FILE" ]; then
  echo "error: token file '$TOKEN_FILE' not found or empty." >&2
  echo "create it with: python tools/termux/make_interaction_token.py" >&2
  exit 1
fi

# Enforce private token file permissions where POSIX permissions apply.
case "$(uname -s 2>/dev/null || echo unknown)" in
  MINGW* | MSYS* | CYGWIN*) ;;
  *)
    if command -v stat >/dev/null 2>&1; then
      token_mode="$(stat -c '%a' "$TOKEN_FILE" 2>/dev/null || true)"
      case "$token_mode" in
        '' | *[!0-7]*) ;;
        *)
          if [ "$(( 8#$token_mode & 077 ))" -ne 0 ]; then
            echo "error: token file '$TOKEN_FILE' is readable by group/others (mode $token_mode)." >&2
            echo "fix with: chmod 600 '$TOKEN_FILE'" >&2
            exit 1
          fi
          ;;
      esac
    fi
    ;;
esac

if [ -z "$MODEL" ]; then
  echo "error: set JARVISOS_MODEL to the local understanding model id." >&2
  echo "the interaction endpoint requires a model id to start (fail closed)." >&2
  exit 1
fi

# Export the token under its environment variable name; the value is never
# passed as an argument and never printed.
export "$TOKEN_ENV=$(cat "$TOKEN_FILE")"

exec python -m jarvis_core.api \
  --config "$PROFILE" \
  --host "$BIND_HOST" \
  --port "$BIND_PORT" \
  --interaction-only \
  --interaction-token-env "$TOKEN_ENV" \
  --interaction-provider-model "$MODEL" \
  --interaction-provider-host "$PROVIDER_HOST" \
  --interaction-provider-port "$PROVIDER_PORT"
