"""Pydantic schemas for the public transcription API."""

from fastapi import UploadFile
from pydantic import BaseModel, ConfigDict, Field


class TranscriptionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: UploadFile = Field(description="Audio file, up to 64 MiB. WAV and FLAC are supported.")


class TranscriptionResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    text: str
    model: str
    duration: float = Field(ge=0, allow_inf_nan=False)


class TranscriptionCapabilitiesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, strict=True)

    automatic_language_detection: bool
    languages: tuple[str, ...]
