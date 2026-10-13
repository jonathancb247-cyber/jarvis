"""Process entry point for the optional localhost Runtime API."""

import argparse
import os
import signal

from jarvis_core.ai.gemma_android_bridge import (
    DEFAULT_ANDROID_BRIDGE_PORT,
    GemmaAndroidBridgeConfig,
    GemmaAndroidBridgeTransport,
)
from jarvis_core.ai.gemma_understanding import (
    GemmaLocalUnderstandingProvider,
    GemmaUnderstandingProviderConfig,
)
from jarvis_core.api.adapter import RuntimeApiAdapter
from jarvis_core.api.interaction_service import (
    DEFAULT_MAX_CONCURRENCY,
    InteractionAuth,
    LocalInteractionService,
)
from jarvis_core.api.projections import ApiProjectionBuilder
from jarvis_core.api.server import DEFAULT_HOST, DEFAULT_PORT, make_server
from jarvis_core.bootstrap import build_runtime_from_config
from jarvis_core.configuration import ConfigurationError, RuntimeConfigurationLoader
from jarvis_core.state_store import StateStoreError


DEFAULT_INTERACTION_TOKEN_ENV = "JARVIS_API_INTERACTION_TOKEN"
INTERACTION_PROVIDER_ID = "gemma-local-understanding"

STARTUP_MESSAGES = {
    "invalid_host": "Runtime API host must be 127.0.0.1 or localhost.",
    "port_unavailable": "Runtime API port is unavailable.",
    "runtime_construction_failed": "Runtime API could not be started.",
    "interaction_token_missing": (
        "Interaction mode requires the bearer token environment variable to be set."
    ),
    "interaction_model_required": (
        "Interaction mode requires --interaction-provider-model."
    ),
    "interaction_provider_invalid": (
        "Interaction provider configuration is invalid."
    ),
}


def main(argv=None):
    _install_signal_handlers()
    args = _parse_args(argv)
    try:
        config_loader = RuntimeConfigurationLoader()
        profile = config_loader.load(args.config)
        runtime = build_runtime_from_config(args.config)
        adapter = _build_adapter(runtime, profile, args)
        server = make_server(adapter, host=args.host, port=args.port)
    except ConfigurationError:
        print("Configuration is invalid.")
        return 1
    except StateStoreError:
        print("Device state could not be restored.")
        return 1
    except ValueError as error:
        print(STARTUP_MESSAGES.get(str(error), "Runtime API could not be started."))
        return 1
    except OSError:
        print(STARTUP_MESSAGES["port_unavailable"])
        return 1

    host, port = server.server_address
    print(f"JarvisOS Runtime API listening on http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        adapter.shutdown()
    return 0


def _build_adapter(runtime, profile, args):
    projection_builder = ApiProjectionBuilder(
        runtime.context.device_registry,
        profile_name=profile.name,
        persistence_enabled=bool(profile.runtime_options.get("state_store_path")),
    )
    if not args.interaction_only:
        return RuntimeApiAdapter(runtime, projection_builder)
    interaction_service, interaction_auth = _build_interaction_boundary(
        runtime.context.device_registry, args
    )
    return RuntimeApiAdapter(
        runtime,
        projection_builder,
        interaction_service=interaction_service,
        interaction_auth=interaction_auth,
        interaction_only=True,
    )


def _build_interaction_boundary(device_registry, args):
    token = os.environ.get(args.interaction_token_env, "")
    if not token.strip():
        raise ValueError("interaction_token_missing")
    if not args.interaction_provider_model:
        raise ValueError("interaction_model_required")
    try:
        provider_config = GemmaUnderstandingProviderConfig(
            model=args.interaction_provider_model
        )
        transport = GemmaAndroidBridgeTransport(
            GemmaAndroidBridgeConfig(
                host=args.interaction_provider_host,
                port=args.interaction_provider_port,
            )
        )
        service = LocalInteractionService(
            device_registry,
            GemmaLocalUnderstandingProvider(provider_config, transport=transport),
            provider_id=INTERACTION_PROVIDER_ID,
            model_id=provider_config.model,
            max_concurrency=args.interaction_max_concurrency,
        )
        auth = InteractionAuth(token)
    except ValueError as error:
        raise ValueError("interaction_provider_invalid") from error
    return service, auth


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="python -m jarvis_core.api")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to an explicit JarvisOS runtime profile JSON file.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Localhost bind address.")
    parser.add_argument("--port", default=DEFAULT_PORT, type=int, help="Local API port.")
    parser.add_argument(
        "--interaction-only",
        action="store_true",
        help="Expose only the authenticated, non-executing interaction endpoint.",
    )
    parser.add_argument(
        "--interaction-token-env",
        default=DEFAULT_INTERACTION_TOKEN_ENV,
        help="Environment variable holding the interaction bearer token.",
    )
    parser.add_argument(
        "--interaction-provider-model",
        default="",
        help="Local Gemma understanding model identifier.",
    )
    parser.add_argument(
        "--interaction-provider-host",
        default=DEFAULT_HOST,
        help="Local Gemma Android bridge host (localhost/private only).",
    )
    parser.add_argument(
        "--interaction-provider-port",
        default=DEFAULT_ANDROID_BRIDGE_PORT,
        type=int,
        help="Local Gemma Android bridge port.",
    )
    parser.add_argument(
        "--interaction-max-concurrency",
        default=DEFAULT_MAX_CONCURRENCY,
        type=int,
        help="Bounded number of concurrent local interaction turns.",
    )
    return parser.parse_args(argv)


def _install_signal_handlers():
    def interrupt(signum, frame):
        raise KeyboardInterrupt

    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, interrupt)


if __name__ == "__main__":
    raise SystemExit(main())
