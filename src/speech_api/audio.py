"""Decode uploaded audio without interpreting filenames or fetching URLs."""

from math import gcd
from typing import BinaryIO

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

MAX_UPLOAD_BYTES = 64 * 1024 * 1024
MAX_DECODED_SAMPLES = 32_000_000  # Bound expanded audio to 128 MB before downmixing.


class InvalidAudio(ValueError):
    pass


def decode_audio(file: BinaryIO, sample_rate: int) -> np.ndarray:
    try:
        with sf.SoundFile(file) as source:
            if not 8000 <= source.samplerate <= 192000:
                raise InvalidAudio("Audio sample rate must be between 8,000 and 192,000 Hz.")
            if source.frames == 0:
                raise InvalidAudio("The audio file is empty.")
            if source.frames * source.channels > MAX_DECODED_SAMPLES:
                raise InvalidAudio("The decoded audio is too large; split it into smaller files.")
            if source.frames / source.samplerate > 1800:
                raise InvalidAudio("Audio must be 30 minutes or shorter.")
            original_rate = source.samplerate
            samples = source.read(dtype="float32", always_2d=True).mean(axis=1)
    except (sf.LibsndfileError, RuntimeError) as error:
        raise InvalidAudio("Cannot decode this audio file. Use WAV or FLAC.") from error
    if not len(samples) or not np.isfinite(samples).all():
        raise InvalidAudio("Audio contains no usable samples.")
    if original_rate != sample_rate:
        divisor = gcd(original_rate, sample_rate)
        samples = resample_poly(samples, sample_rate // divisor, original_rate // divisor)
    return samples.astype(np.float32, copy=False)
