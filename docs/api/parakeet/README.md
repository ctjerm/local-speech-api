# Parakeet transcription integration

Model: [NVIDIA Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3), provided by NVIDIA under CC BY 4.0. Original model card is retained at `runtime/parakeet/model/README.md`.

Pinned model revision: `541d1f99c6b0c3cd0b11a95167540bb8edefd82b`. The safetensors checkpoint and JSON configuration/tokenizer files are downloaded; alternate NeMo/GGUF weights are unnecessary for this runtime.

## Runtime contract

Transformers 5.20.1 supports Parakeet through its documented automatic-speech-recognition pipeline. The model runs on CUDA in bfloat16 with PyTorch 2.9.1+cu128 and the dedicated Python 3.12.8 installation under `runtime/python`. Breeze's incompatible Transformers 4.57.3 remains in its own environment. No custom model code or remote-code execution is loaded.

Sources: [Transformers Parakeet documentation](https://huggingface.co/docs/transformers/model_doc/parakeet), [pinned pipeline source](https://github.com/huggingface/transformers/blob/v5.20.1/src/transformers/pipelines/automatic_speech_recognition.py).

The pinned pipeline's TDT path does not trim overlapping strides during postprocessing. Therefore this adapter explicitly uses `chunk_length_s=30, stride_length_s=0`, avoiding duplicated overlap text and bounding GPU memory. Long recordings are supported, but words at hard chunk boundaries may lose context. This API exposes text only; word timestamps and live microphone streaming are not implemented.

`ParakeetConfig` validates the local model directory, CUDA device index, dtype,
positive finite chunk duration, and required zero stride before model loading.
The adapter then verifies device availability. Defaults retain the settings above;
alternative settings are adapter configuration, not public HTTP fields. See
[configuration examples and validation rules](../pydantic/README.md).

## Endpoint

`src/speech_api/transcription/parakeet.py` implements the shared
[transcription adapter contract](../transcription/README.md). The generic routes
and website do not import Parakeet or Transformers. This adapter supplies its
sample rate, language metadata, readiness, and normalized text result.

`POST /v1/audio/transcriptions`, multipart field `file`. Returns JSON:

```json
{"text":"Recognized speech.","model":"nvidia/parakeet-tdt-0.6b-v3","duration":3.2}
```

`duration` is the decoded audio duration in seconds, not processing latency. The server averages channels, resamples using SciPy, and returns the detected language's text. No language field is required. NVIDIA lists 25 supported European languages, including Danish and English; this deployment's accuracy checks used English speech, not every supported language.

WAV and FLAC are verified. Other containers depend on the installed libsndfile decoder; no FFmpeg dependency is required for the verified formats. Filenames are not interpreted as server paths, and remote URLs are not accepted.

Limits protect local storage and memory: 64 MiB per file, an additional 64 KiB multipart envelope allowance enforced while streaming the request body, 8–192 kHz source rates, at most 32 million decoded channel samples, and at most 30 minutes. Malformed, empty, nonfinite, unsupported-rate, or excessive decoded audio returns 400; missing file returns 422; excessive upload bytes return 413. Busy inference returns 409; unexpected model failure returns 500 with details in the local log. Failed requests release the inference slot.

Inference runs in a worker thread so health and the speech proxy stay responsive. The lock remains held until computation finishes even if a caller disconnects. The endpoint handles one transcription at a time; Breeze has its own independent slot.
