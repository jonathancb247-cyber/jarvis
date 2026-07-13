from jarvis_core.cli import run_cli
from jarvis_core.bootstrap import build_runtime, build_runtime_from_config
from jarvis_core.configuration import (
    CONFIG_INVALID,
    CONFIG_NOT_FOUND,
    DUPLICATE_DEVICE,
    INVALID_BINDING,
    INVALID_CAPABILITY,
    ORPHAN_BINDING,
    SCHEMA_VERSION_UNSUPPORTED,
    ConfigurationError,
)
from jarvis_core.state_store import (
    SCHEMA_VERSION_UNSUPPORTED as STATE_SCHEMA_VERSION_UNSUPPORTED,
    STATE_RESTORE_FAILED,
    STATE_SAVE_FAILED,
    STATE_STORE_CORRUPT,
    STATE_STORE_UNAVAILABLE,
    StateStoreError,
)


STARTUP_MESSAGES = {
    CONFIG_NOT_FOUND: "Configuration file was not found.",
    CONFIG_INVALID: "Configuration is invalid.",
    SCHEMA_VERSION_UNSUPPORTED: "Configuration schema version is not supported.",
    DUPLICATE_DEVICE: "Device configuration contains duplicates.",
    INVALID_CAPABILITY: "Device capability configuration is invalid.",
    INVALID_BINDING: "HTTP device binding configuration is invalid.",
    ORPHAN_BINDING: "HTTP device binding references an unknown device.",
}

STATE_STORE_STARTUP_MESSAGES = {
    STATE_STORE_CORRUPT: "State store is corrupt.",
    STATE_SCHEMA_VERSION_UNSUPPORTED: "State store schema version is not supported.",
    STATE_RESTORE_FAILED: "Device state could not be restored.",
    STATE_SAVE_FAILED: "Device state could not be saved.",
    STATE_STORE_UNAVAILABLE: "State store is unavailable.",
}


def main(argv=None):
    args = _parse_args(argv)
    try:
        runtime = (
            build_runtime_from_config(args.config)
            if args.config
            else build_runtime()
        )
    except ConfigurationError as error:
        print(STARTUP_MESSAGES.get(error.code, "Configuration is invalid."))
        return 1
    except StateStoreError as error:
        print(STATE_STORE_STARTUP_MESSAGES.get(error.code, "Device state could not be restored."))
        return 1
    run_cli(runtime)
    return 0


def _parse_args(argv=None):
    import argparse

    parser = argparse.ArgumentParser(prog="python -m jarvis_core")
    parser.add_argument(
        "--config",
        help="Path to an explicit JarvisOS runtime profile JSON file.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
