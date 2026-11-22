import io

import numpy as np
import pytest
import soundfile as sf
from test_api import FakeTranscriber, audio_file, client

from speech_api.transcription.contracts import (
    TranscriptionCapabilities,
    TranscriptionError,
    TranscriptionHealth,
    TranscriptionResult,
)


@pytest.mark.parametrize("sample_rate", [8000, 48000])
def test_replacement_receives_its_rate_and_returns_the_same_api_shape(sample_rate):
    class Replacement:
        model_id = "replacement-model"
        capabilities = TranscriptionCapabilities(languages=("Japanese",))

        def __init__(self):
            self.sample_rate = sample_rate
            self.received = None

        def transcribe(self, samples):
            self.received = samples
            # This provider uses a different native output shape.
            native_result = [{"content": "こんにちは"}, {"content": "世界"}]
            return TranscriptionResult(" ".join(segment["content"] for segment in native_result))

        async def health(self):
            return TranscriptionHealth(True)

    provider = Replacement()
    stereo = np.column_stack((np.full(11025, 0.25), np.full(11025, 0.75)))
    data = io.BytesIO()
    sf.write(data, stereo, 22050, format="WAV", subtype="FLOAT")
    with client(provider) as api:
        response = api.post(
            "/v1/audio/transcriptions", files={"file": ("input.wav", data.getvalue())}
        )
        assert response.status_code == 200
        assert response.json() == {
            "text": "こんにちは 世界", "model": "replacement-model", "duration": 0.5,
        }
        samples = provider.received
        assert samples.shape == (sample_rate // 2,)
        assert samples.dtype == np.float32
        assert np.isfinite(samples).all()
        assert np.mean(samples) == pytest.approx(0.5, abs=0.001)
        assert api.get("/health").json()["services"]["transcription"] == {
            "status": "ready", "model": "replacement-model", "sample_rate": sample_rate,
        }
        assert api.get("/v1/audio/transcriptions/capabilities").json() == {
            "automatic_language_detection": False, "languages": ["Japanese"],
        }


@pytest.mark.parametrize("automatic,languages", [(True, ("English", "Danish")), (False, ())])
def test_capabilities_and_openapi_follow_the_provider(automatic, languages):
    provider = FakeTranscriber()
    provider.capabilities = TranscriptionCapabilities(automatic, languages)
    with client(provider) as api:
        assert api.get("/v1/audio/transcriptions/capabilities").json() == {
            "automatic_language_detection": automatic, "languages": list(languages),
        }
        paths = api.get("/openapi.json").json()["paths"]
        assert "/v1/audio/transcriptions/capabilities" in paths


@pytest.mark.parametrize(
    "kind,status", [("invalid", 400), ("busy", 409), ("unavailable", 502), ("timeout", 504)]
)
def test_expected_provider_failure_and_recovery(kind, status):
    class Recovering(FakeTranscriber):
        failed = False

        def transcribe(self, samples):
            if not self.failed:
                self.failed = True
                raise TranscriptionError(kind, "Provider could not process this recording.")
            return TranscriptionResult("")

    with client(Recovering()) as api:
        failed = api.post("/v1/audio/transcriptions", files=audio_file())
        assert failed.status_code == status
        assert failed.json() == {"detail": "Provider could not process this recording."}
        recovered = api.post("/v1/audio/transcriptions", files=audio_file())
        assert recovered.status_code == 200
        assert recovered.json()["text"] == ""


@pytest.mark.parametrize("raises", [False, True])
def test_transcriber_readiness_affects_unified_health(raises):
    class Unavailable(FakeTranscriber):
        async def health(self):
            if raises:
                raise RuntimeError("Private provider diagnostic")
            return TranscriptionHealth(False)

    with client(Unavailable()) as api:
        response = api.get("/health")
        assert response.status_code == 503
        assert response.json()["status"] == "degraded"
        assert response.json()["services"]["speech"] == "ready"
        assert response.json()["services"]["transcription"]["status"] == "unavailable"
        assert "Private provider diagnostic" not in response.text
