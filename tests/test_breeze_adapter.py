from contextlib import asynccontextmanager, contextmanager
from urllib.parse import parse_qs

import httpx
import pytest
from test_api import client

from speech_api.speech.breeze import BreezeSpeechGenerator
from speech_api.speech.breeze_compat import mount_breeze_compat
from speech_api.speech.breeze_config import BreezeConfig


class Body(httpx.AsyncByteStream):
    def __init__(self, content=b"\x01\x00\x02\x00"):
        self.content = content
        self.closed = False

    async def __aiter__(self):
        yield self.content[:2]
        yield self.content[2:]

    async def aclose(self):
        self.closed = True


def upstream(request):
    if request.url.path == "/health":
        return httpx.Response(200, json={"status": "ok", "sample_rate": 24000})
    return httpx.Response(
        200,
        stream=Body(),
        headers={
            "x-sample-rate": "24000",
            "x-sample-format": "s16le",
        },
    )


@contextmanager
def breeze_client(handler=upstream, compatibility=False, config=None):
    worker = httpx.AsyncClient(base_url="http://worker", transport=httpx.MockTransport(handler))

    @asynccontextmanager
    async def lifespan(app):
        async with worker:
            if compatibility:
                await mount_breeze_compat(app, worker)
            yield

    with client(speech=BreezeSpeechGenerator(worker, config), lifespan=lifespan) as api:
        yield api


@pytest.mark.parametrize("options", [
    {"seed": "-1"}, {"seed": str(2**32)}, {"seed": "1.5"}, {"seed": "oops"},
    {"cfg_scale": "0"}, {"cfg_scale": "-1"}, {"cfg_scale": "NaN"},
    {"cfg_scale": "inf"}, {"cfg_scale": "oops"}, {"cfg_sacle": "4"},
])
def test_invalid_overrides_never_reach_worker_and_next_request_succeeds(options):
    calls = []

    def handler(request):
        calls.append(request)
        return upstream(request)

    with breeze_client(handler) as api:
        response = api.post("/v1/audio/speech", data={"text": "Hello", **options})
        assert response.status_code == 422
        assert next(iter(options)) in response.json()["detail"]
        assert calls == []
        assert api.post("/v1/audio/speech", data={"text": "Hello"}).status_code == 200
        assert len(calls) == 1


def test_validated_configuration_is_used_and_request_override_still_wins():
    calls = []

    def handler(request):
        calls.append(parse_qs(request.content.decode(), keep_blank_values=True))
        return upstream(request)

    config = BreezeConfig(plain_cfg_scale=2.5, instructed_cfg_scale=3, seed=0)
    with breeze_client(handler, config=config) as api:
        assert api.post("/v1/audio/speech", data={"text": "Hello"}).status_code == 200
        assert api.post(
            "/v1/audio/speech", data={"text": "Hello", "instruction": "calm"}
        ).status_code == 200
        assert api.post(
            "/v1/audio/speech", data={"text": "Hello", "cfg_scale": "1.25", "seed": str(2**32 - 1)}
        ).status_code == 200
    assert [(c["cfg_scale"], c["seed"]) for c in calls] == [
        (["2.5"], ["0"]), (["3"], ["0"]), (["1.25"], [str(2**32 - 1)]),
    ]


@pytest.mark.parametrize("instruction,scale", [("", "1"), (" calm ", "4"), ("   ", "1")])
def test_default_parameters_are_owned_by_adapter(instruction, scale):
    def handler(request):
        assert parse_qs(request.content.decode(), keep_blank_values=True) == {
            "text": ["Hello"],
            "instruction": [instruction.strip()],
            "cfg_scale": [scale],
            "seed": ["42"],
        }
        return upstream(request)

    with breeze_client(handler) as api:
        result = api.post("/v1/audio/speech", data={"text": "Hello", "instruction": instruction})
        assert result.status_code == 200
        assert result.content == b"\x01\x00\x02\x00"


def test_existing_overrides_and_reference_upload_survive_translation():
    def handler(request):
        content = request.content
        for value in (
            b'name="cfg_scale"\r\n\r\n2',
            b'name="seed"\r\n\r\n9',
            b'name="ref_text"\r\n\r\nReference',
            b'filename="ref.wav"',
            b"reference bytes",
        ):
            assert value in content
        return upstream(request)

    with breeze_client(handler) as api:
        result = api.post(
            "/v1/audio/speech",
            data={
                "text": "Hello",
                "cfg_scale": "2",
                "seed": "9",
                "ref_text": "Reference",
            },
            files={"ref_audio": ("ref.wav", b"reference bytes", "audio/wav")},
        )
        assert result.status_code == 200
        assert api.post("/v1/audio/speech", data={"text": "Hi", "unknown": "1"}).status_code == 422


@pytest.mark.parametrize("status", [200, 400, 409, 422, 500])
def test_worker_stream_is_closed_after_success_or_error(status):
    body = Body()

    def handler(request):
        return httpx.Response(
            status,
            stream=body,
            headers={
                "x-sample-rate": "24000",
                "x-sample-format": "s16le",
            },
        )

    with breeze_client(handler) as api:
        result = api.post("/v1/audio/speech", data={"text": "Hello"})
        assert result.status_code == (502 if status == 500 else status)
        assert body.closed


@pytest.mark.parametrize("headers", [{}, {"x-sample-rate": "24000", "x-sample-format": "float32"}])
def test_invalid_audio_metadata_is_rejected_and_closed(headers):
    body = Body()
    with breeze_client(lambda request: httpx.Response(200, stream=body, headers=headers)) as api:
        assert api.post("/v1/audio/speech", data={"text": "Hello"}).status_code == 502
        assert body.closed


@pytest.mark.parametrize("exception,status", [(httpx.ConnectError, 502), (httpx.ReadTimeout, 504)])
def test_unavailable_worker_has_consistent_errors(exception, status):
    def handler(request):
        raise exception("private connection details")

    with breeze_client(handler) as api:
        assert api.get("/health").status_code == 503
        result = api.post("/v1/audio/speech", data={"text": "Hello"})
        assert result.status_code == status
        assert "private connection details" not in result.text


@pytest.mark.parametrize("exception,status", [(httpx.ReadError, 502), (httpx.ReadTimeout, 504)])
def test_failure_while_reading_worker_error_closes_response(exception, status):
    class BrokenBody(Body):
        async def __aiter__(self):
            yield b""
            raise exception("error response interrupted")

    body = BrokenBody()
    with breeze_client(lambda request: httpx.Response(409, stream=body)) as api:
        result = api.post("/v1/audio/speech", data={"text": "Hello"})
        assert result.status_code == status
        assert body.closed


def test_compatibility_routes_do_not_replace_stable_speech_schema():
    def handler(request):
        if request.url.path == "/openapi.json":
            return httpx.Response(
                200,
                json={
                    "paths": {
                        "/v1/model": {"get": {"responses": {"200": {"description": "model"}}}},
                        "/v1/audio/speech/batch": {
                            "post": {"responses": {"200": {"description": "batch"}}}
                        },
                    }
                },
            )
        return httpx.Response(200, stream=Body(request.content or b"model"))

    with breeze_client(handler, compatibility=True) as api:
        assert api.get("/v1/model").content == b"model"
        assert (
            api.post("/v1/audio/speech/batch", data={"texts": '["hi"]'}).content
            == b"texts=%5B%22hi%22%5D"
        )
        paths = api.get("/openapi.json").json()["paths"]
        assert paths["/v1/audio/speech"]["post"]["operationId"].startswith("generate_speech")
        assert "/v1/model" in paths and "/v1/audio/speech/batch" in paths
