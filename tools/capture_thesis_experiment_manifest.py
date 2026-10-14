"""Capture a thesis experiment manifest as JSON for evidence provenance.

This tool is additive thesis evidence tooling. Design boundaries:

- Standard library only. It never imports ``jarvis_core``, Runtime,
  ExecutionGate, Planner, Drivers, the State Store or any MQTT client.
- No network access, no hardware access, no source mutation, no ``state/``
  writes, no commits, no pushes.
- Read-only git probes (``rev-parse``, ``branch``, ``status``) record the
  repository provenance of a physical experiment run.
- Supplied files (profile, harness, evidence, firmware sources) are read ONLY
  to compute SHA-256, byte size and modification time. File contents, profile
  values, broker credentials, Wi-Fi credentials, API keys, passwords and
  tokens are never serialized or printed.
- Environment inspection is limited to configured/unconfigured booleans for
  ``JARVIS_MQTT_HOST``, ``JARVIS_MQTT_PORT`` and ``JARVIS_MQTT_ALLOW_LAN``.
  Their values are never recorded.
- A ``*.local.json`` profile is a legitimate physical-run profile: it is
  hashed like any other profile, never rejected and never embedded.

Usage:

    python tools/capture_thesis_experiment_manifest.py --experiment-id exp-01
    python tools/capture_thesis_experiment_manifest.py --experiment-id exp-01 \
        --profile profiles/mqtt-esp32.example.json \
        --firmware examples/mqtt-led/main/main.c \
        --evidence captures/thesis/exp-01/report.md \
        --out captures/thesis/exp-01/manifest.json

Default output is stdout JSON. With ``--out``, the manifest is written
atomically (temp file in the destination directory, then ``os.replace``).

Recommended run location: ``captures/thesis/<experiment_id>/manifest.json``.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA_VERSION = "1.0"
TOOL_NAME = "capture_thesis_experiment_manifest.py"

REPO_ROOT = Path(__file__).resolve().parents[1]

ENV_FLAG_VARIABLES = (
    "JARVIS_MQTT_HOST",
    "JARVIS_MQTT_PORT",
    "JARVIS_MQTT_ALLOW_LAN",
)


def _utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _display_path(path: Path) -> str:
    """Return a repo-relative path when possible, else the absolute path."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _hash_file(path: Path, errors: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Read file bytes ONLY to compute sha256/size/mtime. Never contents."""
    entry: Dict[str, Any] = {"path": _display_path(path)}
    try:
        stat = path.stat()
    except OSError as exc:
        entry["sha256"] = None
        entry["error"] = type(exc).__name__
        errors.append({"path": entry["path"], "error": type(exc).__name__})
        return entry

    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        entry["sha256"] = None
        entry["error"] = type(exc).__name__
        errors.append({"path": entry["path"], "error": type(exc).__name__})
        return entry

    entry["sha256"] = digest.hexdigest()
    entry["size_bytes"] = stat.st_size
    entry["mtime_utc"] = _dt.datetime.fromtimestamp(
        stat.st_mtime, _dt.timezone.utc
    ).isoformat(timespec="seconds")
    return entry


def _git_probe(args: List[str]) -> Optional[str]:
    """Run one read-only git command. Return stripped stdout or None."""
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    # Preserve leading status characters on the first porcelain line.
    return completed.stdout.rstrip("\r\n")


def _git_section() -> Dict[str, Any]:
    head = _git_probe(["rev-parse", "HEAD"])
    if head is None:
        return {"available": False, "commit": None, "branch": None,
                "dirty": None, "dirty_files": []}

    branch = _git_probe(["branch", "--show-current"])
    status = _git_probe(["status", "--porcelain"]) or ""
    dirty_files: List[str] = []
    for line in status.splitlines():
        if not line.strip():
            continue
        dirty_files.append(line[3:] if len(line) > 3 else line)

    return {
        "available": True,
        "commit": head,
        "branch": branch,
        "dirty": bool(dirty_files),
        "dirty_files": dirty_files,
    }


