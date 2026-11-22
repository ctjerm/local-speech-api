"""Exercise browser recording with a simulated microphone; never use physical input."""

import argparse
import json
import os
import time
import wave
from hashlib import sha256
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "runtime" / "verification" / "microphone"
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(ROOT / "runtime" / "browser-qa" / "browsers")
os.environ["TEMP"] = os.environ["TMP"] = str(ROOT / "runtime" / "scratch" / "temp")
OUTPUT.mkdir(parents=True, exist_ok=True)


def verify(address: str):
    lan = f"http://{address}:7860"
    secure = f"https://{address}:8443/"
    report = {"checks": [], "physical_microphone": False}
    errors = []

    def passed(name):
        report["checks"].append(name)
        print(f"PASS {name}", flush=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--use-fake-device-for-media-stream",
                "--use-fake-ui-for-media-stream",
                f"--use-file-for-fake-audio-capture={ROOT / 'runtime/verification/website/speech.wav'}",
            ],
        )
        try:
            context = browser.new_context(
                permissions=["microphone"], viewport={"width": 1366, "height": 1100}
            )
            context.add_init_script("""(() => {
              if (!navigator.mediaDevices) return;
              window.testTracks = [];
              const get = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
              window.testGetMedia = async options => {
                const stream = await get(options); testTracks.push(...stream.getTracks()); return stream;
              };
              navigator.mediaDevices.getUserMedia = window.testGetMedia;
            })();""")
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"{lan}/", wait_until="networkidle")
            page.locator("#transcribe-tab").click()
            expect(page.locator("#microphone-button")).to_be_disabled()
            expect(page.locator("#microphone-status")).to_contain_text("HTTPS")
            expect(page.locator("#secure-website")).to_have_attribute("href", secure)
            passed("HTTP LAN shows the HTTPS requirement and usable secure link")

            page.goto(secure, wait_until="networkidle")
            assert page.evaluate("window.isSecureContext")
            bounded = page.evaluate("""async () => {
              const source = await (await fetch('/assets/recording/pcm-worklet.js')).text();
              let Processor;
              class Base { constructor() { this.messages = []; this.port = {postMessage: data => this.messages.push(data)}; } }
              new Function('AudioWorkletProcessor', 'registerProcessor', source)(Base, (_, value) => { Processor = value; });
              const processor = new Processor({processorOptions: {maxFrames: 3}});
              processor.process([[new Float32Array([-1, 0, 1, .5])]]);
              processor.process([[new Float32Array([1, 1])]]);
              const pcm = processor.messages.find(x => x.type === 'pcm');
              const view = new DataView(pcm.bytes);
              return {frames: pcm.frames, samples: [0, 2, 4].map(n => view.getInt16(n, true)),
                      completed: processor.messages.filter(x => x.type === 'done').length};
            }""")
            assert bounded == {"frames": 3, "samples": [-32768, 0, 32767], "completed": 1}
            passed("PCM sample encoding, partial-buffer flush and bounded recording completion")
            page.locator("#transcribe-tab").click()
            expect(page.locator("#microphone-button")).to_be_enabled()
            page.locator("#microphone-button").click()
            expect(page.locator("#microphone-label")).to_have_text("Stop recording")
            expect(page.locator("#transcribe-button")).to_be_disabled()
            expect(page.locator("#audio-file")).to_be_disabled()
            expect(page.locator("#audio-file")).to_have_css("opacity", "0")
            page.wait_for_function(
                "document.querySelector('#recording-timer').textContent === '0:06'", timeout=15000
            )
            page.screenshot(path=str(OUTPUT / "recording-desktop.png"), full_page=True)
            page.locator("#microphone-button").click()
            expect(page.locator("#microphone-status")).to_contain_text("Recording ready")
            expect(page.locator("#file-name")).to_contain_text("microphone-")
            page.wait_for_function("testTracks.every(t => t.readyState === 'ended')")
            page.wait_for_function("document.querySelector('#upload-player').duration > 5")
            payload = page.locator("#upload-player").evaluate(
                "async audio => Array.from(new Uint8Array(await (await fetch(audio.src)).arrayBuffer()))"
            )
            path = OUTPUT / "microphone.wav"
            path.write_bytes(bytes(payload))
            with wave.open(str(path)) as audio:
                assert (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) == (
                    1,
                    2,
                    16000,
                )
                assert audio.getnframes() > 80000
            started = time.perf_counter()
            page.locator("#transcribe-button").click()
            expect(page.locator("#microphone-button")).to_be_disabled()
            expect(page.locator("#transcription-status")).to_have_attribute(
                "data-kind", "success", timeout=60000
            )
            report["transcription_seconds"] = round(time.perf_counter() - started, 2)
            report["transcript"] = page.locator("#transcript-text").input_value()
            assert "local audio studio" in report["transcript"].lower(), report["transcript"]
            passed(
                "Trusted HTTPS capture, timer, mono 16 kHz WAV, preview, track release and real transcription"
            )

            previous = page.locator("#file-name").inner_text()
            page.locator("#microphone-button").click()
            expect(page.locator("#microphone-label")).to_have_text("Stop recording")
            page.locator("#cancel-recording").click()
            expect(page.locator("#microphone-status")).to_contain_text("cancelled")
            expect(page.locator("#file-name")).to_have_text(previous)
            assert page.evaluate("testTracks.every(t => t.readyState === 'ended')")
            passed("Cancel releases capture and preserves the previous recording")

            for name in ["NotAllowedError", "NotFoundError", "NotReadableError"]:
                page.evaluate(
                    "name => navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('test', name); }",
                    name,
                )
                page.locator("#microphone-button").click()
                expect(page.locator("#microphone-status")).to_have_attribute("data-kind", "error")
                expect(page.locator("#microphone-button")).to_be_enabled()
                expect(page.locator("#file-name")).to_have_text(previous)
            passed("Permission denied, missing device and unavailable device recover cleanly")

            page.evaluate(
                "() => { navigator.mediaDevices.getUserMedia = options => new Promise(resolve => { window.releasePermission = () => testGetMedia(options).then(resolve); }); }"
            )
            page.locator("#microphone-button").click()
            page.wait_for_function("typeof window.releasePermission === 'function'")
            page.locator("#cancel-recording").click()
            page.evaluate("window.releasePermission()")
            page.wait_for_function("testTracks.every(t => t.readyState === 'ended')")
            expect(page.locator("#microphone-button")).to_be_enabled()
            passed("Permission granted after cancellation immediately releases the microphone")

            page.evaluate("() => { navigator.mediaDevices.getUserMedia = window.testGetMedia; }")
            page.locator("#microphone-button").click()
            expect(page.locator("#microphone-label")).to_have_text("Stop recording")
            page.evaluate("testTracks.at(-1).dispatchEvent(new Event('ended'))")
            expect(page.locator("#microphone-status")).to_contain_text("disconnected")
            assert page.evaluate("testTracks.every(t => t.readyState === 'ended')")
            passed("Device disconnection stops capture and reports recovery guidance")

            page.locator("#microphone-button").click()
            expect(page.locator("#microphone-label")).to_have_text("Stop recording")
            page.evaluate("dispatchEvent(new PageTransitionEvent('pagehide'))")
            expect(page.locator("#microphone-status")).to_contain_text("cancelled")
            assert page.evaluate("testTracks.every(t => t.readyState === 'ended')")
            passed("Leaving the page releases capture")

            for width in [320, 390, 768]:
                page.set_viewport_size({"width": width, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(OUTPUT / "recording-mobile.png"), full_page=True)
            passed("Microphone controls fit phone and tablet layouts")

            page.goto("http://localhost:7860/", wait_until="networkidle")
            page.locator("#transcribe-tab").click()
            expect(page.locator("#microphone-button")).to_be_enabled()
            page.locator("#microphone-button").click()
            expect(page.locator("#microphone-label")).to_have_text("Stop recording")
            page.locator("#cancel-recording").click()
            assert page.evaluate("testTracks.every(t => t.readyState === 'ended')")
            passed("Localhost recording also works without HTTPS")
            page.goto(f"{lan}/assets/recording/setup.html", wait_until="networkidle")
            expect(page.locator("#certificate-fingerprint")).to_have_text(
                sha256((ROOT / "runtime/tls/local-ca.cer").read_bytes()).hexdigest().upper()
            )
            expect(page.locator("#open-secure-studio")).to_have_attribute("href", secure)
            with page.expect_download() as download:
                page.locator("#certificate-download").click()
            certificate_path = OUTPUT / "public-certificate.cer"
            download.value.save_as(certificate_path)
            assert certificate_path.read_bytes() == (ROOT / "runtime/tls/local-ca.cer").read_bytes()
            passed("Device setup page and exact public certificate download")
            assert not errors, errors
            context.close()
        finally:
            browser.close()
    (OUTPUT / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", required=True, help="This PC's LAN IP, as passed to Setup-Https.ps1")
    verify(parser.parse_args().address)
