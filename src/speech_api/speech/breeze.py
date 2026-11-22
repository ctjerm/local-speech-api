"""Translate the common speech contract to the existing Breeze worker API."""

import anyio
import httpx
from pydantic import ValidationError

from .breeze_config import BreezeConfig, BreezeOptions
from .contracts import SpeechAudio, SpeechCapabilities, SpeechError, SpeechHealth, SpeechRequest


class BreezeSpeechGenerator:
    capabilities = SpeechCapabilities(
        voice_direction=True, reference_audio=True, languages=("English", "Chinese"),
    )

    def __init__(self, client: httpx.AsyncClient, config: BreezeConfig | None = None):
        # The composition root owns the client's lifetime and worker process.
        self.client = client
        self.config = config or BreezeConfig()

    async def health(self) -> SpeechHealth:
        try:
            response = await self.client.get("/health", timeout=2)
            response.raise_for_status()
            health = response.json()
            return SpeechHealth(health.get("status") == "ok", health.get("sample_rate"))
        except (httpx.HTTPError, ValueError):
            return SpeechHealth(False)

    async def generate(self, request: SpeechRequest) -> SpeechAudio:
        try:
            options = BreezeOptions.model_validate({
                "cfg_scale": (
                    self.config.instructed_cfg_scale if request.instruction
                    else self.config.plain_cfg_scale
                ),
                "seed": self.config.seed,
                **request.provider_options,
            })
        except ValidationError as error:
            details = "; ".join(
                f"{'.'.join(map(str, item['loc']))}: {item['msg']}"
                for item in error.errors(include_input=False, include_url=False)
            )
            raise SpeechError("validation", f"Invalid speech options: {details}") from error
        fields = {
            "text": request.text,
            "instruction": request.instruction,
            "cfg_scale": format(options.cfg_scale, ".17g"),
            "seed": str(options.seed),
        }
        files = None
        if request.reference:
            reference = request.reference
            fields["ref_text"] = reference.text
            files = {"ref_audio": (reference.filename, reference.content, reference.media_type)}
        outgoing = self.client.build_request("POST", "/v1/audio/speech", data=fields, files=files)
        try:
            response = await self.client.send(outgoing, stream=True)
        except httpx.TimeoutException as error:
            raise SpeechError("timeout", "Speech generation worker timed out.") from error
        except httpx.HTTPError as error:
            raise SpeechError("unavailable", "Speech generation worker is unavailable.") from error
        try:
            if response.is_error:
                await response.aread()
                kind = {
                    400: "invalid",
                    422: "validation",
                    409: "busy",
                    413: "too_large",
                    504: "timeout",
                }.get(response.status_code, "unavailable")
                message = "Speech generation worker could not complete the request."
                if response.status_code < 500:
                    try:
                        detail = response.json().get("detail")
                        if isinstance(detail, str):
                            message = detail
                    except (ValueError, AttributeError):
                        pass
                raise SpeechError(kind, message)
            rate = int(response.headers.get("x-sample-rate", "0"))
            if rate <= 0 or response.headers.get("x-sample-format") != "s16le":
                raise ValueError("Invalid PCM metadata")
            return SpeechAudio(rate, response.aiter_bytes(), response.aclose)
        except BaseException as error:
            with anyio.CancelScope(shield=True):
                await response.aclose()
            if isinstance(error, httpx.TimeoutException):
                raise SpeechError("timeout", "Speech generation worker timed out.") from error
            if isinstance(error, httpx.HTTPError):
                raise SpeechError("unavailable", "Speech generation worker is unavailable.") from error
            if isinstance(error, ValueError):
                raise SpeechError(
                    "unavailable", "Speech worker returned invalid audio metadata."
                ) from error
            raise
