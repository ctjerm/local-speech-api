"""Model-neutral transcription inputs, results, metadata, and failures."""

from dataclasses import dataclass
from typing import Literal, Protocol

import numpy as np


@dataclass(frozen=True)
class TranscriptionCapabilities:
    automatic_language_detection: bool = False
    # Display names; an empty tuple means the provider has not supplied a list.
    languages: tuple[str, ...] = ()


@dataclass(frozen=True)
class TranscriptionResult:
    # Plain text, including an empty string when no speech was detected.
    text: str


@dataclass(frozen=True)
class TranscriptionHealth:
    ready: bool


class TranscriptionError(Exception):
    """An expected provider failure with a safe, client-facing message."""

    def __init__(self, kind: Literal["invalid", "busy", "unavailable", "timeout"], message: str):
        super().__init__(message)
        self.kind = kind


class Transcriber(Protocol):
    model_id: str
    sample_rate: int
    capabilities: TranscriptionCapabilities

    def transcribe(self, samples: np.ndarray) -> TranscriptionResult:
        """Accept finite mono float32 samples at sample_rate; run in a worker thread."""
        ...

    async def health(self) -> TranscriptionHealth:
        """Report readiness without running inference or blocking the event loop."""
        ...
