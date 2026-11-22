"""Compose HTTP routes around injected speech services."""

import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .speech.contracts import SpeechGenerator, SpeechHealth
from .speech.routes import speech_router
from .transcription.contracts import Transcriber, TranscriptionHealth
from .transcription.routes import transcription_router

logger = logging.getLogger(__name__)


def create_app(transcriber: Transcriber, speech: SpeechGenerator, *, lifespan=None) -> FastAPI:
    app = FastAPI(
        title="Local Speech API",
        version="1.2.0",
        lifespan=lifespan,
        description="Speech generation and audio transcription on your local network.",
    )
    app.include_router(speech_router(speech))
    app.include_router(transcription_router(transcriber))

    @app.get("/health", tags=["Status"])
    async def health():
        try:
            status = await speech.health()
        except Exception:
            logger.exception("Speech health check failed")
            status = SpeechHealth(False)
        try:
            transcription_status = await transcriber.health()
        except Exception:
            logger.exception("Transcription health check failed")
            transcription_status = TranscriptionHealth(False)
        ready = status.ready and transcription_status.ready
        return JSONResponse(
            {
                "status": "ok" if ready else "degraded",
                "sample_rate": status.sample_rate,
                "services": {
                    "speech": "ready" if status.ready else "unavailable",
                    "transcription": {
                        "status": "ready" if transcription_status.ready else "unavailable",
                        "model": transcriber.model_id,
                        "sample_rate": transcriber.sample_rate,
                    },
                },
            },
            status_code=200 if ready else 503,
        )

    return app
