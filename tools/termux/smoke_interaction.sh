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
# The bearer token is read from a file and is never printed. This script only
# issues HTTP requests; it does not modify the device.

set -euo pipefail

BASE="${JARVISOS_BASE:-http://127.0.0.1:8765}"
TOKEN_FILE="${JARVISOS_TOKEN_FILE:-$HOME/.jarvisos/interaction.token}"

if [ ! -s "$TOKEN_FILE" ]; then
  echo "error: token file '$TOKEN_FILE' not found or empty." >&2
  echo "create it with: python tools/termux/make_interaction_token.py" >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "error: curl not found. Run tools/termux/bootstrap_termux.sh first." >&2
  exit 1
fi

TOKEN="$(cat "$TOKEN_FILE")"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

passed=0
failed=0

check_status() {
  # name expected actual
  if [ "$2" = "$3" ]; then
    echo "PASS: $1 (HTTP $3)"
    passed=$((passed + 1))
  else
    echo "FAIL: $1 (expected HTTP $2, got $3)"
    failed=$((failed + 1))
  fi
}

echo "== 1. health =="
status="$(curl -s -o "$TMP_DIR/health.json" -w '%{http_code}' "$BASE/api/v1/health")"
check_status "health returns 200" 200 "$status"

echo "== 2. interaction without token =="
status="$(curl -s -o "$TMP_DIR/noauth.json" -w '%{http_code}' \
  -X POST "$BASE/api/v1/interactions" \
  -H 'Content-Type: application/json' \
  --data '{"message":"hola"}')"
check_status "missing bearer token rejected (401)" 401 "$status"

echo "== 3. interaction with wrong token =="
status="$(curl -s -o "$TMP_DIR/badauth.json" -w '%{http_code}' \
  -X POST "$BASE/api/v1/interactions" \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer invalid-token-000000000000' \
  --data '{"message":"hola"}')"
check_status "wrong bearer token rejected (401)" 401 "$status"

echo "== 4. pure greeting with valid token =="
status="$(curl -s -o "$TMP_DIR/greet.json" -w '%{http_code}' \
  -X POST "$BASE/api/v1/interactions" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOKEN" \
  --data '{"message":"hola"}')"
check_status "greeting accepted (200)" 200 "$status"
if grep -Eq '"commands_executed" *: *false' "$TMP_DIR/greet.json" \
  && grep -Eq '"type" *: *"conversation"' "$TMP_DIR/greet.json"; then
  echo "PASS: greeting response is conversation with commands_executed=false"
  passed=$((passed + 1))
else
  echo "FAIL: unexpected greeting body:"
  cat "$TMP_DIR/greet.json"
  echo
  failed=$((failed + 1))
fi

echo "== 5. command route disabled in interaction-only mode =="
status="$(curl -s -o "$TMP_DIR/command.json" -w '%{http_code}' \
  -X POST "$BASE/api/v1/commands" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOKEN" \
  --data '{"input":"device read lamp_1 status.read"}')"
check_status "commands route disabled (404)" 404 "$status"

echo "----"
echo "passed=$passed failed=$failed"
[ "$failed" -eq 0 ]
