import io
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from speech_api.app import create_app
from speech_api.speech.contracts import SpeechAudio, SpeechCapabilities, SpeechHealth
from speech_api.transcription.contracts import (
    TranscriptionCapabilities,
    TranscriptionHealth,
    TranscriptionResult,
)


class FakeTranscriber:
    model_id = "test-model"
    sample_rate = 16000
    capabilities = TranscriptionCapabilities()

    def transcribe(self, samples):
        return TranscriptionResult("Hello from the API.")

    async def health(self):
        return TranscriptionHealth(True)


def audio_file():
    data = io.BytesIO()
    sf.write(data, np.zeros(16000), 16000, format="WAV")
    return {"file": ("audio.wav", data.getvalue(), "audio/wav")}


class FakeSpeech:
    capabilities = SpeechCapabilities(voice_direction=True, reference_audio=True)

    def __init__(self, sample_rate=24000):
        self.sample_rate = sample_rate
        self.requests = []
        self.closed = 0

    async def generate(self, request):
        self.requests.append(request)

        async def chunks():
            yield b"\x01\x00"
            yield b"\x02\x00"

        async def close():
            self.closed += 1

        return SpeechAudio(self.sample_rate, chunks(), close)

    async def health(self):
        return SpeechHealth(True, self.sample_rate)


def client(backend=None, speech=None, lifespan=None):
    return TestClient(
        create_app(backend or FakeTranscriber(), speech or FakeSpeech(), lifespan=lifespan)
    )


def test_transcription_and_unified_docs():
    with client() as api:
        response = api.post("/v1/audio/transcriptions", files=audio_file())
        assert response.status_code == 200
        assert response.json() == {
            "text": "Hello from the API.",
            "model": "test-model",
            "duration": 1.0,
        }
        paths = api.get("/openapi.json").json()["paths"]
        assert "/v1/audio/speech" in paths and "/v1/audio/transcriptions" in paths
        assert api.get("/health").json()["sample_rate"] == 24000


def test_invalid_upload_and_missing_file():
    with client() as api:
        assert api.post("/v1/audio/transcriptions").status_code == 422
        assert (
            api.post("/v1/audio/transcriptions", files={"file": ("bad.wav", b"junk")}).status_code
            == 400
        )
        assert api.post("/v1/audio/transcriptions", files=audio_file()).status_code == 200


@pytest.mark.parametrize("chunked", [False, True])
def test_large_body_rejected_during_upload(monkeypatch, chunked):
    monkeypatch.setattr("speech_api.transcription.routes.MAX_UPLOAD_BYTES", 128)
    header = b'--test\r\nContent-Disposition: form-data; name="file"; filename="audio.wav"\r\n\r\n'
    chunks = [header, b"a" * 35000, b"b" * 35000, b"\r\n--test--\r\n"]
    with client() as api:
        response = api.post(
            "/v1/audio/transcriptions",
            headers={"Content-Type": "multipart/form-data; boundary=test"},
            content=iter(chunks) if chunked else b"".join(chunks),
        )
        assert response.status_code == 413


def test_busy_request_rejected_and_health_remains_responsive():
    entered, release = threading.Event(), threading.Event()

    class SlowTranscriber(FakeTranscriber):
        def transcribe(self, samples):
            entered.set()
            assert release.wait(10)
            return TranscriptionResult("Done.")

    with client(SlowTranscriber()) as api, ThreadPoolExecutor() as pool:
        first = pool.submit(api.post, "/v1/audio/transcriptions", files=audio_file())
        try:
            assert entered.wait(5)
            assert api.post("/v1/audio/transcriptions", files=audio_file()).status_code == 409
            assert api.get("/health").status_code == 200
        finally:
            release.set()
        assert first.result(timeout=5).status_code == 200
        assert api.post("/v1/audio/transcriptions", files=audio_file()).status_code == 200


def test_failed_inference_releases_slot():
    class FlakyTranscriber(FakeTranscriber):
        calls = 0

        def transcribe(self, samples):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("internal model failure")
            return TranscriptionResult("Recovered.")

    with client(FlakyTranscriber()) as api:
        failed = api.post("/v1/audio/transcriptions", files=audio_file())
        assert failed.status_code == 500
        assert "internal model failure" not in failed.text
        assert api.post("/v1/audio/transcriptions", files=audio_file()).status_code == 200
