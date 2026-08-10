"""Secure TLS context helpers for optional AI provider transports."""

import platform
import ssl


def create_provider_ssl_context():
    """Create a verified TLS client context for provider HTTPS calls."""
    if platform.system() == "Windows":
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    return ssl.create_default_context()
