"""Pydantic schemas for the public speech API, independent of providers."""

from typing import Annotated

from fastapi import UploadFile
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

TrimmedText = Annotated[str, StringConstraints(strip_whitespace=True)]


class SpeechInput(BaseModel):
    # Adapter-specific overrides remain opaque text until the adapter validates them.
    model_config = ConfigDict(extra="allow", strict=True)
    __pydantic_extra__: dict[str, str] = Field(init=False)

    text: Annotated[TrimmedText, Field(min_length=1)]
    instruction: TrimmedText = ""
    ref_text: TrimmedText = ""
    ref_audio: UploadFile | None = None


class SpeechCapabilitiesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, strict=True)

    voice_direction: bool
    reference_audio: bool
    languages: tuple[str, ...]
