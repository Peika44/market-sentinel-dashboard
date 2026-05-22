from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.cache import RedisCache
from app.models import AlertRulePayload, MarketEvent
from app.notifier import Notifier
from app.state import DashboardState
from app.storage import SQLiteStore

logger = logging.getLogger("market_sentinel_alerts")

DEFAULT_USER_ID = "demo-user"


class AlertEngine:
    def __init__(
        self,
        store: SQLiteStore,
        cache: RedisCache,
        notifier: Notifier,
        state: DashboardState,
    ) -> None:
        self._store = store
        self._cache = cache
        self._notifier = notifier
        self._state = state

    def evaluate_market_event(self, event: MarketEvent) -> list[dict]:
        rules = self._store.list_alert_rules(DEFAULT_USER_ID)
        triggered: list[dict] = []
        previous_history = self._state.recent_history_before_event(event.ticker, limit=24)

        for row in rules:
            payload = AlertRulePayload.model_validate(row["payload"])
            if not payload.enabled or payload.ticker.upper() != event.ticker.upper():
                continue

            threshold = self._parse_float(payload.threshold)
            if threshold is None:
                continue

            triggered_value: float | None = None
            message = ""

            if payload.condition == "urgency_above":
                urgency = self._compute_urgency_proxy(event.change_pct)
                if urgency >= threshold:
                    triggered_value = urgency
                    message = (
                        f"{event.ticker} urgency reached {urgency:.2f}, above threshold {threshold:.2f}."
                    )
            elif payload.condition == "price_change_above":
                if event.change_pct >= threshold:
                    triggered_value = event.change_pct
                    message = (
                        f"{event.ticker} price change reached {event.change_pct:.2f}%."
                    )
            elif payload.condition == "price_change_below":
                if event.change_pct <= threshold:
                    triggered_value = event.change_pct
                    message = (
                        f"{event.ticker} price change dropped to {event.change_pct:.2f}%."
                    )
            elif payload.condition == "volume_above":
                if float(event.volume) >= threshold:
                    triggered_value = float(event.volume)
                    message = (
                        f"{event.ticker} volume reached {event.volume:,}, above threshold {int(threshold):,}."
                    )
            elif payload.condition == "target_hit":
                if event.current_price >= threshold:
                    triggered_value = event.current_price
                    message = (
                        f"{event.ticker} hit target price {threshold:.2f} with last price {event.current_price:.2f}."
                    )
            elif payload.condition == "drop_below_stop":
                if event.current_price <= threshold:
                    triggered_value = event.current_price
                    message = (
                        f"{event.ticker} dropped below stop level {threshold:.2f} with last price {event.current_price:.2f}."
                    )
            elif payload.condition == "breakout_above_recent_high":
                if previous_history:
                    recent_high = max(previous_history)
                    breakout_threshold = recent_high + threshold
                    if event.current_price > breakout_threshold:
                        triggered_value = event.current_price
                        message = (
                            f"{event.ticker} broke above recent high {recent_high:.2f} with last price {event.current_price:.2f}."
                        )
            elif payload.condition == "breakdown_below_recent_low":
                if previous_history:
                    recent_low = min(previous_history)
                    breakdown_threshold = recent_low - threshold
                    if event.current_price < breakdown_threshold:
                        triggered_value = event.current_price
                        message = (
                            f"{event.ticker} broke below recent low {recent_low:.2f} with last price {event.current_price:.2f}."
                        )

            if triggered_value is None:
                continue

            cooldown_key = (
                f"alert_cooldown:{DEFAULT_USER_ID}:{event.ticker.upper()}:"
                f"{payload.condition}:{payload.threshold}:{payload.channel}"
            )
            if self._cache.get_json(cooldown_key) is not None:
                logger.info("alert COOLDOWN %s", cooldown_key)
                continue

            triggered_at = datetime.now(timezone.utc).isoformat()
            stored_payload = {
                "ticker": event.ticker.upper(),
                "condition": payload.condition,
                "threshold": payload.threshold,
                "channel": payload.channel,
                "triggered_value": f"{triggered_value:.2f}",
                "message": message,
            }
            self._store.save_triggered_alert(
                DEFAULT_USER_ID,
                event.ticker.upper(),
                stored_payload,
                triggered_at,
            )

            cooldown_minutes = self._parse_float(payload.cooldownMinutes) or 15.0
            self._cache.set_json(
                cooldown_key,
                {"triggered_at": triggered_at},
                ttl_seconds=max(60, int(cooldown_minutes * 60)),
            )
            self._notifier.send(
                payload.channel,
                f"Alert Triggered: {event.ticker.upper()}",
                message,
            )
            logger.info("alert TRIGGERED %s %s", event.ticker.upper(), payload.condition)
            triggered.append(
                {
                    "ticker": event.ticker.upper(),
                    "triggered_at": triggered_at,
                    "payload": stored_payload,
                }
            )

        return triggered

    def list_triggered_alerts(self, user_id: str, limit: int = 20) -> list[dict]:
        return self._store.list_triggered_alerts(user_id, limit=limit)

    @staticmethod
    def _parse_float(value: str) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _compute_urgency_proxy(change_pct: float) -> float:
        return min(abs(change_pct) * 5.0, 100.0)
