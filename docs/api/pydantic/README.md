# Validation boundaries

Pydantic 2.14.1 is pinned as a direct API dependency (it was already installed).
The API uses FastAPI's native form-model parsing, documented in
[Form Models](https://fastapi.tiangolo.com/tutorial/request-form-models/), together
with its `UploadFile` type. `File()` declares multipart request documentation and
still accepts URL-encoded speech forms. No custom request parser is used.

## Public API schemas

`speech/schemas.py` owns the public speech form and capability response.
`transcription/schemas.py` owns the transcription form, result, and capabilities.
These modules contain no model identities or tuning parameters. Internal request
and result dataclasses, NumPy audio, and provider protocols remain lightweight.

- Speech `text` is required and must contain non-whitespace text. Text,
  instruction, and reference transcript are trimmed. Their values must be strings;
  the optional reference recording must be an uploaded file.
- Extra speech fields must be strings and are forwarded to the selected adapter
  for validation. A replacement can define its own options without editing the
  generic schema. Breeze-specific options are not advertised as portable fields.
- Transcription requires an uploaded `file`; a string containing a path is not
  an upload. Unknown fields now return 422 instead of being silently ignored.
- Common field validation failures return HTTP 422 with FastAPI's field locations
  and messages in `detail`. Reference-pair and unsupported-capability checks retain
  their existing HTTP 400 responses. File-size and decoded-audio limits stay in
  their existing upload/decoder layers.
- Capability responses and transcript results are validated and described in
  OpenAPI. The existing response field names, audio format, and endpoints remain.

## Adapter configuration

Each provider owns its Pydantic models. Configuration objects validate defaults,
reject misspelled/unknown keys, use strict types, and are frozen after construction.
See [Pydantic model configuration](https://docs.pydantic.dev/latest/api/config/).

`speech/breeze_config.py` defines `BreezeConfig` for generation defaults and
`BreezeOptions` for optional request overrides. Guidance must be finite and greater
than zero. Seeds must be integers in 0–4,294,967,295: the pinned worker's
`breeze_infer/runtime.py:set_all_seeds` calls NumPy's legacy `random.seed`.
Request overrides intentionally parse numeric form strings. Invalid overrides
return 422 before contacting the worker, including guidance values that previously
returned 400 from the worker. Unknown options also return 422.

```python
speech = BreezeSpeechGenerator(
    worker,
    BreezeConfig(plain_cfg_scale=1.0, instructed_cfg_scale=4.0, seed=42),
)
```

`transcription/parakeet_config.py` defines `ParakeetConfig`: an existing local model
directory, nonnegative CUDA device index, dtype (`bfloat16`, `float16`, `float32`),
positive finite chunk duration, and zero stride. Zero stride is required because
the pinned TDT pipeline does not trim overlap. The adapter checks that the selected
CUDA device exists before creating the Transformers pipeline. Its 16 kHz sample
rate and language list are model properties, not adjustable settings.

```python
transcriber = ParakeetTranscriber(
    ParakeetConfig(model_path=model_directory, device=0, dtype="bfloat16", chunk_length_s=30),
)
```

The composition root selects these adapters. New providers supply their own
configuration schemas alongside their implementation. No global model-options
registry or environment-variable loader was introduced. Optional legacy Breeze
batch routes retain the worker's own validation.
