import asyncio

import numpy as np
import pytest

from speech_api.transcription import parakeet
from speech_api.transcription.parakeet_config import ParakeetConfig


def test_adapter_uses_validated_settings_and_normalizes_native_result(monkeypatch, tmp_path):
    calls = []
    captured = []

    def pipeline(task, **settings):
        calls.append((task, settings))

        def recognize(samples):
            captured.append(samples)
            return {"text": "  Recognized words. \n"}

        return recognize

    monkeypatch.setattr(parakeet, "pipeline", pipeline)
    monkeypatch.setattr(parakeet.torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(parakeet.torch.cuda, "device_count", lambda: 2)
    config = ParakeetConfig(model_path=tmp_path, device=1, dtype="float32", chunk_length_s=12.5)
    adapter = parakeet.ParakeetTranscriber(config)
    samples = np.zeros(16000, dtype=np.float32)
    assert adapter.transcribe(samples).text == "Recognized words."
    assert captured[0] is samples
    assert calls == [("automatic-speech-recognition", {
        "model": str(tmp_path), "device": 1, "dtype": parakeet.torch.float32,
        "chunk_length_s": 12.5, "stride_length_s": 0,
    })]
    assert asyncio.run(adapter.health()).ready


@pytest.mark.parametrize("available,device", [(False, 0), (True, 1)])
def test_unavailable_device_is_rejected_before_pipeline_load(monkeypatch, tmp_path, available, device):
    def unexpected_load(*args, **kwargs):
        pytest.fail("The model must not load for an unavailable device")

    monkeypatch.setattr(parakeet, "pipeline", unexpected_load)
    monkeypatch.setattr(parakeet.torch.cuda, "is_available", lambda: available)
    monkeypatch.setattr(parakeet.torch.cuda, "device_count", lambda: 1)
    with pytest.raises((RuntimeError, ValueError), match="unavailable"):
        parakeet.ParakeetTranscriber(ParakeetConfig(model_path=tmp_path, device=device))
