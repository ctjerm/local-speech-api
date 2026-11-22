"""Headless browser checks against the running local models; artifacts stay under runtime/."""

import argparse
import json
import os
import time
import wave
from pathlib import Path
from urllib.parse import parse_qs

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "runtime" / "verification" / "website"
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(ROOT / "runtime" / "browser-qa" / "browsers")
os.environ["TEMP"] = os.environ["TMP"] = str(ROOT / "runtime" / "scratch" / "temp")
OUTPUT.mkdir(parents=True, exist_ok=True)
Path(os.environ["TEMP"]).mkdir(parents=True, exist_ok=True)


def capability_response(capabilities):
    def respond(route):
        route.fulfill(status=200 if capabilities else 503,
                      json=capabilities or {"detail": "Temporarily unavailable"})
    return respond


def verify(url: str):
    report = {"url": url, "checks": [], "timings_seconds": {}}
    errors = []
    external = []

    def passed(name):
        report["checks"].append(name)
        print(f"PASS {name}", flush=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(viewport={"width": 1366, "height": 1050})
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: external.append(request.url)
                    if request.url.startswith("http") and not request.url.startswith(url) else None)
            page.goto(url, wait_until="networkidle")
            assert page.evaluate("async () => (await fetch('/health')).json()")["status"] == "ok"
            expect(page.locator("#generate-button")).to_be_disabled()
            page.locator("#speak-tab").focus()
            page.keyboard.press("ArrowRight")
            expect(page.locator("#transcribe-tab")).to_be_focused()
            expect(page.locator("#transcribe-panel")).to_be_visible()
            expect(page.locator("#transcribe-button")).to_be_disabled()
            page.keyboard.press("Home")
            expect(page.locator("#speak-panel")).to_be_visible()
            page.screenshot(path=str(OUTPUT / "desktop.png"), full_page=True)
            passed("Initial state, health, keyboard tab navigation")

            for capabilities in ({"voice_direction": False, "reference_audio": False, "languages": ["Danish"]}, None):
                page.route("**/v1/audio/speech/capabilities", capability_response(capabilities))
                page.route("**/v1/audio/speech", lambda route: route.fulfill(
                    status=200, body=b"\x00\x00" * 1600,
                    headers={"X-Sample-Rate": "16000", "X-Sample-Format": "s16le"},
                ))
                page.reload(wait_until="networkidle")
                expect(page.locator("#voice-options")).to_be_hidden()
                if capabilities:
                    expect(page.locator("#speech-languages")).to_have_text("Danish")
                else:
                    expect(page.locator("#speech-languages")).to_be_hidden()
                page.locator("#example-button").click()
                with page.expect_request("**/v1/audio/speech") as request:
                    page.locator("#generate-button").click()
                form = parse_qs(request.value.post_data, keep_blank_values=True)
                assert set(form) == {"text", "instruction"} and form["instruction"] == [""]
                expect(page.locator("#speech-status")).to_have_attribute("data-kind", "success")
                page.unroute("**/v1/audio/speech")
                page.unroute("**/v1/audio/speech/capabilities")
            page.reload(wait_until="networkidle")
            expect(page.locator("#voice-options")).to_be_visible()
            expect(page.locator("#speech-languages")).to_have_text("English · Chinese")
            passed("Provider capabilities adapt voice controls; plain speech works without capabilities")

            for capabilities, note in (
                ({"automatic_language_detection": True, "languages": ["English", "Danish"]},
                 "Automatic language detection · English · Danish"),
                ({"automatic_language_detection": False, "languages": ["Japanese"]}, "Japanese"),
                ({"automatic_language_detection": False, "languages": []}, ""),
                (None, ""),
            ):
                page.route("**/v1/audio/transcriptions/capabilities", capability_response(capabilities))
                page.route("**/v1/audio/transcriptions", lambda route: route.fulfill(
                    json={"text": "こんにちは", "model": "replacement", "duration": 1.0},
                ))
                page.reload(wait_until="networkidle")
                page.locator("#transcribe-tab").click()
                if note:
                    expect(page.locator("#transcription-languages")).to_have_text(note)
                    expect(page.locator("#transcription-language-note")).to_be_visible()
                else:
                    expect(page.locator("#transcription-language-note")).to_be_hidden()
                page.locator("#audio-file").set_input_files({
                    "name": "replacement.wav", "mimeType": "audio/wav", "buffer": b"fixture",
                })
                with page.expect_request("**/v1/audio/transcriptions") as request:
                    page.locator("#transcribe-button").click()
                body = request.value.post_data_buffer
                assert body.count(b' name="') == 1 and b' name="file"' in body
                expect(page.locator("#transcript-text")).to_have_value("こんにちは")
                page.unroute("**/v1/audio/transcriptions")
                page.unroute("**/v1/audio/transcriptions/capabilities")
            page.reload(wait_until="networkidle")
            expect(page.locator("#transcription-languages")).to_have_text(
                "Automatic language detection · 25 supported languages"
            )
            passed("Transcription provider metadata adapts languages; uploads work without metadata")

            text = "Welcome to the local audio studio. Both speech tools are ready to use."
            page.locator("#speech-text").fill(text)
            page.locator("#voice-direction").fill("   ")
            started = time.perf_counter()
            with page.expect_request("**/v1/audio/speech") as request:
                page.locator("#generate-button").click()
            assert set(parse_qs(request.value.post_data, keep_blank_values=True)) == {"text", "instruction"}
            expect(page.locator("#speech-status")).to_have_attribute("data-kind", "success", timeout=180000)
            report["timings_seconds"]["speech_without_direction"] = round(time.perf_counter() - started, 2)
            page.wait_for_function("document.querySelector('#speech-player').duration > 0")
            page.locator("#speech-player").evaluate("async a => { a.muted = true; await a.play(); }")
            page.wait_for_function("document.querySelector('#speech-player').currentTime > 0.15")
            page.locator("#speech-player").evaluate("a => a.pause()")
            with page.expect_download() as download:
                page.locator("#audio-download").click()
            wav_path = OUTPUT / "speech.wav"
            download.value.save_as(wav_path)
            with wave.open(str(wav_path)) as audio:
                assert (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) == (1, 2, 24000)
                assert audio.getnframes() > 24000
            page.screenshot(path=str(OUTPUT / "desktop-audio.png"), full_page=True)
            passed("Real speech generation, muted playback, waveform and valid WAV download")

            page.locator("#use-audio").click()
            expect(page.locator("#file-name")).to_have_text("generated-speech.wav")
            started = time.perf_counter()
            page.locator("#transcribe-button").click()
            expect(page.locator("#transcription-status")).to_have_attribute("data-kind", "success", timeout=180000)
            report["timings_seconds"]["transcription_handoff"] = round(time.perf_counter() - started, 2)
            transcript = page.locator("#transcript-text").input_value()
            assert "local audio studio" in transcript.lower(), transcript
            report["transcript"] = transcript
            page.locator("#copy-transcript").click()
            expect(page.locator("#copy-status")).to_have_text("Copied to clipboard.")
            with page.expect_download() as download:
                page.locator("#transcript-download").click()
            transcript_path = OUTPUT / "transcript.txt"
            download.value.save_as(transcript_path)
            assert transcript_path.read_text(encoding="utf-8") == transcript
            page.screenshot(path=str(OUTPUT / "desktop-transcript.png"), full_page=True)
            passed("Generated audio handoff, real transcription, clipboard copy and text download")

            page.locator("#remove-file").click()
            expect(page.locator("#transcribe-button")).to_be_disabled()
            page.locator("#audio-file").set_input_files(str(wav_path))
            page.wait_for_function("document.querySelector('#upload-player').duration > 0")
            page.locator("#transcribe-button").click()
            expect(page.locator("#transcription-status")).to_have_attribute("data-kind", "success", timeout=60000)
            assert page.locator("#transcript-text").input_value() == transcript
            passed("Recording upload, preview, removal and real upload transcription")

            page.locator("#audio-file").set_input_files({"name": "invalid.wav", "mimeType": "audio/wav", "buffer": b"not audio"})
            page.locator("#transcribe-button").click()
            expect(page.locator("#transcription-status")).to_have_attribute("data-kind", "error")
            expect(page.locator("#transcribe-button")).to_be_enabled()
            expect(page.locator("#preview-note")).to_be_visible()
            passed("Real invalid audio error and request recovery")

            page.locator("#audio-file").evaluate("""input => {
              const transfer = new DataTransfer();
              transfer.items.add(new File([new ArrayBuffer(64 * 1024 * 1024 + 1)], 'oversized.wav'));
              input.files = transfer.files; input.dispatchEvent(new Event('change'));
            }""")
            expect(page.locator("#transcription-status")).to_contain_text("too large")
            passed("Oversized file blocked before upload")

            # Drop a real WAV under a long, untrusted filename; it must stay plain text.
            payload = list(wav_path.read_bytes())
            filename = '<img src=x onerror=alert(1)>' + 'very-long-recording-name-' * 12 + '.wav'
            page.locator("#drop-zone").evaluate("""(zone, data) => {
              const transfer = new DataTransfer();
              transfer.items.add(new File([new Uint8Array(data.bytes)], data.name, {type: 'audio/wav'}));
              zone.dispatchEvent(new DragEvent('drop', {dataTransfer: transfer, bubbles: true}));
            }""", {"bytes": payload, "name": filename})
            expect(page.locator("#file-name")).to_have_text(filename)
            assert page.locator("#file-name img").count() == 0
            passed("Drag-and-drop and safe filename rendering")

            for status in [409, 500]:
                page.route("**/v1/audio/transcriptions", lambda route, request, code=status: route.fulfill(status=code, json={"detail": "Test failure"}))
                page.locator("#transcribe-button").click()
                expect(page.locator("#transcription-status")).to_have_attribute("data-kind", "error")
                expect(page.locator("#transcription-status")).to_contain_text("another request" if status == 409 else "couldn’t finish")
                expect(page.locator("#transcribe-button")).to_be_enabled()
                page.unroute("**/v1/audio/transcriptions")
            passed("Busy and server errors restore controls")

            held = []
            page.route("**/v1/audio/transcriptions", lambda route: held.append(route))
            page.locator("#transcribe-button").click()
            expect(page.locator("#cancel-transcription")).to_be_visible()
            expect(page.locator("#audio-file")).to_be_disabled()
            page.locator("#speak-tab").click()
            expect(page.locator("#use-audio")).to_be_disabled()
            page.locator("#transcribe-tab").click()
            page.locator("#cancel-transcription").click()
            expect(page.locator("#transcription-status")).to_contain_text("Cancelled")
            expect(page.locator("#transcribe-button")).to_be_enabled()
            for route in held:
                route.abort()
            page.unroute("**/v1/audio/transcriptions")
            passed("Cancellation and protection against replacing an active upload")

            page.locator("#speak-tab").click()
            page.locator("#example-button").click()
            expect(page.locator("#speech-text")).not_to_have_value("")
            page.locator("#speech-text").fill("Your voice, right here on your local network.")
            started = time.perf_counter()
            with page.expect_request("**/v1/audio/speech") as request:
                page.locator("#generate-button").click()
            form = parse_qs(request.value.post_data, keep_blank_values=True)
            assert set(form) == {"text", "instruction"} and form["instruction"][0]
            expect(page.locator("#speech-status")).to_have_attribute("data-kind", "success", timeout=180000)
            report["timings_seconds"]["speech_with_direction"] = round(time.perf_counter() - started, 2)
            passed("Example text and real speech with voice direction")

            held.clear()
            page.route("**/v1/audio/speech", lambda route: held.append(route))
            page.locator("#generate-button").click()
            expect(page.locator("#cancel-speech")).to_be_visible()
            page.locator("#cancel-speech").click()
            expect(page.locator("#speech-status")).to_contain_text("Cancelled")
            expect(page.locator("#generate-button")).to_be_enabled()
            for route in held:
                route.abort()
            page.unroute("**/v1/audio/speech")
            page.route("**/v1/audio/speech", lambda route: route.fulfill(status=200,
                       headers={"X-Sample-Format": "s16le", "X-Sample-Rate": "24000"}, body=b"x"))
            page.locator("#generate-button").click()
            expect(page.locator("#speech-status")).to_have_attribute("data-kind", "error")
            expect(page.locator("#speech-status")).to_contain_text("incomplete")
            expect(page.locator("#audio-result")).to_be_visible()
            page.unroute("**/v1/audio/speech")
            passed("Speech cancellation and malformed PCM retain the last valid audio")

            page.locator("#transcribe-tab").click()
            page.route("**/v1/audio/transcriptions", lambda route: route.fulfill(
                status=200, json={"text": transcript, "duration": 7.2, "model": "test"}))
            page.locator("#transcribe-button").click()
            expect(page.locator("#transcription-status")).to_have_attribute("data-kind", "success")
            expect(page.locator("#transcript-meta")).to_contain_text(filename)
            page.unroute("**/v1/audio/transcriptions")

            for width in [390, 320, 768]:
                page.set_viewport_size({"width": width, "height": 844})
                for panel in ["speak", "transcribe"]:
                    page.locator(f"#{panel}-tab").click()
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (width, panel)
                if width == 390:
                    page.screenshot(path=str(OUTPUT / "mobile-transcript.png"), full_page=True)
                    page.locator("#speak-tab").click()
                    page.screenshot(path=str(OUTPUT / "mobile-speech.png"), full_page=True)
            passed("Phone and tablet layouts at 320, 390 and 768 pixels")

            contrast = page.locator("#upload-hint").evaluate("""element => {
              const luminance = color => {
                const rgb = color.match(/[\\d.]+/g).slice(0, 3).map(Number).map(v => v / 255)
                  .map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
                return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
              };
              const front = luminance(getComputedStyle(element).color);
              const back = luminance(getComputedStyle(element.parentElement).backgroundColor);
              return (Math.max(front, back) + .05) / (Math.min(front, back) + .05);
            }""")
            assert contrast >= 4.5, contrast
            report["helper_text_contrast"] = round(contrast, 2)
            passed("Helper text contrast and long transcript filename wrapping")

            assert not errors, errors
            assert not external, external
            passed("No browser JavaScript errors or external asset requests")
            context.close()
        finally:
            browser.close()
    (OUTPUT / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:7860")
    verify(parser.parse_args().url.rstrip("/"))
