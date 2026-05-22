import asyncio
import json
import os
import random
from datetime import datetime, timezone

from aiokafka import AIOKafkaProducer

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "market-prices")
PUBLISH_INTERVAL_SECONDS = float(os.getenv("PUBLISH_INTERVAL_SECONDS", "1.0"))

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


async def main() -> None:
    producer = await build_producer()
    current_prices = {symbol: meta["base"] for symbol, meta in SYMBOLS.items()}
    anchors = current_prices.copy()

    try:
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
                await producer.send_and_wait(
                    KAFKA_TOPIC,
                    json.dumps(payload).encode("utf-8"),
                )

            await asyncio.sleep(PUBLISH_INTERVAL_SECONDS)
    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())

