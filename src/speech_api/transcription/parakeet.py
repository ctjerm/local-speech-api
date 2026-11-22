"""Parakeet adapter; owns Transformers and CUDA details."""

import numpy as np
import torch
from transformers import pipeline

from .contracts import TranscriptionCapabilities, TranscriptionHealth, TranscriptionResult
from .parakeet_config import ParakeetConfig


class ParakeetTranscriber:
    model_id = "nvidia/parakeet-tdt-0.6b-v3"
    sample_rate = 16000
    capabilities = TranscriptionCapabilities(
        automatic_language_detection=True,
        languages=(
            "Bulgarian", "Croatian", "Czech", "Danish", "Dutch", "English", "Estonian",
            "Finnish", "French", "German", "Greek", "Hungarian", "Italian", "Latvian",
            "Lithuanian", "Maltese", "Polish", "Portuguese", "Romanian", "Russian",
            "Slovak", "Slovenian", "Spanish", "Swedish", "Ukrainian",
        ),
    )

    def __init__(self, config: ParakeetConfig):
        self.config = config
        if not torch.cuda.is_available():
            raise RuntimeError("The configured NVIDIA CUDA GPU is unavailable.")
        if config.device >= torch.cuda.device_count():
            raise ValueError(f"CUDA device {config.device} is unavailable.")
        # The TDT pipeline currently does not trim overlapping strides. Use zero
        # overlap to avoid duplicated words; chunking bounds GPU memory for long files.
        self.recognizer = pipeline(
            "automatic-speech-recognition",
            model=str(config.model_path),
            device=config.device,
            dtype=getattr(torch, config.dtype),
            chunk_length_s=config.chunk_length_s,
            stride_length_s=config.stride_length_s,
        )

    def transcribe(self, samples: np.ndarray) -> TranscriptionResult:
        with torch.inference_mode():
            return TranscriptionResult(self.recognizer(samples)["text"].strip())

    async def health(self) -> TranscriptionHealth:
        # The constructor loads the model or raises, so a built adapter is ready.
        return TranscriptionHealth(True)
