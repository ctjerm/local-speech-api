import io
import wave

import numpy as np
import pytest
import soundfile as sf

from speech_api.audio import InvalidAudio, decode_audio


def wav(samples, rate):
    data = io.BytesIO()
    sf.write(data, samples, rate, format="WAV", subtype="FLOAT")
    data.seek(0)
    return data


def test_stereo_is_mixed_and_resampled_with_duration_preserved():
    samples = np.column_stack([np.full(24000, 0.4), np.full(24000, 0.2)])
    result = decode_audio(wav(samples, 24000), 16000)
    assert result.shape == (16000,)
    assert result.dtype == np.float32
    assert np.mean(result[100:-100]) == pytest.approx(0.3, abs=0.001)


@pytest.mark.parametrize("data", [io.BytesIO(b"not audio"), wav(np.array([]), 16000)])
def test_invalid_or_empty_audio_is_rejected(data):
    with pytest.raises(InvalidAudio):
        decode_audio(data, 16000)


def test_nonfinite_audio_is_rejected():
    with pytest.raises(InvalidAudio):
        decode_audio(wav(np.full(160, np.nan), 16000), 16000)


@pytest.mark.parametrize("rate", [1, 2147483647])
def test_extreme_sample_rates_are_rejected_before_resampling(rate):
    data = io.BytesIO()
    with wave.open(data, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(b"\x01\x00")
    data.seek(0)
    with pytest.raises(InvalidAudio, match="sample rate"):
        decode_audio(data, 16000)
