"""Stable upload and JSON endpoints around an injected transcriber."""

import logging
import threading
from typing import Annotated

from fastapi import APIRouter, File, HTTPException
from fastapi.routing import APIRoute
from starlette.datastructures import Headers

from ..audio import MAX_UPLOAD_BYTES, InvalidAudio, decode_audio
from .contracts import Transcriber, TranscriptionError
from .schemas import (
    TranscriptionCapabilitiesResponse,
    TranscriptionInput,
    TranscriptionResponse,
)

logger = logging.getLogger(__name__)
ERROR_STATUS = {"invalid": 400, "busy": 409, "unavailable": 502, "timeout": 504}


class BoundedUploadRoute(APIRoute):
    async def handle(self, scope, receive, send):
        # Include a small allowance for multipart headers. Enforce this before
        # and during parsing, so chunked uploads cannot exhaust the temp drive.
        limit = MAX_UPLOAD_BYTES + 64 * 1024
        length = Headers(scope=scope).get("content-length")
        if length is not None:
            try:
                oversized = int(length) > limit
            except ValueError as error:
                raise HTTPException(400, "Invalid Content-Length.") from error
            if oversized:
                raise HTTPException(413, "Audio uploads must be 64 MiB or smaller.")
        received = 0

        async def bounded_receive():
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > limit:
                raise HTTPException(413, "Audio uploads must be 64 MiB or smaller.")
            return message

        await super().handle(scope, bounded_receive, send)


def transcription_router(transcriber: Transcriber) -> APIRouter:
    router = APIRouter(route_class=BoundedUploadRoute)
    inference_slot = threading.Lock()

    @router.get(
        "/v1/audio/transcriptions/capabilities",
        tags=["Transcription"],
        response_model=TranscriptionCapabilitiesResponse,
    )
    async def capabilities():
        return transcriber.capabilities

    @router.post("/v1/audio/transcriptions", tags=["Transcription"])
    def transcribe(
        form: Annotated[TranscriptionInput, File()],
    ) -> TranscriptionResponse:
        file = form.file
        # A synchronous route runs in FastAPI's thread pool. The lock stays held even
        # if the caller disconnects while GPU inference is still finishing.
        if not inference_slot.acquire(blocking=False):
            raise HTTPException(
                409, "Transcription is busy. Retry after the current request finishes."
            )
        try:
            if file.size is not None and file.size > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "Audio uploads must be 64 MiB or smaller.")
            try:
                samples = decode_audio(file.file, transcriber.sample_rate)
            except InvalidAudio as error:
                raise HTTPException(400, str(error)) from error
            try:
                result = transcriber.transcribe(samples)
            except TranscriptionError as error:
                raise HTTPException(ERROR_STATUS[error.kind], str(error)) from error
            except Exception as error:
                logger.exception("Transcription inference failed")
                raise HTTPException(
                    500, "Transcription failed. See the local server log."
                ) from error
            return TranscriptionResponse(
                text=result.text,
                model=transcriber.model_id,
                duration=round(len(samples) / transcriber.sample_rate, 3),
            )
        finally:
            inference_slot.release()

    return router
