import asyncio
import json
import logging
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone

from aiokafka import AIOKafkaConsumer
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.alerts import AlertEngine
from app.config import settings
from app.models import (
    AlertRulePayload,
    MarketEvent,
    SaveAlertRuleRequest,
    SaveTradePlanDraftRequest,
    StoredAlertRule,
    StoredTriggeredAlert,
    StoredTradePlanDraft,
    WatchlistMutation,
)
from app.cache import RedisCache
from app.notifier import Notifier
from app.state import DashboardState
from app.storage import SQLiteStore
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
                app.state.alert_engine.evaluate_market_event(event)
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
    app.state.store = SQLiteStore(settings.sqlite_db_path)
    app.state.cache = RedisCache(settings.redis_url)
    app.state.dashboard_state = DashboardState(app.state.store, app.state.cache)
    app.state.notifier = Notifier()
    app.state.alert_engine = AlertEngine(
        app.state.store,
        app.state.cache,
        app.state.notifier,
        app.state.dashboard_state,
    )
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
async def health() -> dict[str, object]:
    cache_ok = app.state.cache.ping()
    websocket_clients = len(app.state.websocket_hub._connections)
    return {
        "status": "ok",
        "service": "backend",
        "provider": settings.market_data_provider,
        "cache": "ok" if cache_ok else "degraded",
        "websocket_clients": websocket_clients,
    }


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


@app.get("/api/trade-plan-drafts/{user_id}", response_model=list[StoredTradePlanDraft])
async def list_trade_plan_drafts(user_id: str):
    rows = app.state.dashboard_state.list_trade_plan_drafts(user_id)
    return [
        StoredTradePlanDraft(
            ticker=row["ticker"],
            updated_at=row["updated_at"],
            payload=row["payload"],
        )
        for row in rows
    ]


@app.post("/api/trade-plan-drafts")
async def save_trade_plan_draft(payload: SaveTradePlanDraftRequest):
    updated_at = datetime.now(timezone.utc).isoformat()
    app.state.dashboard_state.save_trade_plan_draft(
        payload.user_id,
        payload.draft.model_dump(),
        updated_at,
    )
    return {"ok": True, "updated_at": updated_at}


@app.get("/api/alert-rules/{user_id}", response_model=list[StoredAlertRule])
async def list_alert_rules(user_id: str):
    rows = app.state.dashboard_state.list_alert_rules(user_id)
    return [
        StoredAlertRule(
            ticker=row["ticker"],
            updated_at=row["updated_at"],
            payload=row["payload"],
        )
        for row in rows
    ]


@app.post("/api/alert-rules")
async def save_alert_rule(payload: SaveAlertRuleRequest):
    updated_at = datetime.now(timezone.utc).isoformat()
    app.state.dashboard_state.save_alert_rule(
        payload.user_id,
        payload.rule.model_dump(),
        updated_at,
    )
    return {"ok": True, "updated_at": updated_at}


@app.get("/api/triggered-alerts/{user_id}", response_model=list[StoredTriggeredAlert])
async def list_triggered_alerts(user_id: str, limit: int = 20):
    rows = app.state.alert_engine.list_triggered_alerts(user_id, limit=limit)
    return [
        StoredTriggeredAlert(
            ticker=row["ticker"],
            triggered_at=row["triggered_at"],
            payload=row["payload"],
        )
        for row in rows
    ]


@app.get("/api/stocks/{ticker}/history")
async def get_stock_history(ticker: str, range: str = "1M"):
    return {
        "ticker": ticker.upper(),
        "range": range,
        "candles": app.state.dashboard_state.build_history(ticker, range),
    }


@app.websocket("/ws/dashboard")
async def dashboard_socket(websocket: WebSocket) -> None:
    await app.state.websocket_hub.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        app.state.websocket_hub.disconnect(websocket)
