"""HTTP and optional HTTPS listeners share one application and model instance."""

from hypercorn.config import Config


def server_config(port: int, https_port: int, certificate: str | None, key: str | None):
    if bool(certificate) != bool(key):
        raise ValueError("HTTPS requires both a certificate and its private key.")
    config = Config()
    config.bind = [f"0.0.0.0:{port}"]
    config.accesslog = "-"
    if certificate:
        if port == https_port:
            raise ValueError("HTTP and HTTPS ports must differ.")
        config.bind = [f"0.0.0.0:{https_port}"]
        config.insecure_bind = [f"0.0.0.0:{port}"]
        config.certfile = certificate
        config.keyfile = key
    return config
