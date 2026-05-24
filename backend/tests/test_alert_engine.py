from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from app.domain.models import MarketEvent
from app.services.alerts import AlertEngine


class FakeStore:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = payloads
        self.saved: list[dict] = []

    def list_all_alert_rules(self) -> list[dict]:
        return self.payloads

    def save_triggered_alert(self, user_id: str, ticker: str, payload: dict, triggered_at: str) -> None:
        self.saved.append(
            {
                "user_id": user_id,
                "ticker": ticker,
                "payload": payload,
                "triggered_at": triggered_at,
            }
        )

    def list_triggered_alerts(self, user_id: str, limit: int = 20, offset: int = 0) -> list[dict]:
        return []


class FakeCache:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def get_json(self, key: str):
        return self.values.get(key)

    def set_json(self, key: str, value, ttl_seconds: int) -> None:
        self.values[key] = value


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send(self, channel: str, title: str, body: str) -> None:
        self.sent.append((channel, title, body))


class AlertEngineGapTests(unittest.TestCase):
    def test_gap_up_above_triggers(self) -> None:
        store = FakeStore(
            [
                {
                    "user_id": "demo-user",
                    "rule_id": "rule_gap_up",
                    "payload": {
                        "ticker": "NVDA",
                        "condition": "gap_up_above",
                        "threshold": "3",
                        "cooldownMinutes": "15",
                        "channel": "dashboard",
                        "enabled": True,
                    },
                }
            ]
        )
        cache = FakeCache()
        notifier = FakeNotifier()
        state = SimpleNamespace(
            recent_history_before_event=lambda ticker, limit=24: [],
            load_urgency_settings=lambda user_id: None,
            compute_urgency=lambda settings, change_pct, sentiment: 0.0,
        )
        engine = AlertEngine(store, cache, notifier, state)
        event = MarketEvent(
            ticker="NVDA",
            display_name="NVIDIA",
            current_price=125.0,
            change_pct=4.2,
            volume=1_000_000,
            as_of=datetime(2026, 5, 23, tzinfo=timezone.utc),
        )

        triggered = engine.evaluate_market_event(event)

        self.assertEqual(len(triggered), 1)
        self.assertEqual(triggered[0]["payload"]["condition"], "gap_up_above")
        self.assertIn("gapped up", triggered[0]["payload"]["message"])

    def test_gap_down_below_triggers(self) -> None:
        store = FakeStore(
            [
                {
                    "user_id": "demo-user",
                    "rule_id": "rule_gap_down",
                    "payload": {
                        "ticker": "TSLA",
                        "condition": "gap_down_below",
                        "threshold": "2.5",
                        "cooldownMinutes": "15",
                        "channel": "dashboard",
                        "enabled": True,
                    },
                }
            ]
        )
        cache = FakeCache()
        notifier = FakeNotifier()
        state = SimpleNamespace(
            recent_history_before_event=lambda ticker, limit=24: [],
            load_urgency_settings=lambda user_id: None,
            compute_urgency=lambda settings, change_pct, sentiment: 0.0,
        )
        engine = AlertEngine(store, cache, notifier, state)
        event = MarketEvent(
            ticker="TSLA",
            display_name="Tesla",
            current_price=170.0,
            change_pct=-3.1,
            volume=800_000,
            as_of=datetime(2026, 5, 23, tzinfo=timezone.utc),
        )

        triggered = engine.evaluate_market_event(event)

        self.assertEqual(len(triggered), 1)
        self.assertEqual(triggered[0]["payload"]["condition"], "gap_down_below")
        self.assertIn("gapped down", triggered[0]["payload"]["message"])


if __name__ == "__main__":
    unittest.main()
