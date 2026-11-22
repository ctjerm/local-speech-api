import pytest

from speech_api.server import server_config


def test_http_and_https_share_configuration_without_redirecting_existing_clients():
    plain = server_config(7860, 8443, None, None)
    assert plain.bind == ["0.0.0.0:7860"]
    assert not plain.insecure_bind
    secured = server_config(7860, 8443, "server.pem", "key.pem")
    assert secured.bind == ["0.0.0.0:8443"]
    assert secured.insecure_bind == ["0.0.0.0:7860"]
    assert secured.certfile == "server.pem"


@pytest.mark.parametrize("port,certificate,key", [(8443, "cert", "key"), (7860, "cert", None)])
def test_invalid_listener_configuration_fails_before_loading_models(port, certificate, key):
    with pytest.raises(ValueError):
        server_config(port, 8443, certificate, key)
