from fastapi import WebSocket

from app.domain.models import MarketEvent


class WebSocketHub:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)
        await websocket.send_json(
            {
                "type": "connected",
                "message": "dashboard stream ready",
            }
        )

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)

    async def broadcast(self, event: MarketEvent) -> None:
        stale: list[WebSocket] = []
        payload = event.model_dump(mode="json")

        for websocket in list(self._connections):
            try:
                await websocket.send_json(payload)
            except Exception:
                stale.append(websocket)

        for websocket in stale:
            self.disconnect(websocket)
