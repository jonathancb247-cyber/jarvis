#!/usr/bin/env bash
#
# Launch the local, authenticated, strictly non-executing JarvisOS interaction
# endpoint on the Android device.
#
# The bearer token is read from a file outside the repository and is never
# echoed. The endpoint binds to loopback only and the command execution route is
# disabled (interaction-only mode). This script does not modify the device,
# install apps or expose any LAN/public listener.

set -euo pipefail

TOKEN_FILE="${JARVISOS_TOKEN_FILE:-$HOME/.jarvisos/interaction.token}"
PROFILE="${JARVISOS_PROFILE:-profiles/android-termux.local.json}"
MODEL="${JARVISOS_MODEL:-}"
TOKEN_ENV="${JARVISOS_TOKEN_ENV:-JARVIS_API_INTERACTION_TOKEN}"
BIND_HOST="${JARVISOS_HOST:-127.0.0.1}"
BIND_PORT="${JARVISOS_PORT:-8765}"
PROVIDER_HOST="${JARVISOS_PROVIDER_HOST:-127.0.0.1}"
PROVIDER_PORT="${JARVISOS_PROVIDER_PORT:-8767}"

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

if [ -z "$MODEL" ]; then
  echo "error: set JARVISOS_MODEL to the local understanding model id." >&2
  echo "the interaction endpoint requires a model id to start (fail closed)." >&2
  exit 1
fi

# Read the token from disk and export it under the API's env var. The value is
# never passed on the command line and never printed.
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
