import asyncio
import json
import os
import random
from contextlib import suppress
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from aiokafka import AIOKafkaProducer
from redis import Redis
import websockets

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "market-prices")
PUBLISH_INTERVAL_SECONDS = float(os.getenv("PUBLISH_INTERVAL_SECONDS", "1.0"))
MARKET_DATA_PROVIDER = os.getenv("MARKET_DATA_PROVIDER", "synthetic").lower()
ALPACA_API_KEY_ID = os.getenv("APCA_API_KEY_ID", "")
ALPACA_SECRET_KEY = os.getenv("APCA_API_SECRET_KEY", "")
ALPACA_FEED = os.getenv("ALPACA_FEED", "iex")
ALPACA_WS_URL = os.getenv(
    "ALPACA_WS_URL",
    f"wss://stream.data.alpaca.markets/v2/{ALPACA_FEED}",
)
ALPACA_DATA_URL = os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets")
ALPACA_TRADING_URL = os.getenv("ALPACA_TRADING_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
TARGET_SYNC_INTERVAL_SECONDS = float(os.getenv("TARGET_SYNC_INTERVAL_SECONDS", "5.0"))

DEFAULT_SYMBOLS = {
    "AAPL": {"display_name": "Apple", "base": 212.10},
    "MSFT": {"display_name": "Microsoft", "base": 428.55},
    "NVDA": {"display_name": "NVIDIA", "base": 116.40},
    "TSLA": {"display_name": "Tesla", "base": 177.25},
    "AMZN": {"display_name": "Amazon", "base": 188.30},
    "META": {"display_name": "Meta", "base": 507.80},
    "SPY": {"display_name": "S&P 500 ETF", "base": 530.10},
    "QQQ": {"display_name": "Nasdaq 100 ETF", "base": 456.20},
    "IWM": {"display_name": "Russell 2000 ETF", "base": 208.35},
}

ACTIVE_TICKERS_CACHE_KEY = "market_feed:active_tickers"
BASELINE_CACHE_KEY = "alpaca:snapshot_baselines"


async def build_producer() -> AIOKafkaProducer:
    while True:
        try:
            producer = AIOKafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            )
            await producer.start()
            return producer
        except Exception as exc:
            print(f"Producer connection failed: {exc}. Retrying in 3s.")
            await asyncio.sleep(3)


async def publish_event(producer: AIOKafkaProducer, payload: dict) -> None:
    await producer.send_and_wait(
        KAFKA_TOPIC,
        json.dumps(payload).encode("utf-8"),
    )


def default_target_symbols() -> list[str]:
    return sorted(DEFAULT_SYMBOLS.keys())


def get_redis_client() -> Redis:
    return Redis.from_url(REDIS_URL, decode_responses=True)


def load_requested_symbols(redis_client: Redis | None = None) -> list[str]:
    try:
        redis_client = redis_client or get_redis_client()
        payload = redis_client.get(ACTIVE_TICKERS_CACHE_KEY)
        if not payload:
            print(f"cache MISS {ACTIVE_TICKERS_CACHE_KEY}")
            return default_target_symbols()
        decoded = json.loads(payload)
    except Exception as exc:
        print(f"Redis active tickers read failed: {exc}")
        return default_target_symbols()

    if isinstance(decoded, dict):
        raw_tickers = decoded.get("tickers", [])
    elif isinstance(decoded, list):
        raw_tickers = decoded
    else:
        raw_tickers = []

    tickers = sorted({str(ticker).strip().upper() for ticker in raw_tickers if str(ticker).strip()})
    return tickers or default_target_symbols()


async def run_synthetic(producer: AIOKafkaProducer) -> None:
    redis_client = get_redis_client()
    current_prices = {
        symbol: float(meta["base"])
        for symbol, meta in DEFAULT_SYMBOLS.items()
    }
    anchors = current_prices.copy()

    while True:
        for symbol in load_requested_symbols(redis_client):
            meta = DEFAULT_SYMBOLS.get(
                symbol,
                {"display_name": symbol, "base": current_prices.get(symbol, 100.0)},
            )
            base_price = float(meta["base"])
            current_prices.setdefault(symbol, base_price)
            anchors.setdefault(symbol, base_price)

            move = random.uniform(-0.0045, 0.0045)
            current_prices[symbol] = max(
                base_price * 0.65,
                current_prices[symbol] * (1.0 + move),
            )
            current_price = round(current_prices[symbol], 2)
            change_pct = round(
                ((current_price - anchors[symbol]) / anchors[symbol]) * 100.0,
                2,
            )
            payload = {
                "type": "price_update",
                "ticker": symbol,
                "display_name": str(meta["display_name"]),
                "current_price": current_price,
                "change_pct": change_pct,
                "volume": random.randint(50_000, 2_500_000),
                "as_of": datetime.now(timezone.utc).isoformat(),
            }
            await publish_event(producer, payload)

        await asyncio.sleep(PUBLISH_INTERVAL_SECONDS)


