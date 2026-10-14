#!/usr/bin/env bash
#
# Idempotent Termux bootstrap for running the JarvisOS local interaction
# endpoint on the same Android device as the JarvisOS Companion app.
#
# This script:
#   - installs only the runtime tools the stdlib-only interaction path needs;
#   - never modifies the repository, the device profile or any app;
#   - never installs, updates or removes Android applications;
#   - never prints or stores any secret.
#
# It is safe to run more than once.

set -euo pipefail

case "${PREFIX:-}" in
  *com.termux*) ;;
  *)
    echo "warning: this script is intended to run inside Termux." >&2
    ;;
esac

DATA_DIR="${JARVISOS_HOME:-$HOME/.jarvisos}"
mkdir -p "$DATA_DIR"
# Best-effort private directory; ignored on filesystems that do not support it.
chmod 700 "$DATA_DIR" 2>/dev/null || true

if ! command -v pkg >/dev/null 2>&1; then
  echo "error: 'pkg' not found. Run this script inside Termux." >&2
  exit 1
fi

echo "Installing required Termux packages (idempotent): python git curl"
# 'pkg install -y' is a no-op when the package is already present.
pkg install -y python git curl

python - <<'PY'
import sys

if sys.version_info < (3, 8):
    raise SystemExit("error: Python 3.8 or newer is required by JarvisOS.")
print("python: " + sys.version.split()[0])
PY

echo "Bootstrap complete."
echo "Data directory (outside the repository): $DATA_DIR"
echo "Next: python tools/termux/make_interaction_token.py"
