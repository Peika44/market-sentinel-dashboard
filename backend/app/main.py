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
from app.services.streaming import consume_market_events
from app.ws import WebSocketHub

logger = logging.getLogger("market_sentinel_backend")
logging.basicConfig(level=logging.INFO)


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

register_routes(app)
