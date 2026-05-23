from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

import publisher


class FakeRedis:
    def __init__(self, payload: str | None = None, raises: Exception | None = None) -> None:
        self.payload = payload
        self.raises = raises
        self.setex_calls: list[tuple[str, int, str]] = []

    def get(self, key: str):
        if self.raises is not None:
            raise self.raises
        return self.payload

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.setex_calls.append((key, ttl, value))


class PublisherTests(unittest.IsolatedAsyncioTestCase):
    def test_load_requested_symbols_normalizes_payload(self) -> None:
        redis_client = FakeRedis(
            json.dumps({"tickers": [" msft ", "AAPL", "aapl", "", "tsla"]})
        )

        symbols = publisher.load_requested_symbols(redis_client)

        self.assertEqual(symbols, ["AAPL", "MSFT", "TSLA"])

    def test_load_requested_symbols_falls_back_to_defaults_on_error(self) -> None:
        redis_client = FakeRedis(raises=RuntimeError("redis offline"))

        symbols = publisher.load_requested_symbols(redis_client)

        self.assertEqual(symbols, publisher.default_target_symbols())

    def test_alpaca_trading_base_urls_deduplicates_and_ignores_blanks(self) -> None:
        with patch.object(publisher, "ALPACA_TRADING_URL", "https://paper-api.alpaca.markets/"):
            urls = publisher.alpaca_trading_base_urls()

        self.assertEqual(
            urls,
            ["https://paper-api.alpaca.markets", "https://api.alpaca.markets"],
        )

    def test_prime_symbol_state_bootstraps_only_missing_symbols(self) -> None:
        redis_client = FakeRedis()
        symbol_meta = {"AAPL": {"display_name": "Apple", "base": 212.1}}
        anchors = {"AAPL": 212.1}
        previous_prices = {"AAPL": 213.0}

        with patch.object(
            publisher,
            "load_alpaca_asset_metadata",
            return_value={"NFLX": {"display_name": "Netflix", "base": 620.0}},
        ) as mock_meta, patch.object(
            publisher,
            "load_alpaca_snapshots",
            return_value=({"NFLX": 615.5}, {"NFLX": 618.25}),
        ) as mock_snapshots, patch.object(
            publisher,
            "store_cached_baselines",
        ) as mock_store:
            publisher.prime_symbol_state(
                {"AAPL", "NFLX"},
                symbol_meta,
                anchors,
                previous_prices,
                redis_client,
            )

        mock_meta.assert_called_once_with(["NFLX"])
        mock_snapshots.assert_called_once()
        self.assertEqual(symbol_meta["NFLX"]["display_name"], "Netflix")
        self.assertEqual(symbol_meta["NFLX"]["base"], 615.5)
        self.assertEqual(anchors["NFLX"], 615.5)
        self.assertEqual(previous_prices["NFLX"], 618.25)
        mock_store.assert_called_once_with(anchors, previous_prices, redis_client)

    async def test_sync_alpaca_subscriptions_sends_add_and_remove_diffs(self) -> None:
        websocket = object()
        redis_client = FakeRedis()
        subscription_state = {"symbols": {"AAPL", "TSLA"}}
        symbol_meta: dict[str, dict[str, float | str]] = {}
        anchors: dict[str, float] = {}
        previous_prices: dict[str, float] = {}

        sleep_mock = AsyncMock(side_effect=[None, asyncio.CancelledError()])
        send_mock = AsyncMock()

        with patch.object(
            publisher,
            "load_requested_symbols",
            return_value=["MSFT"],
        ), patch.object(
            publisher,
            "prime_symbol_state",
        ) as mock_prime, patch.object(
            publisher,
            "send_subscription_update",
            send_mock,
        ), patch.object(
            publisher.asyncio,
            "sleep",
            sleep_mock,
        ):
            with self.assertRaises(asyncio.CancelledError):
                await publisher.sync_alpaca_subscriptions(
                    websocket,
                    redis_client,
                    subscription_state,
                    symbol_meta,
                    anchors,
                    previous_prices,
                )

        mock_prime.assert_called_once_with({"MSFT"}, symbol_meta, anchors, previous_prices, redis_client)
        self.assertEqual(
            send_mock.await_args_list[0].args,
            (websocket, "subscribe", ["MSFT"]),
        )
        self.assertEqual(
            send_mock.await_args_list[1].args,
            (websocket, "unsubscribe", ["AAPL", "TSLA"]),
        )
        self.assertEqual(subscription_state["symbols"], {"MSFT"})


if __name__ == "__main__":
    unittest.main()
