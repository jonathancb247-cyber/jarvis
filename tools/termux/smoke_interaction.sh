#!/usr/bin/env bash
#
# Read-only HTTP checks for the local JarvisOS interaction endpoint.
#
# Verifies the safe interaction contract against an already-running endpoint:
#   1. GET  /api/v1/health                -> 200
#   2. POST /api/v1/interactions (no auth) -> 401 api_unauthorized
#   3. POST /api/v1/interactions (bad auth) -> 401 api_unauthorized
#   4. POST /api/v1/interactions "hola"    -> 200, commands_executed=false
#   5. POST /api/v1/commands (interaction-only) -> 404 api_route_not_found
#
# Security properties:
#   - the bearer token is only ever read from a file; it is never passed on a
#     command line (curl reads it from a mode-0600 config file) and never printed;
#   - authenticated requests are refused unless the target is loopback;
#   - redirects are never followed (--max-redirs 0);
#   - every request has a connection timeout and a total time budget and fails
#     explicitly when either is exceeded;
#   - temporary files are created under umask 077 and always cleaned up.
#
# This script only issues HTTP requests; it does not modify the device.

set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECKER="$SCRIPT_DIR/check_interaction_response.py"

BASE="${JARVISOS_BASE:-http://127.0.0.1:8765}"
TOKEN_FILE="${JARVISOS_TOKEN_FILE:-$HOME/.jarvisos/interaction.token}"
CONNECT_TIMEOUT="${JARVISOS_CONNECT_TIMEOUT:-3}"
MAX_TIME="${JARVISOS_MAX_TIME:-10}"

# Refuse to send the bearer token anywhere other than loopback.
case "$BASE" in
  http://127.0.0.1 | http://127.0.0.1[:/]* | http://localhost | http://localhost[:/]*) ;;
  *)
    echo "error: refusing to send the bearer token to non-loopback target '$BASE'." >&2
    echo "JARVISOS_BASE must point at 127.0.0.1 or localhost." >&2
    exit 1
    ;;
esac

if [ ! -s "$TOKEN_FILE" ]; then
  echo "error: token file '$TOKEN_FILE' not found or empty." >&2
  echo "create it with: python tools/termux/make_interaction_token.py" >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "error: curl not found. Run tools/termux/bootstrap_termux.sh first." >&2
  exit 1
fi

# Enforce private token file permissions where POSIX permissions apply.
# Windows test hosts (MINGW/MSYS/CYGWIN) do not implement POSIX modes.
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

TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT INT TERM

# Build the Authorization header inside a mode-0600 curl config file so the
# token never appears in any process argument list.
AUTH_CONF="$TMP_DIR/curl_auth.conf"
{
  printf 'header = "Authorization: Bearer '
  tr -d '\r\n' < "$TOKEN_FILE"
  printf '"\n'
} > "$AUTH_CONF"

passed=0
failed=0
CURL_RC=0

http_request() {
  # $1 = output file; remaining args are curl arguments.
  # Writes the HTTP status code to "$TMP_DIR/curl.code" and records curl's exit
  # status in CURL_RC (both in the current shell, never a subshell).
  local out="$1"
  shift
  set +e
  curl -sS \
    --connect-timeout "$CONNECT_TIMEOUT" \
    --max-time "$MAX_TIME" \
    --max-redirs 0 \
    --proto '=http' \
    -o "$out" -w '%{http_code}' "$@" \
    >"$TMP_DIR/curl.code" 2>"$TMP_DIR/curl.err"
  CURL_RC=$?
  set -e
}

expect_status() {
  # $1 = name; $2 = expected code; $3 = actual code
  if [ "$CURL_RC" -ne 0 ]; then
    if [ "$CURL_RC" -eq 28 ]; then
      echo "FAIL: $1 (request timed out: connect<=${CONNECT_TIMEOUT}s total<=${MAX_TIME}s)"
    else
      echo "FAIL: $1 (transport error, curl rc=$CURL_RC)"
    fi
    failed=$((failed + 1))
    return 0
  fi
  if [ "$2" = "$3" ]; then
    echo "PASS: $1 (HTTP $3)"
    passed=$((passed + 1))
  else
    echo "FAIL: $1 (expected HTTP $2, got $3)"
    failed=$((failed + 1))
  fi
}

echo "== 1. health =="
http_request "$TMP_DIR/health.json" "$BASE/api/v1/health"
expect_status "health returns 200" 200 "$(cat "$TMP_DIR/curl.code")"

echo "== 2. interaction without token =="
http_request "$TMP_DIR/noauth.json" \
  -X POST "$BASE/api/v1/interactions" \
  -H 'Content-Type: application/json' \
  --data '{"message":"hola"}'
expect_status "missing bearer token rejected (401)" 401 "$(cat "$TMP_DIR/curl.code")"

echo "== 3. interaction with wrong token =="
http_request "$TMP_DIR/badauth.json" \
  -X POST "$BASE/api/v1/interactions" \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer invalid-token-000000000000' \
  --data '{"message":"hola"}'
expect_status "wrong bearer token rejected (401)" 401 "$(cat "$TMP_DIR/curl.code")"

echo "== 4. pure greeting with valid token =="
http_request "$TMP_DIR/greet.json" \
  -X POST "$BASE/api/v1/interactions" \
  -H 'Content-Type: application/json' \
  -K "$AUTH_CONF" \
  --data '{"message":"hola"}'
expect_status "greeting accepted (200)" 200 "$(cat "$TMP_DIR/curl.code")"
if [ "$CURL_RC" -eq 0 ]; then
  if python "$CHECKER" --file "$TMP_DIR/greet.json" --type conversation --expect-success true; then
    echo "PASS: greeting response passes strict root-level commands_executed=false check"
    passed=$((passed + 1))
  else
    echo "FAIL: greeting response failed strict validation (root commands_executed must be false)"
    failed=$((failed + 1))
  fi
fi

echo "== 5. command route disabled in interaction-only mode =="
http_request "$TMP_DIR/command.json" \
  -X POST "$BASE/api/v1/commands" \
  -H 'Content-Type: application/json' \
  -K "$AUTH_CONF" \
  --data '{"input":"device read lamp_1 status.read"}'
expect_status "commands route disabled (404)" 404 "$(cat "$TMP_DIR/curl.code")"

echo "----"
echo "passed=$passed failed=$failed"
[ "$failed" -eq 0 ]
