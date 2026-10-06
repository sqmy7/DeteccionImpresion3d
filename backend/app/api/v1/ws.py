import json

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.api.deps import get_current_user_ws
from app.db.models import User
from app.ws.manager import manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, current_user: User = Depends(get_current_user_ws)) -> None:
    await manager.connect(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if message.get("action") == "subscribe":
                manager.subscribe(websocket, message.get("printer_ids"))
    except WebSocketDisconnect:
        manager.disconnect(websocket)
