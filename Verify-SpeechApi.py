"""End-to-end verification of both real models through the public API."""

import argparse
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import numpy as np
import soundfile as sf


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:7860")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    output = root / "runtime/verification"
    output.mkdir(exist_ok=True, parents=True)
    report = {}
    with httpx.Client(base_url=args.url, timeout=300, trust_env=False) as client:
        report["health"] = client.get("/health").json()
        schema = client.get("/openapi.json").json()
        assert {"/v1/audio/speech", "/v1/audio/speech/batch", "/v1/audio/transcriptions"} <= schema[
            "paths"
        ].keys()
        source = output / "breeze/voice-design.wav"
        data, rate = sf.read(source)

        def transcribe(payload):
            before = time.perf_counter()
            result = client.post(
                "/v1/audio/transcriptions", files={"file": ("audio.wav", payload, "audio/wav")}
            )
            result.raise_for_status()
            return {**result.json(), "request_seconds": round(time.perf_counter() - before, 3)}

        report["transcription"] = transcribe(source.read_bytes())
        assert "local network" in report["transcription"]["text"].lower()
        stereo = io.BytesIO()
        sf.write(stereo, np.column_stack([data, data]), rate, format="FLAC")
        report["stereo_flac"] = transcribe(stereo.getvalue())
        assert "local network" in report["stereo_flac"]["text"].lower()
        long_audio = io.BytesIO()
        sf.write(long_audio, np.tile(data, 5), rate, format="WAV")
        report["chunked_audio"] = transcribe(long_audio.getvalue())
        assert report["chunked_audio"]["duration"] > 30
        assert report["chunked_audio"]["text"].lower().count("local network") == 5

        # Exercise both GPU models concurrently after both have loaded.
        def speak():
            before = time.perf_counter()
            result = client.post(
                "/v1/audio/speech",
                data={
                    "text": "Both speech models are working together on this computer.",
                    "instruction": "A clear, friendly English voice.",
                },
            )
            result.raise_for_status()
            assert result.headers["x-sample-rate"] == "24000"
            assert result.headers["x-sample-format"] == "s16le"
            samples = np.frombuffer(result.content, dtype="<i2")
            assert len(samples) > 2400 and np.max(np.abs(samples.astype(float))) > 100
            path = output / "roundtrip.wav"
            sf.write(path, samples, 24000, subtype="PCM_16")
            return {
                "request_seconds": round(time.perf_counter() - before, 3),
                "audio_seconds": len(samples) / 24000,
                "bytes": len(result.content),
            }

        with ThreadPoolExecutor() as pool:
            speech = pool.submit(speak)
            report["concurrent_transcription"] = transcribe(long_audio.getvalue())
            report["speech"] = speech.result()
        report["roundtrip"] = transcribe((output / "roundtrip.wav").read_bytes())
        assert "speech models" in report["roundtrip"]["text"].lower()
        assert (
            client.post("/v1/audio/transcriptions", files={"file": ("bad.wav", b"bad")}).status_code
            == 400
        )
        assert client.post("/v1/audio/transcriptions").status_code == 422
        assert client.get("/health").status_code == 200
    (output / "unified-api.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
