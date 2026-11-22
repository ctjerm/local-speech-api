r"""Exercise the running API and retain a small WAV plus a JSON verification record.

Run with runtime\breeze\.venv\Scripts\python.exe Verify-Breeze.py from this project.
"""

import argparse
import json
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import numpy as np


def save_audio(path: Path, pcm: bytes, sample_rate: int) -> dict:
    assert sample_rate == 24000, sample_rate
    assert pcm and len(pcm) % 2 == 0, "Empty or incomplete PCM"
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
    duration = len(samples) / sample_rate
    rms = float(np.sqrt(np.mean(samples**2)))
    assert 0.25 < duration < 40, duration
    assert rms > 0.001, f"Audio is silent: RMS={rms}"
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm)
    return {"bytes": len(pcm), "duration_seconds": duration, "rms": rms}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:7860")
    parser.add_argument("--lan-url", required=True, help="This PC's LAN address, e.g. http://<server-ip>:7860")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "runtime/verification/breeze")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"url": args.url, "lan_url_on_this_pc": args.lan_url, "remote_lan_test": "not performed"}
    with httpx.Client(base_url=args.url, timeout=300, trust_env=False) as client:
        health = client.get("/health")
        health.raise_for_status()
        assert health.json()["status"] == "ok" and health.json()["sample_rate"] == 24000, health.text
        report["health"] = health.json()
        info = client.get("/v1/model")
        info.raise_for_status()
        report["model"] = info.json()
        assert len(report["model"]["model_digest"]) == 64
        for path in ("/docs", "/openapi.json"):
            response = client.get(path)
            response.raise_for_status()
        with httpx.Client(timeout=10, trust_env=False) as lan_client:
            lan_health = lan_client.get(args.lan_url + "/health")
            lan_health.raise_for_status()
            assert lan_health.json()["status"] == "ok"
        report["self_lan_health"] = "passed"

        rejection_codes = []
        for form, expected in (({}, 422), ({"text": " "}, 422),
                               ({"text": "Test", "cfg_scale": "0"}, 422),
                               ({"text": "Test", "cfg_scale": "NaN"}, 422),
                               ({"text": "Test", "seed": "-1"}, 422),
                               ({"text": "Test", "ref_text": "Missing audio"}, 400)):
            response = client.post("/v1/audio/speech", data=form)
            assert response.status_code == expected, response.text
            rejection_codes.append(response.status_code)
        report["invalid_input_statuses"] = rejection_codes

        text = "Hello. Breeze is now running on your local network. You can call this API to generate speech."
        form = {"text": text, "instruction": "A warm, clear English narrator with a calm delivery.",
                "cfg_scale": "4", "seed": "42"}
        start = time.perf_counter()
        chunks = []
        first_audio = None
        # A separate client sends a competing request while synthesis owns the slot.
        def check_concurrency():
            with httpx.Client(base_url=args.url, timeout=30, trust_env=False) as competing:
                conflict = competing.post("/v1/audio/speech", data={"text": "A competing request."})
                assert conflict.status_code == 409, conflict.text
                ready = competing.get("/health")
                ready.raise_for_status()
                return {"conflict_status": conflict.status_code, "health_status": ready.status_code}

        with ThreadPoolExecutor(max_workers=1) as pool:
            with client.stream("POST", "/v1/audio/speech", data=form) as response:
                response.raise_for_status()
                assert response.headers["x-sample-format"] == "s16le"
                concurrent = pool.submit(check_concurrency)
                for chunk in response.iter_bytes():
                    if chunk:
                        if first_audio is None:
                            first_audio = time.perf_counter() - start
                        chunks.append(chunk)
                elapsed = time.perf_counter() - start
                sample_rate = int(response.headers["x-sample-rate"])
            report["concurrency"] = concurrent.result()
        sample = args.output / "voice-design.wav"
        report["voice_design"] = save_audio(sample, b"".join(chunks), sample_rate)
        report["voice_design"].update(first_audio_seconds=first_audio, total_seconds=elapsed)

        # A reference upload exercises a different path: audio decoding and voice conditioning.
        start = time.perf_counter()
        with sample.open("rb") as reference:
            cloned = client.post(
                "/v1/audio/speech",
                data={"text": "This is a second request using the reference voice.", "ref_text": text, "seed": "42"},
                files={"ref_audio": ("reference.wav", reference, "audio/wav")},
            )
        cloned.raise_for_status()
        elapsed = time.perf_counter() - start
        report["voice_clone"] = save_audio(args.output / "voice-clone.wav", cloned.content,
                                            int(cloned.headers["x-sample-rate"]))
        report["voice_clone"]["total_seconds"] = elapsed
        assert client.get("/health").json()["status"] == "ok"
    record = args.output / "verification.json"
    record.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
