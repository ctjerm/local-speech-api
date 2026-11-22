# Breeze TTS API contract

Upstream: https://github.com/breezeblue-ai/breeze-tts

Model: https://huggingface.co/BreezeBlue/Breeze-TTS-2

Revisions are pinned in `service.psd1`. This setup uses the official server, without changing model or API source. Upstream documents Linux; this deployment tests native Windows with CUDA PyTorch 2.9.1, CUDA 12.8, Python 3.12, and eager inference. Full fast mode is disabled because the upstream recommendation is 24 GB VRAM.

## Requests

The following is the upstream Breeze worker contract. The public `/v1/audio/speech` endpoint now uses the [model-independent speech contract](../speech/README.md): clients normally send `text` and optional `instruction`. `BreezeSpeechGenerator` chooses guidance scale 1 for plain text, 4 for voice direction, and seed 42. Existing explicit `cfg_scale` and `seed` fields remain accepted as provider-specific overrides. Batch and model-info routes remain optional Breeze compatibility endpoints.

- `GET /health`: JSON status and audio sample rate. The server only accepts connections after model loading finishes.
- `GET /v1/model`: checkpoint digest, frame rate, and token/batch limits.
- `GET /docs`: generated Swagger documentation with interactive request forms.
- `POST /v1/audio/speech`: form data (`application/x-www-form-urlencoded` or multipart). Required `text`; optional `instruction`, `cfg_scale` (default 1), `seed` (default 42), and paired `ref_audio` file plus `ref_text` transcript. Use `cfg_scale=4` with a nonempty voice instruction. Plain text without an instruction uses the default `cfg_scale=1`; upstream rejects higher CFG for that template. Voice cloning needs the exact transcript of the entire reference clip. Add an instruction to direct the cloned voice.
- `POST /v1/audio/speech/batch`: form `texts` as a JSON array; optional voice parameters and `max_new_tokens`. Shares the inference slot. Batch memory grows with text count; the upstream limit of 128 is a schema limit, not a tested capacity for this 16 GB GPU.

The single speech response streams **raw mono signed 16-bit little-endian PCM at 24,000 Hz**, with `X-Sample-Rate` and `X-Sample-Format: s16le`. It has no WAV header and cannot be renamed to a WAV file. `examples/speak.py` wraps it correctly using Python's standard library. Streaming errors can interrupt a response after HTTP 200; callers must treat incomplete transfers as failures.

Only one inference request runs at a time. A simultaneous request returns HTTP 409; callers can retry after the active request finishes. Health remains available. Missing fields return HTTP 422; invalid CFG or incomplete reference pairs return HTTP 400. Batch responses concatenate segments and provide byte lengths in `X-Segment-Bytes`.

## Network and privacy

The public FastAPI server binds `0.0.0.0:7860` and translates speech requests through its Breeze adapter to the official worker at `127.0.0.1:7861`. The public health response also reports transcription readiness. `Enable-Lan.ps1` adds only an inbound TCP rule on the Private profile for `LocalSubnet`. Run that script from an administrator PowerShell if a rule is needed. The API is unauthenticated and intended for this trusted LAN. This setup does not configure router forwarding or Internet publication. Localhost and self-LAN calls do not prove that another device can pass the firewall.

After installation, startup sets Hugging Face and Transformers offline modes and loads the local checkpoint. Text and reference audio are processed locally. Upstream temporarily saves reference uploads and deletes them when the request finishes. Logs are under the runtime's `logs` directory.

The model supports English and Chinese. Its weights and self-hosted outputs are governed by the BreezeBlue research and non-commercial license; the source has a separate Apache 2.0 license. The model license is downloaded to `runtime/breeze/model/LICENSE`.