def alpaca_trading_base_urls() -> list[str]:
    candidates = [
        ALPACA_TRADING_URL.strip(),
        "https://paper-api.alpaca.markets",
        "https://api.alpaca.markets",
    ]
    urls: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = candidate.rstrip("/")
        if not normalized or normalized in seen:
            continue
        urls.append(normalized)
        seen.add(normalized)
    return urls


def load_alpaca_snapshots(
    symbols: list[str],
    symbol_meta: dict[str, dict[str, float | str]],
) -> tuple[dict[str, float], dict[str, float]]:
    if not ALPACA_API_KEY_ID or not ALPACA_SECRET_KEY:
        raise RuntimeError("Missing Alpaca credentials.")
    if not symbols:
        return {}, {}

    query = urlencode(
        {
            "symbols": ",".join(symbols),
            "feed": ALPACA_FEED,
        }
    )
    url = f"{ALPACA_DATA_URL}/v2/stocks/snapshots?{query}"
    request = Request(
        url,
        headers={
            "APCA-API-KEY-ID": ALPACA_API_KEY_ID,
            "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
            "accept": "application/json",
        },
    )

    with urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))

    snapshots = payload.get("snapshots", {})
    anchors: dict[str, float] = {}
    current_prices: dict[str, float] = {}

    for symbol in symbols:
        meta = symbol_meta.get(symbol, {"base": 100.0})
        fallback_base = float(meta.get("base", 100.0))
        snapshot = snapshots.get(symbol, {})
        prev_daily_bar = snapshot.get("prevDailyBar") or {}
        daily_bar = snapshot.get("dailyBar") or {}
        latest_trade = snapshot.get("latestTrade") or {}
        latest_quote = snapshot.get("latestQuote") or {}

        anchor = (
            prev_daily_bar.get("c")
            or daily_bar.get("o")
            or latest_trade.get("p")
            or latest_quote.get("ap")
            or latest_quote.get("bp")
            or fallback_base
        )
        current = (
            latest_trade.get("p")
            or daily_bar.get("c")
            or latest_quote.get("ap")
            or latest_quote.get("bp")
            or anchor
        )

        anchors[symbol] = round(float(anchor), 4)
        current_prices[symbol] = round(float(current), 4)

    return anchors, current_prices


def load_alpaca_asset_metadata(symbols: list[str]) -> dict[str, dict[str, float | str]]:
    if not symbols:
        return {}

    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY_ID,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
        "accept": "application/json",
    }
    metadata: dict[str, dict[str, float | str]] = {}

    for symbol in symbols:
        default_meta = DEFAULT_SYMBOLS.get(
            symbol,
            {"display_name": symbol, "base": 100.0},
        )
        metadata[symbol] = {
            "display_name": str(default_meta["display_name"]),
            "base": float(default_meta["base"]),
        }
        last_error: str | None = None

        for base_url in alpaca_trading_base_urls():
            request = Request(
                f"{base_url}/v2/assets/{quote(symbol)}",
                headers=headers,
            )
            try:
                with urlopen(request, timeout=10) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                last_error = f"{base_url} returned {exc.code}"
                if exc.code == 404:
                    break
                continue
            except Exception as exc:
                last_error = str(exc)
                continue

            metadata[symbol]["display_name"] = str(payload.get("name") or symbol)
            break

        if last_error:
            print(f"Asset metadata fallback for {symbol}: {last_error}")

    return metadata


