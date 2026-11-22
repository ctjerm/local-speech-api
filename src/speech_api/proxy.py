"""Streaming HTTP forwarding with explicit upstream connection ownership."""

import httpx
from fastapi import HTTPException, Request
from starlette.responses import StreamingResponse

HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "host",
}


def forwarded_headers(headers):
    excluded = HOP_HEADERS | {
        name.strip().lower() for name in headers.get("connection", "").split(",")
    }
    return {key: value for key, value in headers.items() if key.lower() not in excluded}


class UpstreamResponse(StreamingResponse):
    def __init__(self, response: httpx.Response):
        self.upstream = response
        super().__init__(
            response.aiter_raw(),
            status_code=response.status_code,
            headers=forwarded_headers(response.headers),
        )

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.upstream.aclose()


def proxy_handler(client: httpx.AsyncClient, path: str):
    async def forward(request: Request):
        outgoing = client.build_request(
            request.method,
            path,
            params=request.query_params,
            headers=forwarded_headers(request.headers),
            content=request.stream(),
        )
        try:
            response = await client.send(outgoing, stream=True)
        except httpx.TimeoutException as error:
            raise HTTPException(504, "Speech generation worker timed out.") from error
        except httpx.HTTPError as error:
            raise HTTPException(502, "Speech generation worker is unavailable.") from error
        return UpstreamResponse(response)

    return forward
