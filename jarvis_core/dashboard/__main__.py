"""Process entry point for the optional local Dashboard."""

import argparse
import signal

from jarvis_core.api.adapter import RuntimeApiAdapter
from jarvis_core.api.projections import ApiProjectionBuilder
from jarvis_core.api.server import DEFAULT_HOST, DEFAULT_PORT
from jarvis_core.bootstrap import build_runtime_from_config
from jarvis_core.configuration import ConfigurationError, RuntimeConfigurationLoader
from jarvis_core.dashboard.server import make_dashboard_server
from jarvis_core.state_store import StateStoreError


STARTUP_MESSAGES = {
    "invalid_host": "Dashboard host must be 127.0.0.1 or localhost.",
    "port_unavailable": "Dashboard port is unavailable.",
    "runtime_construction_failed": "Dashboard could not be started.",
}


def main(argv=None):
    _install_signal_handlers()
    args = _parse_args(argv)
    try:
        loader = RuntimeConfigurationLoader()
        profile = loader.load(args.config)
        runtime = build_runtime_from_config(args.config)
        adapter = RuntimeApiAdapter(
            runtime,
            ApiProjectionBuilder(
                runtime.context.device_registry,
                profile_name=profile.name,
                persistence_enabled=bool(profile.runtime_options.get("state_store_path")),
            ),
        )
        server = make_dashboard_server(adapter, host=args.host, port=args.port)
    except ConfigurationError:
        print("Configuration is invalid.")
        return 1
    except StateStoreError:
        print("Device state could not be restored.")
        return 1
    except ValueError as error:
        print(STARTUP_MESSAGES.get(str(error), "Dashboard could not be started."))
        return 1
    except OSError:
        print(STARTUP_MESSAGES["port_unavailable"])
        return 1

    host, port = server.server_address
    print(f"JarvisOS Dashboard listening on http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        adapter.shutdown()
    return 0


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="python -m jarvis_core.dashboard")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to an explicit JarvisOS runtime profile JSON file.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Localhost bind address.")
    parser.add_argument("--port", default=DEFAULT_PORT, type=int, help="Local Dashboard port.")
    return parser.parse_args(argv)


def _install_signal_handlers():
    def interrupt(signum, frame):
        raise KeyboardInterrupt

    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, interrupt)


if __name__ == "__main__":
    raise SystemExit(main())

