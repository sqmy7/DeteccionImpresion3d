import json
import logging
from datetime import datetime, timezone

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        # None = no filter (receive every event); otherwise the set of printer_ids to receive.
        self._connections: dict[WebSocket, set[int] | None] = {}

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[websocket] = None

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.pop(websocket, None)

    def subscribe(self, websocket: WebSocket, printer_ids: list[int] | None) -> None:
        self._connections[websocket] = set(printer_ids) if printer_ids else None

    async def broadcast(self, event_type: str, data: dict) -> None:
        envelope = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        message = json.dumps(envelope)
        printer_id = data.get("printer_id")

        for websocket, printer_filter in list(self._connections.items()):
            if printer_filter is not None and printer_id is not None and printer_id not in printer_filter:
                continue
            try:
                await websocket.send_text(message)
            except Exception:
                logger.warning("Dropping WS connection after failed send", exc_info=True)
                self.disconnect(websocket)


manager = ConnectionManager()