def load_cached_baselines(
    redis_client: Redis | None = None,
) -> tuple[dict[str, float], dict[str, float]] | None:
    try:
        redis_client = redis_client or get_redis_client()
        payload = redis_client.get(BASELINE_CACHE_KEY)
        if not payload:
            print(f"cache MISS {BASELINE_CACHE_KEY}")
            return None
        print(f"cache HIT {BASELINE_CACHE_KEY}")
        decoded = json.loads(payload)
        return decoded.get("anchors", {}), decoded.get("current_prices", {})
    except Exception as exc:
        print(f"Redis baseline cache read failed: {exc}")
        return None


def store_cached_baselines(
    anchors: dict[str, float],
    current_prices: dict[str, float],
    redis_client: Redis | None = None,
) -> None:
    try:
        redis_client = redis_client or get_redis_client()
        redis_client.setex(
            BASELINE_CACHE_KEY,
            6 * 60 * 60,
            json.dumps(
                {
                    "anchors": anchors,
                    "current_prices": current_prices,
                }
            ),
        )
        print(f"cache SET {BASELINE_CACHE_KEY} ttl=21600s")
    except Exception as exc:
        print(f"Redis baseline cache write failed: {exc}")


def prime_symbol_state(
    symbols: set[str],
    symbol_meta: dict[str, dict[str, float | str]],
    anchors: dict[str, float],
    previous_prices: dict[str, float],
    redis_client: Redis,
) -> None:
    missing = sorted(
        symbol
        for symbol in symbols
        if symbol not in anchors or symbol not in previous_prices or symbol not in symbol_meta
    )
    if not missing:
        return

    for symbol, meta in load_alpaca_asset_metadata(missing).items():
        existing = DEFAULT_SYMBOLS.get(symbol, {"display_name": symbol, "base": 100.0}).copy()
        existing.update(meta)
        symbol_meta[symbol] = existing

    try:
        next_anchors, next_prices = load_alpaca_snapshots(missing, symbol_meta)
    except Exception as exc:
        print(f"Snapshot bootstrap fallback for {', '.join(missing)}: {exc}")
        next_anchors = {}
        next_prices = {}

    for symbol in missing:
        meta = symbol_meta.setdefault(symbol, {"display_name": symbol, "base": 100.0})
        fallback_base = float(meta.get("base", 100.0))
        anchors[symbol] = round(float(next_anchors.get(symbol, fallback_base)), 4)
        previous_prices[symbol] = round(float(next_prices.get(symbol, anchors[symbol])), 4)
        meta["base"] = anchors[symbol]

    store_cached_baselines(anchors, previous_prices, redis_client)


async def send_subscription_update(websocket, action: str, symbols: list[str]) -> None:
    if not symbols:
        return

    await websocket.send(
        json.dumps(
            {
                "action": action,
                "quotes": symbols,
                "bars": symbols,
            }
        )
    )
    print(f"Sent {action} update for symbols: {', '.join(symbols)}")


async def sync_alpaca_subscriptions(
    websocket,
    redis_client: Redis,
    subscription_state: dict[str, set[str]],
    symbol_meta: dict[str, dict[str, float | str]],
    anchors: dict[str, float],
    previous_prices: dict[str, float],
) -> None:
    while True:
        await asyncio.sleep(TARGET_SYNC_INTERVAL_SECONDS)
        current_symbols = subscription_state["symbols"]
        target_symbols = set(load_requested_symbols(redis_client))
        to_add = sorted(target_symbols - current_symbols)
        to_remove = sorted(current_symbols - target_symbols)

        if not to_add and not to_remove:
            continue

        if to_add:
            prime_symbol_state(set(to_add), symbol_meta, anchors, previous_prices, redis_client)
            await send_subscription_update(websocket, "subscribe", to_add)

        if to_remove:
            await send_subscription_update(websocket, "unsubscribe", to_remove)

        subscription_state["symbols"] = target_symbols
        print(f"Active Alpaca symbols: {', '.join(sorted(target_symbols))}")


