from pathlib import Path

from test_api import client

from speech_api.website import mount_website


def test_website_and_assets_share_the_api_without_replacing_api_routes():
    api = client()
    mount_website(api.app, Path(__file__).resolve().parents[1] / "web")
    with api:
        page = api.get("/")
        assert page.status_code == 200
        assert "text/html" in page.headers["content-type"]
        assert "Voice room" in page.text
        for asset in (
            "styles.css",
            "app.js",
            "api.js",
            "audio.js",
            "recording/controls.js",
            "recording/recorder.js",
            "recording/pcm-worklet.js",
            "recording/setup.html",
        ):
            assert api.get(f"/assets/{asset}").status_code == 200
        assert api.get("/health").status_code == 200
        assert "/v1/audio/transcriptions" in api.get("/openapi.json").json()["paths"]
        assert "/" not in api.get("/openapi.json").json()["paths"]


def test_https_setup_exposes_only_the_public_certificate(tmp_path):
    certificate = tmp_path / "ca.cer"
    certificate.write_bytes(b"public certificate")
    api = client()
    mount_website(
        api.app,
        Path(__file__).resolve().parents[1] / "web",
        https_port=8443,
        ca_certificate=certificate,
    )
    with api:
        assert api.get("/site-config").json()["https_port"] == 8443
        assert len(api.get("/site-config").json()["ca_sha256"]) == 64
        assert api.get("/setup/local-ca.cer").content == b"public certificate"
        assert api.get("/setup/server-key.pem").status_code == 404
