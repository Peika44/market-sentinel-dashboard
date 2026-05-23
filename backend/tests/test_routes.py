from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import register_routes
from app.domain.models import DashboardSnapshot, StockCard, TickerValidationResult


def build_snapshot(
    ticker: str = "NFLX",
    *,
    data_status: str = "waiting",
    current_price: float | None = None,
) -> DashboardSnapshot:
    return DashboardSnapshot(
        user_id="demo-user",
        updated_at=datetime(2026, 5, 23, tzinfo=timezone.utc),
        stocks=[
            StockCard(
                ticker=ticker,
                display_name="Netflix, Inc. Common Stock",
                current_price=current_price,
                change_pct=1.25 if current_price is not None else None,
                volume=150_000 if current_price is not None else 0,
                last_updated=(
                    datetime(2026, 5, 23, 15, 30, tzinfo=timezone.utc)
                    if current_price is not None
                    else None
                ),
                data_status=data_status,
                sentiment_score=0.61,
                sentiment_label="Neutral",
                urgency_score=22.5 if current_price is not None else 0.0,
                history=[current_price] if current_price is not None else [],
            )
        ],
    )


class FakeDashboardState:
    def __init__(
        self,
        *,
        validation: TickerValidationResult,
        snapshot: DashboardSnapshot | None = None,
    ) -> None:
        self.validation = validation
        self.snapshot = snapshot or build_snapshot()
        self.calls: list[tuple[str, str]] = []

    async def validate_ticker(self, ticker: str) -> TickerValidationResult:
        self.calls.append(("validate", ticker))
        return self.validation

    def add_to_watchlist(
        self,
        user_id: str,
        ticker: str,
        validation: TickerValidationResult | None = None,
    ) -> None:
        marker = f"{user_id}:{ticker}:{validation.feed_status if validation else 'none'}"
        self.calls.append(("add", marker))

    async def hydrate_watchlist_ticker(self, ticker: str) -> None:
        self.calls.append(("hydrate", ticker))

    def build_snapshot(self, user_id: str) -> DashboardSnapshot:
        self.calls.append(("snapshot", user_id))
        return self.snapshot

    def remove_from_watchlist(self, user_id: str, ticker: str) -> None:
        self.calls.append(("remove", f"{user_id}:{ticker}"))


class RouteTests(unittest.TestCase):
    def make_client(self, dashboard_state: FakeDashboardState) -> TestClient:
        app = FastAPI()
        register_routes(app)
        app.state.dashboard_state = dashboard_state
        app.state.alert_engine = SimpleNamespace(list_triggered_alerts=lambda *args, **kwargs: [])
        app.state.cache = SimpleNamespace(ping=lambda: True)
        app.state.settings = SimpleNamespace(market_data_provider="alpaca")
        app.state.websocket_hub = SimpleNamespace(_connections=set())
        return TestClient(app)

    def test_validate_ticker_route_returns_validation_payload(self) -> None:
        state = FakeDashboardState(
            validation=TickerValidationResult(
                ticker="NFLX",
                is_valid=True,
                can_add=True,
                display_name="Netflix, Inc. Common Stock",
                feed_status="supported",
                source="alpaca_assets",
                message="Netflix, Inc. Common Stock (NFLX) is available to add.",
            )
        )
        client = self.make_client(state)

        response = client.get("/api/tickers/validate", params={"ticker": "NFLX"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ticker"], "NFLX")
        self.assertEqual(response.json()["display_name"], "Netflix, Inc. Common Stock")
        self.assertEqual(state.calls, [("validate", "NFLX")])

    def test_add_to_watchlist_rejects_invalid_ticker(self) -> None:
        state = FakeDashboardState(
            validation=TickerValidationResult(
                ticker="AMAZ",
                is_valid=False,
                can_add=False,
                display_name=None,
                feed_status="unknown",
                source="alpaca_assets",
                message="AMAZ was not found in Alpaca assets.",
            )
        )
        client = self.make_client(state)

        response = client.post("/api/watchlist", json={"user_id": "demo-user", "ticker": "AMAZ"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "AMAZ was not found in Alpaca assets.")
        self.assertEqual(state.calls, [("validate", "AMAZ")])

    def test_add_to_watchlist_returns_waiting_snapshot_after_hydrate(self) -> None:
        waiting_snapshot = build_snapshot("NFLX", data_status="waiting", current_price=None)
        state = FakeDashboardState(
            validation=TickerValidationResult(
                ticker="NFLX",
                is_valid=True,
                can_add=True,
                display_name="Netflix, Inc. Common Stock",
                feed_status="delayed",
                source="alpaca_assets",
                message="Netflix, Inc. Common Stock (NFLX) is valid, but the configured IEX feed only has delayed bootstrap data right now.",
            ),
            snapshot=waiting_snapshot,
        )
        client = self.make_client(state)

        response = client.post("/api/watchlist", json={"user_id": "demo-user", "ticker": "NFLX"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["stocks"][0]["ticker"], "NFLX")
        self.assertEqual(payload["stocks"][0]["data_status"], "waiting")
        self.assertIsNone(payload["stocks"][0]["current_price"])
        self.assertEqual(
            state.calls,
            [
                ("validate", "NFLX"),
                ("add", "demo-user:NFLX:delayed"),
                ("hydrate", "NFLX"),
                ("snapshot", "demo-user"),
            ],
        )
        self.assertEqual(
            payload["stocks"][0]["data_status"],
            "waiting",
        )

    def test_remove_from_watchlist_returns_updated_snapshot(self) -> None:
        empty_snapshot = DashboardSnapshot(
            user_id="demo-user",
            updated_at=datetime(2026, 5, 23, tzinfo=timezone.utc),
            stocks=[],
        )
        state = FakeDashboardState(
            validation=TickerValidationResult(
                ticker="NFLX",
                is_valid=True,
                can_add=True,
                display_name="Netflix, Inc. Common Stock",
                feed_status="supported",
                source="alpaca_assets",
                message="",
            ),
            snapshot=empty_snapshot,
        )
        client = self.make_client(state)

        response = client.delete("/api/watchlist/demo-user/NFLX")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["stocks"], [])
        self.assertEqual(
            state.calls,
            [
                ("remove", "demo-user:NFLX"),
                ("snapshot", "demo-user"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
