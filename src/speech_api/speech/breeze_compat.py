"""Keep optional Breeze-only routes separate from the stable speech API."""

import httpx
from fastapi import FastAPI

from ..proxy import proxy_handler


async def mount_breeze_compat(app: FastAPI, client: httpx.AsyncClient):
    paths = {"/v1/audio/speech/batch": ["POST"], "/v1/model": ["GET"]}
    response = await client.get("/openapi.json", timeout=10)
    response.raise_for_status()
    upstream = response.json()
    for path, methods in paths.items():
        app.add_api_route(
            path, proxy_handler(client, path), methods=methods, include_in_schema=False
        )
    original_openapi = app.openapi

    def openapi():
        schema = original_openapi()
        for path, methods in paths.items():
            schema["paths"][path] = {
                method.lower(): upstream["paths"][path][method.lower()] for method in methods
            }
        for category, values in upstream.get("components", {}).items():
            for name, value in values.items():
                schema.setdefault("components", {}).setdefault(category, {}).setdefault(name, value)
        return schema

    app.openapi = openapi
