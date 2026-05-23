from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from app.domain.models import MarketEvent, TickerValidationResult
from app.infra.storage import SQLiteStore
from app.services.dashboard import ACTIVE_TICKERS_CACHE_KEY, DashboardState


class FakeCache:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def get_json(self, key: str):
        return self.values.get(key)

    def set_json(self, key: str, value, ttl_seconds=None) -> bool:
        self.values[key] = value
        return True


def make_settings(
    *,
    provider: str,
    alpaca_api_key: str = "",
    alpaca_secret_key: str = "",
) -> SimpleNamespace:
    return SimpleNamespace(
        default_user_id="demo-user",
        market_data_provider=provider,
        alpaca_api_key=alpaca_api_key,
        alpaca_secret_key=alpaca_secret_key,
        alpaca_feed="iex",
        alpaca_data_url="https://data.alpaca.markets",
        alpaca_trading_url="https://paper-api.alpaca.markets",
    )


class DashboardStateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tempdir = TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)

    def make_store(self) -> SQLiteStore:
        return SQLiteStore(str(Path(self.tempdir.name) / "market_sentinel_test.db"))

    def test_placeholder_history_is_purged_on_init_in_alpaca_mode(self) -> None:
        store = self.make_store()
        store.replace_watchlist("demo-user", ["AMD"])
        store.save_price_history_bulk("AMD", [100.0])
        cache = FakeCache()

        with patch(
            "app.services.dashboard.settings",
            make_settings(provider="alpaca", alpaca_api_key="key", alpaca_secret_key="secret"),
        ):
            state = DashboardState(store, cache)

        self.assertEqual(store.load_price_history("AMD"), [])
        self.assertEqual(list(state.price_history["AMD"]), [])
        self.assertEqual(state.recent_history_before_event("AMD"), [])

    def test_build_snapshot_marks_symbols_without_quotes_as_waiting(self) -> None:
        store = self.make_store()
        store.replace_watchlist("demo-user", ["AMD"])
        cache = FakeCache()

        with patch(
            "app.services.dashboard.settings",
            make_settings(provider="alpaca", alpaca_api_key="key", alpaca_secret_key="secret"),
        ):
            state = DashboardState(store, cache)
            snapshot = state.build_snapshot("demo-user")

        self.assertEqual(len(snapshot.stocks), 1)
        card = snapshot.stocks[0]
        self.assertEqual(card.ticker, "AMD")
        self.assertEqual(card.data_status, "waiting")
        self.assertIsNone(card.current_price)
        self.assertIsNone(card.change_pct)
        self.assertIsNone(card.last_updated)
        self.assertEqual(card.history, [])
        self.assertEqual(card.urgency_score, 0.0)

    def test_build_snapshot_sorts_live_cards_ahead_of_waiting_cards(self) -> None:
        store = self.make_store()
        store.replace_watchlist("demo-user", ["AAPL", "AMD"])
        cache = FakeCache()
        live_event = MarketEvent(
            ticker="AAPL",
            display_name="Apple",
            current_price=219.25,
            change_pct=1.75,
            volume=125_000,
            as_of=datetime(2026, 5, 23, tzinfo=timezone.utc),
        )

        with patch(
            "app.services.dashboard.settings",
            make_settings(provider="alpaca", alpaca_api_key="key", alpaca_secret_key="secret"),
        ):
            state = DashboardState(store, cache)
            state.apply_event(live_event)
            snapshot = state.build_snapshot("demo-user")

        self.assertEqual(snapshot.stocks[0].ticker, "AAPL")
        self.assertEqual(snapshot.stocks[0].data_status, "live")
        self.assertEqual(snapshot.stocks[0].current_price, 219.25)
        waiting_card = next(card for card in snapshot.stocks if card.ticker == "AMD")
        self.assertEqual(waiting_card.data_status, "waiting")
        self.assertIsNone(waiting_card.current_price)

    def test_sync_active_tickers_writes_watchlist_and_overview_symbols_to_cache(self) -> None:
        store = self.make_store()
        store.replace_watchlist("demo-user", ["SHOP"])
        cache = FakeCache()

        with patch("app.services.dashboard.settings", make_settings(provider="synthetic")):
            state = DashboardState(store, cache)
            self.assertCountEqual(
                cache.values[ACTIVE_TICKERS_CACHE_KEY]["tickers"],
                ["SHOP", "SPY", "QQQ", "IWM"],
            )

            state.add_to_watchlist("demo-user", "NVDA")

        self.assertCountEqual(
            cache.values[ACTIVE_TICKERS_CACHE_KEY]["tickers"],
            ["SHOP", "NVDA", "SPY", "QQQ", "IWM"],
        )

    async def test_validate_ticker_uses_alpaca_branch_and_sets_display_name(self) -> None:
        store = self.make_store()
        cache = FakeCache()
        expected = TickerValidationResult(
            ticker="NFLX",
            is_valid=True,
            can_add=True,
            display_name="Netflix, Inc. Common Stock",
            feed_status="supported",
            source="alpaca_assets",
            message="",
        )

        with patch(
            "app.services.dashboard.settings",
            make_settings(provider="alpaca", alpaca_api_key="key", alpaca_secret_key="secret"),
        ):
            state = DashboardState(store, cache)
            with patch.object(
                state,
                "_validate_alpaca_ticker",
                AsyncMock(return_value=expected),
            ) as mock_validate:
                result = await state.validate_ticker("nflx")

        mock_validate.assert_awaited_once_with("NFLX")
        self.assertTrue(result.can_add)
        self.assertEqual(
            result.message,
            "Netflix, Inc. Common Stock (NFLX) is available to add.",
        )
        self.assertEqual(
            state.display_names["NFLX"],
            "Netflix, Inc. Common Stock",
        )


if __name__ == "__main__":
    unittest.main()
