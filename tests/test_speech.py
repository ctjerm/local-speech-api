import asyncio

import pytest
from starlette.requests import ClientDisconnect
from test_api import FakeSpeech, client

from speech_api.speech.contracts import SpeechAudio, SpeechCapabilities, SpeechError, SpeechHealth
from speech_api.speech.routes import AudioResponse


@pytest.mark.parametrize("rate,direction", [(16000, False), (48000, True)])
def test_provider_swap_keeps_the_same_request_and_audio_contract(rate, direction):
    provider = FakeSpeech(rate)
    provider.capabilities = SpeechCapabilities(voice_direction=direction)
    with client(speech=provider) as api:
        result = api.post("/v1/audio/speech", data={"text": " Hello ", "instruction": " "})
        assert result.status_code == 200
        assert result.content == b"\x01\x00\x02\x00"
        assert result.headers["x-sample-rate"] == str(rate)
        assert result.headers["x-sample-format"] == "s16le"
        assert result.headers["x-channels"] == "1"
        assert provider.requests[0].text == "Hello"
        assert provider.requests[0].provider_options == {}
        assert provider.closed == 1
        assert api.get("/v1/audio/speech/capabilities").json() == {
            "voice_direction": direction,
            "reference_audio": False,
            "languages": [],
        }
        assert api.get("/health").json()["sample_rate"] == rate
        schema = api.get("/openapi.json").json()
        body = schema["paths"]["/v1/audio/speech"]["post"]["requestBody"]
        ref = body["content"]["multipart/form-data"]["schema"]["$ref"].split("/")[-1]
        assert set(schema["components"]["schemas"][ref]["properties"]) == {
            "text",
            "instruction",
            "ref_audio",
            "ref_text",
        }


def test_invalid_or_unsupported_requests_never_reach_provider():
    provider = FakeSpeech()
    provider.capabilities = SpeechCapabilities()
    with client(speech=provider) as api:
        assert api.post("/v1/audio/speech").status_code == 422
        assert api.post("/v1/audio/speech", data={"text": " "}).status_code == 422
        assert (
            api.post("/v1/audio/speech", data={"text": "Hi", "instruction": "calm"}).status_code
            == 400
        )
        assert (
            api.post("/v1/audio/speech", data={"text": "Hi", "ref_text": "hi"}).status_code == 400
        )
        assert (
            api.post(
                "/v1/audio/speech",
                data={"text": "Hi", "ref_text": "hi"},
                files={"ref_audio": ("ref.wav", b"audio")},
            ).status_code
            == 400
        )
    assert not provider.requests


@pytest.mark.parametrize(
    "kind,status",
    [
        ("invalid", 400),
        ("validation", 422),
        ("busy", 409),
        ("too_large", 413),
        ("unavailable", 502),
        ("timeout", 504),
    ],
)
def test_provider_errors_have_consistent_http_statuses(kind, status):
    class FailingSpeech(FakeSpeech):
        async def generate(self, request):
            raise SpeechError(kind, "Public error")

    with client(speech=FailingSpeech()) as api:
        result = api.post("/v1/audio/speech", data={"text": "Hello"})
        assert result.status_code == status
        assert result.json()["detail"] == "Public error"


def test_failed_provider_is_reported_without_exposing_internal_error():
    class FailingSpeech(FakeSpeech):
        async def generate(self, request):
            raise RuntimeError("private provider failure")

        async def health(self):
            return SpeechHealth(False)

    with client(speech=FailingSpeech()) as api:
        assert api.get("/health").status_code == 503
        result = api.post("/v1/audio/speech", data={"text": "Hello"})
        assert result.status_code == 500
        assert "private provider failure" not in result.text


@pytest.mark.parametrize("failure", ["disconnect", "stream"])
def test_audio_stream_is_closed_when_client_or_provider_fails(failure):
    async def exercise():
        closed = False

        async def chunks():
            yield b"\x01\x00"
            if failure == "stream":
                raise RuntimeError("stream failed")

        async def close():
            nonlocal closed
            await asyncio.sleep(0)
            closed = True

        async def send(message):
            if message["type"] == "http.response.body" and failure == "disconnect":
                raise OSError("disconnected")

        async def receive():
            return {"type": "http.disconnect"}

        response = AudioResponse(SpeechAudio(16000, chunks(), close))
        with pytest.raises((ClientDisconnect, RuntimeError)):
            await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
        assert closed

    asyncio.run(exercise())
