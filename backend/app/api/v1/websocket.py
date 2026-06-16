"""WebSocket endpoint for real-time job/agent updates.

Authentication is by JWT passed as a ``token`` query parameter, because the
WebSocket handshake (unlike HTTP requests from our clients) cannot carry an
``Authorization`` header. The token is validated exactly like a normal access
token; the connection is then bound to the caller's organisation.

Close codes: 4001 = invalid/expired token or unknown user; 4003 = token valid
but for a different organisation than the one requested.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import User
from app.services.websocket_manager import ws_manager
from app.utils.security import decode_access_token

logger = logging.getLogger("counseliq.ws.endpoint")

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{organisation_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    organisation_id: str,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Stream organisation-scoped events to an authenticated client.

    The client may send the text ``ping`` and will receive ``{"type":"pong"}``;
    all other inbound messages are ignored. Auth is via the ``token`` query
    parameter (see module docstring).
    """
    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        await websocket.close(code=4001)
        return

    try:
        user_id = UUID(str(payload["sub"]))
    except (ValueError, TypeError):
        await websocket.close(code=4001)
        return

    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        await websocket.close(code=4001)
        return

    if str(user.organisation_id) != organisation_id:
        await websocket.close(code=4003)
        return

    await ws_manager.connect(websocket, organisation_id)
    await websocket.send_json(
        {
            "type": "connected",
            "organisation_id": organisation_id,
            "user_id": str(user.id),
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, organisation_id)
