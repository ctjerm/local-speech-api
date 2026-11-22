# Transcription adapter contract

The website and HTTP API use one contract. Each provider owns its model loading,
inference settings, native result format, language metadata, and readiness check.
The composition root (`src/speech_api/__main__.py`) selects the provider.

```text
Uploaded file or microphone WAV
          ↓
FastAPI: upload limits → decoding → mono float32 at the provider's sample rate
          ↓
Transcriber adapter → model → TranscriptionResult(text)
          ↓
FastAPI: {text, model, duration} → website or API caller
```

## Stable HTTP interface

`POST /v1/audio/transcriptions` accepts multipart field `file` and returns:

```json
{"text":"Recognized speech.","model":"provider-model-id","duration":3.2}
```

`duration` is decoded audio length in seconds. An empty `text` means no speech
was detected. Both uploads and microphone recordings use this endpoint. Clients
do not send a model name, sampling settings, or framework-specific parameters.

`GET /v1/audio/transcriptions/capabilities` returns provider metadata:

```json
{"automatic_language_detection":false,"languages":["Japanese"]}
```

Language entries are display names. An empty list means the provider has not
supplied language information. The website shows this metadata and hides the
note when discovery fails; transcription remains usable. Metadata does not
guarantee recognition accuracy or add language-selection controls.

`GET /health` retains `services.transcription.{status,model,sample_rate}` and
returns 503 if either service is unavailable. A busy provider is still ready.

## Replacing a model

1. Add a provider module in `src/speech_api/transcription/` implementing
   `Transcriber` from `contracts.py` (a Python protocol; inheritance is optional).
2. Declare `model_id`, the required integer `sample_rate`, and
   `TranscriptionCapabilities`. Initialize the model inside the provider.
3. Implement synchronous `transcribe(samples) -> TranscriptionResult`. Input is
   a one-dimensional, finite NumPy float32 array at the declared sample rate.
   Translate the model's native return value into plain text here. Keep model
   chunking, prompts, precision, device selection, and SDK details in this module.
4. Implement async `health() -> TranscriptionHealth`. Keep it lightweight and
   nonblocking; report whether the initialized provider can accept work.
5. Construct the replacement in `__main__.py` and pass it to `create_app`.
   Adjust its runtime dependencies and startup arguments as required. Manage any
   owned clients/resources in the composition root's lifetime. Restart the API.

The routes, website, recorder, and public request/response formats need no edits.
Replacing a model still requires its adapter and runtime dependencies; this is
not a model downloader or runtime model-selection menu. The HTTP contract
currently exposes plain transcription text, without timestamps or live streaming.

## Shared policy and failures

FastAPI runs inference in a worker thread and admits one transcription at a time.
The lock remains held until inference finishes, including after a caller cancels.
Health and speech generation remain responsive. Every completed or failed request
releases the slot.

The shared decoder owns file limits: 64 MiB upload plus a 64 KiB multipart
envelope; source rates 8–192 kHz; at most 32 million decoded channel samples and
30 minutes. It downmixes and resamples before calling the adapter. WAV and FLAC
are verified; other formats depend on the installed decoder.

Missing input, a non-file value, or unknown form fields return 422; invalid audio
returns 400, oversized upload 413, and concurrent
inference 409. Providers can raise `TranscriptionError` with a safe message and
kind `invalid` (400), `busy` (409), `unavailable` (502), or `timeout` (504).
Unexpected exceptions return a generic 500 and are logged locally.

The default [Parakeet provider](../parakeet/README.md) owns its 16 kHz rate,
25-language list, CUDA/bfloat16 configuration, 30-second nonoverlapping chunks,
and Transformers dictionary-to-text conversion. Alternative providers are covered
by contract tests at 8 and 48 kHz, with different native output shapes and metadata.

The Parakeet constructor accepts `ParakeetConfig`, which validates the local model
directory and runtime settings before loading. See [validation boundaries and
configuration examples](../pydantic/README.md).
