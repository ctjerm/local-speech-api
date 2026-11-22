"""Static website delivery, independent of the model and API implementations."""

from hashlib import sha256
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def mount_website(
    app: FastAPI,
    directory: Path,
    *,
    https_port: int | None = None,
    ca_certificate: Path | None = None,
) -> None:
    app.mount("/assets", StaticFiles(directory=directory), name="website-assets")

    @app.get("/", include_in_schema=False)
    async def website():
        return FileResponse(directory / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/site-config", include_in_schema=False)
    async def site_config():
        return {
            "https_port": https_port,
            "local_certificate": bool(ca_certificate),
            "ca_sha256": sha256(ca_certificate.read_bytes()).hexdigest().upper()
            if ca_certificate
            else None,
        }

    if ca_certificate:

        @app.get("/setup/local-ca.cer", include_in_schema=False)
        async def public_certificate():
            return FileResponse(
                ca_certificate,
                media_type="application/x-x509-ca-cert",
                filename="voice-room-local-ca.cer",
            )
