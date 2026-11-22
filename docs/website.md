# Voice room website

Open `/` on the API address. The existing Start and Stop scripts manage the website and both models together. The browser uses relative API URLs, so the same page works through localhost or the PC's LAN address.

## Boundaries

`src/speech_api/website.py` serves the document and static assets. The composition root in `__main__.py` mounts it; the generic API factory does not depend on the website. There is no frontend build process or external asset dependency.

| File | Responsibility |
| --- | --- |
| `web/index.html` | Semantic forms, tabs, result players and downloads |
| `web/styles.css` | Responsive layout, focus states and reduced motion |
| `web/app.js` | Form state, cancellation, file selection, result presentation |
| `web/api.js` | Stable HTTP requests, provider capabilities, error translation |
| `web/audio.js` | PCM-to-WAV encoding and waveform drawing |
| `web/recording` | Microphone lifecycle, PCM capture, controls and device setup |

The browser sends only `text` and `instruction`. The server-side provider adapter owns model tuning and defaults. The browser reads `/v1/audio/speech/capabilities` to show supported voice controls and the provider's language names; plain text generation remains available if capability discovery fails. It checks the audio headers and packages the complete mono signed 16-bit PCM response into a WAV blob for browser playback. Playback begins after generation finishes. The API itself continues to stream PCM for API callers. See [the speech adapter contract](api/speech/README.md).

Transcription sends the selected file as multipart field `file`. The website reads `/v1/audio/transcriptions/capabilities` for language support and automatic detection; unavailable metadata hides the note without blocking recording or uploads. The server resamples audio to the selected provider's required rate and returns the same transcript JSON. See [the transcription adapter contract](api/transcription/README.md). Browser validation rejects files larger than 64 MiB before upload; the server owns audio decoding and all other limits. Generated WAVs can become transcription inputs directly. Downloads and previews use browser object URLs, which are released when replaced or the document is discarded. Reloading clears the workspace.

Each form has independent request state. Cancel aborts the browser request; an active transcription may finish on the server before its next request is accepted. Busy, invalid audio, oversized upload and server errors restore form controls and preserve the last successful output. Uploaded filenames and transcripts render as plain text.

File upload and speech generation work on HTTP LAN addresses. Copy first tries the Clipboard API, then falls back to browser copy with selected text. If both fail, the text stays selected with a manual-copy prompt. Voice cloning controls remain outside this example's scope.

Microphone recording needs trusted HTTPS or localhost. `getUserMedia` requests mono audio after a user click. An `AudioWorklet` captures signed 16-bit PCM without routing microphone sound to the speakers. The requested sample rate is 16 kHz; the WAV header uses the actual audio context rate. The recorder stops at the existing API limit of 30 minutes or 32 million samples, whichever comes first. Stop makes a WAV for preview and the existing multipart transcription flow; Cancel preserves the previous recording. Tracks and audio contexts are released on stop, cancel, failure, disconnection and page exit, including permission granted after cancellation. Recordings stay in browser memory until submitted.

`Verify-Microphone.py` tests trusted HTTPS and localhost with Chromium's simulated microphone, plus a real Parakeet transcription of the captured WAV. It does not access the physical microphone. It also tests permission failures, delayed permission after cancellation, disconnected tracks, page exit, PCM bounds, mobile layout and certificate download. Run it with the same dedicated Playwright environment below, after `Verify-Website.py` creates its speech fixture and before removing the browser. Pass the LAN IP used for the certificate, for example `Verify-Microphone.py --address <server-ip>`. It requires configured HTTPS with the local CA trusted by the Windows user and writes evidence under `runtime/verification/microphone`.

## Headless verification

`tests/test_website.py` checks that the document and assets coexist with health, transcription and OpenAPI routes. `Verify-Website.py` runs a separate headless Chromium session against the actual local models, with mocked responses only for deterministic failure, cancellation and long-filename cases. It saves screenshots, a WAV, a transcript and JSON results under `runtime/verification/website`.

Prepare a dedicated test environment with all browser downloads, profiles and cache under `runtime`. These commands run from the project directory:

```powershell
$env:TEMP = Join-Path $PWD 'runtime\scratch\temp'
$env:TMP = $env:TEMP
$env:UV_CACHE_DIR = Join-Path $PWD 'runtime\scratch\uv-cache'
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $PWD 'runtime\browser-qa\browsers'
New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
if (-not (Test-Path '.\runtime\browser-qa\.venv\Scripts\python.exe')) {
    uv venv --relocatable --python '.\runtime\python\cpython-3.12.8-windows-x86_64-none\python.exe' '.\runtime\browser-qa\.venv'
}
uv pip install --python '.\runtime\browser-qa\.venv\Scripts\python.exe' playwright==1.64.0
& .\runtime\browser-qa\.venv\Scripts\python.exe -m playwright install chromium --only-shell
& .\runtime\browser-qa\.venv\Scripts\python.exe .\Verify-Website.py
& .\runtime\browser-qa\.venv\Scripts\python.exe -m playwright uninstall
uv pip uninstall --python '.\runtime\browser-qa\.venv\Scripts\python.exe' playwright greenlet pyee typing-extensions
uv cache clean --cache-dir $env:UV_CACHE_DIR
```

The cleanup commands remove only this dedicated browser installation and its test packages. Reinstall those packages and the browser to rerun. The script closes its browser even if an assertion fails. It plays generated audio muted and never opens a visible browser or takes desktop focus. Browser checks cover 320, 390, 768 and 1366 px widths, keyboard tabs, real speech with/without voice direction, recording upload/drop, playback, both downloads, copy on HTTP, cancellation, busy/error recovery and long filename wrapping. They exercise Chromium; Safari/Firefox and physical mobile devices have not been tested.
