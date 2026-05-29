from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress

from aiokafka import AIOKafkaConsumer

from app.core.config import settings
from app.domain.models import MarketEvent

logger = logging.getLogger("market_sentinel_streaming")


async def consume_market_events(app) -> None:
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
                await app.state.alert_engine.evaluate_market_event(event)
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
