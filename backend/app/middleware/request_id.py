"""Per-request correlation ID.

A pure-ASGI middleware (so the contextvar reliably propagates into route
handlers and every log line they emit, unlike ``BaseHTTPMiddleware`` which can
run the endpoint in a separate context). Each request gets a UUID — or reuses an
inbound ``X-Request-ID`` for cross-service tracing — exposed on
``request.state.request_id`` and echoed back in the ``X-Request-ID`` response
header. The structured logger reads the contextvar (see app.utils.logging).
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Read by JsonFormatter to stamp request_id onto every log line in scope.
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

REQUEST_ID_HEADER = b"x-request-id"


class RequestIDMiddleware:
    """Assign/propagate a correlation ID for each HTTP request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        inbound = headers.get(REQUEST_ID_HEADER)
        request_id = inbound.decode() if inbound else str(uuid.uuid4())

        # Expose on request.state for handlers that want it.
        scope.setdefault("state", {})
        scope["state"]["request_id"] = request_id

        token = request_id_ctx.set(request_id)

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers") or [])
                response_headers.append((REQUEST_ID_HEADER, request_id.encode()))
                message["headers"] = response_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            request_id_ctx.reset(token)
