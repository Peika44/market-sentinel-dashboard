import asyncio
import json
import os
import random
from datetime import datetime, timezone
from urllib.parse import urlencode
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
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

SYMBOLS = {
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


async def run_synthetic(producer: AIOKafkaProducer) -> None:
    current_prices = {symbol: meta["base"] for symbol, meta in SYMBOLS.items()}
    anchors = current_prices.copy()

    while True:
        for symbol, meta in SYMBOLS.items():
            move = random.uniform(-0.0045, 0.0045)
            current_prices[symbol] = max(
                meta["base"] * 0.65,
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
                "display_name": meta["display_name"],
                "current_price": current_price,
                "change_pct": change_pct,
                "volume": random.randint(50_000, 2_500_000),
                "as_of": datetime.now(timezone.utc).isoformat(),
            }
            await publish_event(producer, payload)

        await asyncio.sleep(PUBLISH_INTERVAL_SECONDS)


def load_alpaca_snapshots() -> tuple[dict[str, float], dict[str, float]]:
    if not ALPACA_API_KEY_ID or not ALPACA_SECRET_KEY:
        raise RuntimeError("Missing Alpaca credentials.")

    query = urlencode(
        {
            "symbols": ",".join(SYMBOLS.keys()),
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

    for symbol, meta in SYMBOLS.items():
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
            or meta["base"]
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


def get_redis_client() -> Redis:
    return Redis.from_url(REDIS_URL, decode_responses=True)


def load_cached_baselines() -> tuple[dict[str, float], dict[str, float]] | None:
    try:
        redis_client = get_redis_client()
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


def store_cached_baselines(anchors: dict[str, float], current_prices: dict[str, float]) -> None:
    try:
        redis_client = get_redis_client()
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


async def run_alpaca_stream(producer: AIOKafkaProducer) -> None:
    if not ALPACA_API_KEY_ID or not ALPACA_SECRET_KEY:
        raise RuntimeError("Missing Alpaca credentials.")

    symbol_list = list(SYMBOLS.keys())
    try:
        cached = load_cached_baselines()
        if cached:
            anchors, previous_prices = cached
            print("Loaded Alpaca snapshot baselines from Redis cache.")
        else:
            anchors, previous_prices = load_alpaca_snapshots()
            store_cached_baselines(anchors, previous_prices)
            print("Loaded Alpaca snapshot baselines from API and cached them.")
    except Exception as exc:
        print(f"Failed to load Alpaca snapshots, using fallback baselines: {exc}")
        previous_prices = {symbol: meta["base"] for symbol, meta in SYMBOLS.items()}
        anchors = previous_prices.copy()
    event_count = 0

    while True:
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
                await websocket.send(
                    json.dumps(
                        {
                            "action": "subscribe",
                            "quotes": symbol_list,
                            "bars": symbol_list,
                        }
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

                        symbol = message.get("S")
                        if not symbol or symbol not in SYMBOLS:
                            continue

                        display_name = SYMBOLS[symbol]["display_name"]

                        if message_type == "q":
                            bid = message.get("bp")
                            ask = message.get("ap")
                            if bid is None and ask is None:
                                continue
                            current_price = float(ask or bid or previous_prices[symbol])
                            volume = 0
                            timestamp = message.get("t")
                        elif message_type == "b":
                            current_price = float(message.get("c", previous_prices[symbol]))
                            volume = int(message.get("v", 0))
                            timestamp = message.get("t")
                        else:
                            continue

                        anchor = anchors.get(symbol, previous_prices[symbol])
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
        except Exception as exc:
            print(f"Alpaca stream error: {exc}. Retrying in 5s.")
            await asyncio.sleep(5)


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
