"""Upload an audio file to the local API using only Python's standard library."""

import argparse
import json
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def transcribe(base_url: str, audio: Path) -> dict:
    boundary = "audio" + uuid.uuid4().hex
    header = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode()
    body = header + audio.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    request = Request(
        base_url.rstrip("/") + "/v1/audio/transcriptions",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urlopen(request, timeout=300) as response:
            return json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"API returned HTTP {error.code}: {error.read().decode()}") from error


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--url", default="http://localhost:7860")
    args = parser.parse_args()
    print(json.dumps(transcribe(args.url, args.file), ensure_ascii=False, indent=2))
