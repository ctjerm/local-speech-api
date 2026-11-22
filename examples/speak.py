"""Call the speech API and save its streaming PCM response as a WAV file.

Uses only Python's standard library. Run with --help for arguments.
"""

import argparse
import wave
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def synthesize(base_url: str, text: str, instruction: str, output: Path) -> None:
    form = urlencode(
        {
            "text": text,
            "instruction": instruction,
        }
    )
    request = Request(
        base_url.rstrip("/") + "/v1/audio/speech",
        data=form.encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        response = urlopen(request, timeout=300)
    except HTTPError as error:
        raise RuntimeError(
            f"Speech API returned HTTP {error.code}: {error.read().decode('utf-8')}"
        ) from error
    # Read the complete response before writing so a broken stream cannot leave a WAV.
    with closing(response):
        if response.headers.get("X-Sample-Format") != "s16le":
            raise ValueError("The server returned an unsupported audio format.")
        sample_rate = int(response.headers["X-Sample-Rate"])
        pcm = response.read()
    if not pcm or len(pcm) % 2:
        raise ValueError("The server returned empty or incomplete PCM audio.")
    with wave.open(str(output), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(pcm)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text")
    parser.add_argument("--url", default="http://localhost:7860")
    parser.add_argument(
        "--instruction", default="A warm, clear English narrator with a calm delivery."
    )
    parser.add_argument("--output", type=Path, default=Path("speech.wav"))
    args = parser.parse_args()
    synthesize(args.url, args.text, args.instruction, args.output)
    print(f"Saved {args.output}")
