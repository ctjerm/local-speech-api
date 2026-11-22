import argparse
import asyncio
from pathlib import Path

import httpx
from hypercorn.asyncio import serve

from .app import create_app
from .server import server_config
from .speech.breeze import BreezeSpeechGenerator
from .speech.breeze_compat import mount_breeze_compat
from .transcription.parakeet import ParakeetTranscriber
from .transcription.parakeet_config import ParakeetConfig
from .website import mount_website


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--worker-port", type=int, default=7861)
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--https-port", type=int, default=8443)
    parser.add_argument("--certificate")
    parser.add_argument("--key")
    parser.add_argument("--ca-certificate")
    args = parser.parse_args()
    asyncio.run(run(args))


async def run(args):
    config = server_config(args.port, args.https_port, args.certificate, args.key)
    backend = ParakeetTranscriber(ParakeetConfig(model_path=args.model))
    async with httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{args.worker_port}",
        timeout=httpx.Timeout(600, connect=5),
        trust_env=False,
    ) as worker:
        app = create_app(backend, BreezeSpeechGenerator(worker))
        await mount_breeze_compat(app, worker)
        mount_website(
            app,
            Path(__file__).resolve().parents[2] / "web",
            https_port=args.https_port if args.certificate else None,
            ca_certificate=Path(args.ca_certificate) if args.ca_certificate else None,
        )
        await serve(app, config)


if __name__ == "__main__":
    main()