async def run_alpaca_stream(producer: AIOKafkaProducer) -> None:
    if not ALPACA_API_KEY_ID or not ALPACA_SECRET_KEY:
        raise RuntimeError("Missing Alpaca credentials.")

    redis_client = get_redis_client()
    symbol_meta: dict[str, dict[str, float | str]] = {
        symbol: meta.copy()
        for symbol, meta in DEFAULT_SYMBOLS.items()
    }

    cached = load_cached_baselines(redis_client)
    if cached:
        anchors, previous_prices = cached
        print("Loaded Alpaca snapshot baselines from Redis cache.")
    else:
        anchors, previous_prices = {}, {}

    initial_symbols = set(load_requested_symbols(redis_client))
    prime_symbol_state(initial_symbols, symbol_meta, anchors, previous_prices, redis_client)
    event_count = 0

    while True:
        sync_task: asyncio.Task | None = None
        try:
            async with websockets.connect(ALPACA_WS_URL, ping_interval=20, ping_timeout=20) as websocket:
                print(f"Connected to Alpaca stream: {ALPACA_WS_URL}")
                await websocket.send(
                    json.dumps(
                        {
                            "action": "auth",
                            "key": ALPACA_API_KEY_ID,
                            "secret": ALPACA_SECRET_KEY,
                        }
                    )
                )

                subscription_state = {"symbols": set(initial_symbols)}
                await send_subscription_update(
                    websocket,
                    "subscribe",
                    sorted(subscription_state["symbols"]),
                )
                print(f"Active Alpaca symbols: {', '.join(sorted(subscription_state['symbols']))}")

                sync_task = asyncio.create_task(
                    sync_alpaca_subscriptions(
                        websocket,
                        redis_client,
                        subscription_state,
                        symbol_meta,
                        anchors,
                        previous_prices,
                    )
                )

                async for raw_message in websocket:
                    try:
                        messages = json.loads(raw_message)
                    except json.JSONDecodeError:
                        print(f"Received non-JSON message: {raw_message!r}")
                        continue

                    if not isinstance(messages, list):
                        continue

                    for message in messages:
                        message_type = message.get("T")
                        if message_type in {"success", "subscription"}:
                            print(f"Alpaca stream event: {message}")
                            continue
                        if message_type == "error":
                            print(f"Alpaca stream error payload: {message}")
                            continue

                        symbol = str(message.get("S") or "").upper()
                        if not symbol or symbol not in subscription_state["symbols"]:
                            continue

                        meta = symbol_meta.get(symbol, {"display_name": symbol, "base": 100.0})
                        display_name = str(meta.get("display_name") or symbol)

                        if message_type == "q":
                            bid = message.get("bp")
                            ask = message.get("ap")
                            if bid is None and ask is None:
                                continue
                            current_price = float(ask or bid or previous_prices.get(symbol, 100.0))
                            volume = 0
                            timestamp = message.get("t")
                        elif message_type == "b":
                            current_price = float(
                                message.get("c", previous_prices.get(symbol, 100.0))
                            )
                            volume = int(message.get("v", 0))
                            timestamp = message.get("t")
                        else:
                            continue

                        anchor = anchors.get(symbol, previous_prices.get(symbol, current_price))
                        change_pct = round(
                            ((current_price - anchor) / anchor) * 100.0,
                            2,
                        ) if anchor else 0.0
                        previous_prices[symbol] = current_price

                        payload = {
                            "type": "price_update",
                            "ticker": symbol,
                            "display_name": display_name,
                            "current_price": round(current_price, 2),
                            "change_pct": change_pct,
                            "volume": volume,
                            "as_of": timestamp or datetime.now(timezone.utc).isoformat(),
                        }
                        await publish_event(producer, payload)
                        event_count += 1
                        if event_count <= 5 or event_count % 25 == 0:
                            print(
                                "Published Alpaca event "
                                f"#{event_count}: {symbol} {payload['current_price']} "
                                f"{payload['change_pct']}%"
                            )
                        if event_count % 100 == 0:
                            store_cached_baselines(anchors, previous_prices, redis_client)
        except Exception as exc:
            print(f"Alpaca stream error: {exc}. Retrying in 5s.")
            await asyncio.sleep(5)
        finally:
            if sync_task is not None:
                sync_task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await sync_task

        initial_symbols = set(load_requested_symbols(redis_client))
        prime_symbol_state(initial_symbols, symbol_meta, anchors, previous_prices, redis_client)


async def main() -> None:
    producer = await build_producer()
    try:
        if MARKET_DATA_PROVIDER == "alpaca":
            print("Starting Alpaca market data stream publisher.")
            await run_alpaca_stream(producer)
        else:
            print("Starting synthetic market data publisher.")
            await run_synthetic(producer)
    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