def _paho_mqtt_version() -> Dict[str, Any]:
    """Discover paho-mqtt version via distribution metadata only.

    ``importlib.metadata`` reads installed package metadata; it does not
    import paho, JarvisOS or any network client.
    """
    try:
        from importlib import metadata as _md
    except ImportError:  # pragma: no cover - stdlib always present on 3.8+
        return {"installed": False, "version": None}
    try:
        version = _md.version("paho-mqtt")
    except _md.PackageNotFoundError:
        return {"installed": False, "version": None}
    except Exception:  # noqa: BLE001 - metadata parsing must never crash capture
        return {"installed": None, "version": None}
    return {"installed": True, "version": version}


def _environment_configuration() -> Dict[str, Dict[str, bool]]:
    """Record configured/unconfigured booleans only. Never variable values."""
    return {
        name: {"configured": bool(os.environ.get(name))}
        for name in ENV_FLAG_VARIABLES
    }


def build_manifest(args: argparse.Namespace) -> Dict[str, Any]:
    errors: List[Dict[str, Any]] = []

    harness_entry = _hash_file(Path(__file__), errors)
    profiles = [_hash_file(Path(p), errors) for p in args.profile or []]
    evidence_files = [_hash_file(Path(p), errors) for p in args.evidence or []]
    firmware_sources = [_hash_file(Path(p), errors) for p in args.firmware or []]

    manifest: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "experiment_id": args.experiment_id,
        "label": args.label,
        "notes": args.notes,
        "captured_at_utc": _utc_now_iso(),
        "git": _git_section(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "os": platform.system(),
        "hostname": socket.gethostname(),
        "harness": harness_entry,
        "profiles": profiles,
        "evidence_files": evidence_files,
        "firmware_sources": firmware_sources,
        "paho_mqtt": _paho_mqtt_version(),
        "environment_configuration": _environment_configuration(),
    }
    if errors:
        manifest["errors"] = errors
    return manifest


def write_manifest_atomic(manifest: Dict[str, Any], out_path: Path) -> None:
    """Write via temp file in the destination directory, then replace."""
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    fd, temp_name = tempfile.mkstemp(
        dir=str(out_path.parent),
        prefix=f".{out_path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, str(out_path))
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Capture a thesis experiment manifest (JSON) describing repository "
            "provenance and file hashes for a physical experiment run. Reads "
            "no secrets into the manifest and performs no network, hardware "
            "or Runtime interaction."
        )
    )
    parser.add_argument("--experiment-id", default=None,
                        help="Experiment identifier, e.g. exp-01.")
    parser.add_argument("--label", default=None,
                        help="Short human-readable experiment label.")
    parser.add_argument("--notes", default=None,
                        help="Free-form notes (avoid secrets).")
    parser.add_argument("--profile", action="append", default=[],
                        metavar="PATH",
                        help="Runtime profile to hash (repeatable). "
                             "*.local.json profiles are allowed and hashed, "
                             "never embedded.")
    parser.add_argument("--evidence", action="append", default=[],
                        metavar="PATH",
                        help="Existing evidence file to hash (repeatable).")
    parser.add_argument("--firmware", action="append", default=[],
                        metavar="PATH",
                        help="Firmware source file to hash (repeatable).")
    parser.add_argument("--out", default=None, metavar="PATH",
                        help="Write manifest atomically to PATH instead of "
                             "stdout. Recommended: "
                             "captures/thesis/<experiment_id>/manifest.json")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    manifest = build_manifest(args)

    if args.out:
        write_manifest_atomic(manifest, Path(args.out))
        print(f"manifest written: {_display_path(Path(args.out))}")
    else:
        print(json.dumps(manifest, indent=2, ensure_ascii=False))

    if manifest.get("errors"):
        for error in manifest["errors"]:
            print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
