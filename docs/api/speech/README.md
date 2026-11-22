# Model-independent speech API

The website and other clients use `POST /v1/audio/speech`. The route depends only on `SpeechGenerator`, defined in `src/speech_api/speech/contracts.py`. Provider selection and resource ownership live in `src/speech_api/__main__.py`.

```mermaid
flowchart LR
    UI[Website] <--> Routes[Common FastAPI routes]
    Routes <--> Contract[SpeechGenerator contract]
    Contract <--> Adapter[Breeze adapter]
    Adapter <--> Worker[Local model worker]
```

## Requests and results

Requests accept URL-encoded or multipart form fields:

| Field | Meaning |
| --- | --- |
| `text` | Required nonempty text |
| `instruction` | Optional voice direction, when supported |
| `ref_audio` and `ref_text` | Optional reference recording and its exact transcript, when supported; supply both |

The response streams raw **mono signed 16-bit little-endian PCM**. `X-Sample-Rate` declares samples per second, `X-Sample-Format` is `s16le`, and `X-Channels` is `1`. Adapters must convert their model's native output to this contract. Clients must use the declared sample rate rather than assuming 24 kHz. The browser and Python example wrap PCM in a WAV for playback.

`GET /v1/audio/speech/capabilities` returns `voice_direction` and `reference_audio` booleans plus a `languages` list of display names (empty means unspecified). Unsupported optional inputs are rejected before inference. The website uses this metadata for its voice controls and language label; if discovery fails, plain speech generation remains available.

Errors are JSON `detail` messages (or field-error lists for Pydantic form validation): 400 for unsupported capabilities or incomplete reference pairs, 422 for malformed fields and invalid provider overrides, 409 for a busy provider, 413 for oversized input, 502 for an unavailable worker or invalid audio metadata, and 504 for worker timeout. Unexpected internal errors return a generic 500. Failures after streaming begins terminate the transfer; clients must discard incomplete audio. See [validation boundaries](../pydantic/README.md).

## Replacing a provider

1. Implement `generate(SpeechRequest) -> SpeechAudio` and `health() -> SpeechHealth` as async methods, and declare `SpeechCapabilities`. Python's `Protocol` describes the required methods without requiring inheritance.
2. Translate text, instruction and reference audio to the new model's inputs. A reference contains a borrowed file stream: consume it while generating the response and do not retain it after the request ends.
3. Return an async PCM chunk iterator, a positive integer sample rate, and an async `close` callback. The HTTP response calls `close` after completion, failure or client disconnection, shielding cleanup from cancellation. The adapter owns resources until it returns a `SpeechAudio`; it must close them itself if preparation fails.
4. Construct the provider in `__main__.py` and pass it to `create_app(transcriber, speech)`. That startup code also owns provider clients and processes. The common routes and website need no edits. Remove the optional Breeze compatibility mounting when replacing Breeze.

New models may need different runtime dependencies or a worker process. The interface isolates their request and output differences; it does not install or load arbitrary checkpoints automatically.

Tests inject providers with different capabilities and 16/48 kHz output through the same routes. They also cover error translation, reference uploads, and stream cleanup after completion, provider failure and disconnection.

## Breeze compatibility

`speech/breeze.py` owns worker requests and audio-header validation. Its `BreezeConfig` in `speech/breeze_config.py` validates guidance scale defaults (1 for plain text, 4 for voice direction) and seed 42. The common speech request schema and browser contain no Breeze tuning fields.

For existing callers, extra text form fields are passed to the selected adapter as `provider_options`. Breeze validates `cfg_scale` as finite and positive and `seed` as an unsigned 32-bit integer, rejecting invalid or unknown fields with 422 before contacting the worker. These overrides are provider-specific and are not part of the portable contract; replacements must reject overrides they do not support. Normal callers do not need them.

`speech/breeze_compat.py` optionally mounts the original `/v1/model` and `/v1/audio/speech/batch` endpoints and their upstream documentation. These provider-specific routes do not replace the common speech schema. The generic app does not import the Breeze adapter or compatibility module.
