"""The speech contract uses Python data, without HTTP or model dependencies."""

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import BinaryIO, Literal, Protocol


@dataclass(frozen=True)
class SpeechCapabilities:
    voice_direction: bool = False
    reference_audio: bool = False
    languages: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReferenceAudio:
    content: BinaryIO
    filename: str
    media_type: str
    text: str


@dataclass(frozen=True)
class SpeechRequest:
    text: str
    instruction: str = ""
    reference: ReferenceAudio | None = None
    # Optional legacy overrides. Normal clients need only the fields above.
    # An adapter must reject overrides it does not understand.
    provider_options: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SpeechAudio:
    """Mono signed 16-bit little-endian PCM; the caller owns closing the stream."""

    sample_rate: int
    chunks: AsyncIterator[bytes]
    close: Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class SpeechHealth:
    ready: bool
    sample_rate: int | None = None


ErrorKind = Literal["invalid", "validation", "busy", "too_large", "unavailable", "timeout"]


class SpeechError(Exception):
    def __init__(self, kind: ErrorKind, message: str):
        super().__init__(message)
        self.kind = kind


class SpeechGenerator(Protocol):
    capabilities: SpeechCapabilities

    async def generate(self, request: SpeechRequest) -> SpeechAudio: ...

    async def health(self) -> SpeechHealth: ...
