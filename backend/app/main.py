import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import register_routes
from app.core.cache import RedisCache
from app.core.config import settings
from app.infra.notifier import Notifier
from app.infra.storage import SQLiteStore
from app.services.alerts import AlertEngine
from app.services.dashboard import DashboardState
from app.services.intraday import IntradayService
from app.services.scanner import ScannerService
from app.services.streaming import consume_market_events
from app.ws import WebSocketHub

logger = logging.getLogger("market_sentinel_backend")
logging.basicConfig(level=logging.INFO)


async def _periodic_history_flush(state: DashboardState, interval: int = 60) -> None:
    """Flush in-memory price deques to SQLite every `interval` seconds."""
    loop = asyncio.get_event_loop()
    while True:
        await asyncio.sleep(interval)
        await loop.run_in_executor(None, state.flush_history_to_db)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.store = SQLiteStore(settings.sqlite_db_path)
    app.state.cache = RedisCache(settings.redis_url)
    app.state.settings = settings
    app.state.dashboard_state = DashboardState(app.state.store, app.state.cache)
    app.state.notifier = Notifier()
    app.state.alert_engine = AlertEngine(
        app.state.store,
        app.state.cache,
        app.state.notifier,
        app.state.dashboard_state,
    )
    app.state.scanner = ScannerService()
    app.state.intraday = IntradayService()
    app.state.websocket_hub = WebSocketHub()
    consumer_task = asyncio.create_task(consume_market_events(app))
    flush_task = asyncio.create_task(
        _periodic_history_flush(app.state.dashboard_state)
    )

    yield

    consumer_task.cancel()
    flush_task.cancel()
    with suppress(asyncio.CancelledError):
        await consumer_task
    with suppress(asyncio.CancelledError):
        await flush_task
    # Final flush so the last ≤60 s of ticks are not lost on clean shutdown
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, app.state.dashboard_state.flush_history_to_db)


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

register_routes(app)
