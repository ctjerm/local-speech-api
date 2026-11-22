# Verification

Measured on native Windows with an RTX 5080 (16 GB), Python 3.12.8 and PyTorch 2.9.1+cu128. Timings are complete HTTP requests for these inputs on this machine, not latency guarantees.

## Automated tests

- 100 pytest tests cover audio decoding, bounded uploads, busy and recovery handling, replacement speech and transcription providers at different sample rates, capability reporting, Pydantic validation of forms and adapter configuration, reference uploads, error translation, readiness, stream cleanup, compatibility routes, website assets and HTTPS configuration. Unit tests replace the models; they do not load weights.
- `tests/Test-StartupRollback.ps1` injects a state-write failure during startup and checks that the already started worker is stopped.
- Ruff passes. Dependencies and model and source revisions are pinned.

## Real models

| Check | Result |
| --- | --- |
| Parakeet, 7.3 s English WAV and stereo FLAC | Correct text; 0.09 to 0.14 s warm |
| Parakeet, 36.4 s recording across the 30 s chunk boundary | All five passages transcribed in about 0.4 s |
| Speech generation and transcription at the same time | Both succeed; about 12 GiB GPU memory in use |
| Breeze streaming, first audio | About 0.5 s |
| Breeze voice design and reference-audio cloning | Pass |
| Generated speech sent back through transcription | Correct text in under 0.1 s |
| Client disconnect mid-stream | Inference slot released; next request returns audio |
| Second request to a busy model | HTTP 409, health stays responsive |
| Raspberry Pi on the LAN | Generated and transcribed speech; private worker port unreachable |

## Browser

`Verify-Website.py` runs headless Chromium against the real models: speech with and without voice direction, playback, WAV and transcript downloads, upload and drag-and-drop, cancellation, busy and error recovery, keyboard navigation, and layouts at 320, 390, 768 and 1366 px. `Verify-Microphone.py` uses Chromium's simulated microphone over trusted HTTPS and localhost, including permission failures, cancellation, disconnection, page exit and certificate download. Neither touches a physical microphone.

## Limitations

- Trusted LAN only: no authentication, manual start after reboot.
- One inference at a time per model. Large Breeze batches are untested.
- Parakeet supports 25 languages according to NVIDIA; accuracy checks here used English.
- Long audio uses non-overlapping 30 s chunks, so words on a boundary may be less accurate.
- Breeze speaks English and Chinese. No formal listening or speaker-similarity study was done.
- Chromium only; Safari, Firefox and physical phones are untested.
