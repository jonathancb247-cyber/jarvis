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


STARTUP_MESSAGES = {
    CONFIG_NOT_FOUND: "Configuration file was not found.",
    CONFIG_INVALID: "Configuration is invalid.",
    SCHEMA_VERSION_UNSUPPORTED: "Configuration schema version is not supported.",
    DUPLICATE_DEVICE: "Device configuration contains duplicates.",
    INVALID_CAPABILITY: "Device capability configuration is invalid.",
    INVALID_BINDING: "HTTP device binding configuration is invalid.",
    ORPHAN_BINDING: "HTTP device binding references an unknown device.",
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
