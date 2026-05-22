import asyncio
import json
import logging
from contextlib import asynccontextmanager, suppress

from aiokafka import AIOKafkaConsumer
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.models import MarketEvent, WatchlistMutation
from app.state import DashboardState
from app.ws import WebSocketHub

logger = logging.getLogger("market_sentinel_backend")
logging.basicConfig(level=logging.INFO)


async def consume_market_events(app: FastAPI) -> None:
    while True:
        consumer: AIOKafkaConsumer | None = None
        try:
            consumer = AIOKafkaConsumer(
                settings.kafka_topic,
                bootstrap_servers=settings.kafka_bootstrap_servers,
                group_id="market-sentinel-dashboard",
                auto_offset_reset="latest",
                value_deserializer=lambda payload: json.loads(payload.decode("utf-8")),
            )
            await consumer.start()
            logger.info("Kafka consumer connected to %s", settings.kafka_bootstrap_servers)

            async for message in consumer:
                event = MarketEvent.model_validate(message.value)
                app.state.dashboard_state.apply_event(event)
                await app.state.websocket_hub.broadcast(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Consumer loop interrupted: %s", exc)
            await asyncio.sleep(3)
        finally:
            if consumer is not None:
                with suppress(Exception):
                    await consumer.stop()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.dashboard_state = DashboardState()
    app.state.websocket_hub = WebSocketHub()
    consumer_task = asyncio.create_task(consume_market_events(app))

    yield

    consumer_task.cancel()
    with suppress(asyncio.CancelledError):
        await consumer_task


app = FastAPI(
    title="Market Sentinel Dashboard API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "backend"}


@app.get("/api/dashboard/{user_id}")
async def get_dashboard(user_id: str):
    return app.state.dashboard_state.build_snapshot(user_id)


@app.get("/api/market-overview")
async def get_market_overview():
    return {"indices": app.state.dashboard_state.build_overview()}


@app.post("/api/watchlist")
async def add_to_watchlist(payload: WatchlistMutation):
    app.state.dashboard_state.add_to_watchlist(payload.user_id, payload.ticker)
    return app.state.dashboard_state.build_snapshot(payload.user_id)


@app.delete("/api/watchlist/{user_id}/{ticker}")
async def remove_from_watchlist(user_id: str, ticker: str):
    app.state.dashboard_state.remove_from_watchlist(user_id, ticker)
    return app.state.dashboard_state.build_snapshot(user_id)


@app.websocket("/ws/dashboard")
async def dashboard_socket(websocket: WebSocket) -> None:
    await app.state.websocket_hub.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        app.state.websocket_hub.disconnect(websocket)

