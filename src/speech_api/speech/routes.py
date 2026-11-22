"""Stable HTTP requests and streaming responses around an injected generator."""

import logging
from typing import Annotated

import anyio
from fastapi import APIRouter, File, HTTPException
from starlette.responses import StreamingResponse

from .contracts import ReferenceAudio, SpeechAudio, SpeechError, SpeechGenerator, SpeechRequest
from .schemas import SpeechCapabilitiesResponse, SpeechInput

logger = logging.getLogger(__name__)
ERROR_STATUS = {
    "invalid": 400,
    "validation": 422,
    "busy": 409,
    "too_large": 413,
    "unavailable": 502,
    "timeout": 504,
}


class AudioResponse(StreamingResponse):
    def __init__(self, audio: SpeechAudio):
        self.audio = audio
        super().__init__(
            audio.chunks,
            media_type="application/octet-stream",
            headers={
                "X-Sample-Rate": str(audio.sample_rate),
                "X-Sample-Format": "s16le",
                "X-Channels": "1",
            },
        )

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            # Disconnect cancellation must not interrupt resource release.
            with anyio.CancelScope(shield=True):
                await self.audio.close()


def speech_router(generator: SpeechGenerator) -> APIRouter:
    router = APIRouter(tags=["Speech"])

    @router.get("/v1/audio/speech/capabilities", response_model=SpeechCapabilitiesResponse)
    async def capabilities():
        return generator.capabilities

    @router.post(
        "/v1/audio/speech",
        response_class=StreamingResponse,
        responses={
            200: {
                "description": "Streaming mono signed 16-bit little-endian PCM.",
                "content": {
                    "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
                },
                "headers": {
                    "X-Sample-Rate": {
                        "schema": {"type": "integer"},
                        "description": "Samples per second.",
                    },
                    "X-Sample-Format": {"schema": {"type": "string", "enum": ["s16le"]}},
                    "X-Channels": {"schema": {"type": "integer", "enum": [1]}},
                },
            },
        },
    )
    async def generate_speech(
        form: Annotated[SpeechInput, File()],
    ):
        if form.instruction and not generator.capabilities.voice_direction:
            raise HTTPException(400, "This speech provider does not support voice direction.")
        if (form.ref_audio is not None) != bool(form.ref_text):
            raise HTTPException(400, "ref_audio and ref_text must be provided together.")
        if form.ref_audio and not generator.capabilities.reference_audio:
            raise HTTPException(400, "This speech provider does not support reference audio.")
        reference = (
            ReferenceAudio(
                form.ref_audio.file,
                form.ref_audio.filename or "reference.wav",
                form.ref_audio.content_type or "application/octet-stream",
                form.ref_text,
            )
            if form.ref_audio
            else None
        )
        try:
            audio = await generator.generate(
                SpeechRequest(form.text, form.instruction, reference, form.model_extra or {})
            )
        except SpeechError as error:
            raise HTTPException(ERROR_STATUS[error.kind], str(error)) from error
        except Exception as error:
            logger.exception("Speech generation failed")
            raise HTTPException(500, "Speech generation failed. See the server log.") from error
        return AudioResponse(audio)

    return router
