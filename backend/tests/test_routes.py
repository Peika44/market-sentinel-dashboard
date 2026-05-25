from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import register_routes
from app.domain.models import (
    DashboardSnapshot,
    EndOfDayDigest,
    FocusQueueEntryPayload,
    FocusQueueEntryView,
    LeaderHoldingPayload,
    StockCard,
    StoredLeaderHolding,
    TickerValidationResult,
)


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
        self.tracked_tickers: set[str] = {self.snapshot.stocks[0].ticker} if self.snapshot.stocks else set()
        self.note = {
            "ticker": "NFLX",
            "updated_at": "",
            "payload": {
                "ticker": "NFLX",
                "thesis": "",
                "notes": "",
                "strategyTag": "",
            },
        }
        self.urgency_settings = {
            "updated_at": "",
            "payload": {
                "priceWeightPct": 65.0,
                "sentimentWeightPct": 35.0,
                "priceMoveScale": 5.0,
                "lowThreshold": 40.0,
                "highThreshold": 70.0,
            },
        }
        self.focus_queue_entry = FocusQueueEntryView(
            ticker="NFLX",
            updated_at="",
            source="generated",
            payload=FocusQueueEntryPayload(
                ticker="NFLX",
                bucket="monitor",
                whyOnList="Auto-generated queue note.",
                triggerCondition="Promote it when momentum confirms.",
                invalidationCondition="Ignore it if the setup fails.",
            ),
            generated_payload=FocusQueueEntryPayload(
                ticker="NFLX",
                bucket="monitor",
                whyOnList="Auto-generated queue note.",
                triggerCondition="Promote it when momentum confirms.",
                invalidationCondition="Ignore it if the setup fails.",
            ),
        )
        self.digest = EndOfDayDigest.model_validate(
            {
                "user_id": "demo-user",
                "generated_at": "2026-05-23T23:59:00Z",
                "headline": "End-of-Day Digest",
                "summary": "Mixed Tape. Review NVDA, TSLA, and AAPL first.",
                "metrics": [
                    {"label": "Index Tone", "value": "Mixed Tape", "detail": "Broad market context."},
                    {"label": "Top Urgency", "value": "NVDA, TSLA, AAPL", "detail": "Highest-ranked live names."},
                ],
            }
        )
        self.leader_holding = StoredLeaderHolding(
            ticker="NFLX",
            updated_at="2026-05-24T08:30:00Z",
            payload=LeaderHoldingPayload(
                ticker="NFLX",
                positionStatus="holding",
                conviction="standard",
                timeHorizon="swing",
                entryZone="420-428",
                thesis="Streaming breakout with improving engagement.",
                invalidatedWhen="Loses prior breakout level with weak tape.",
                lastUpdatedAt="2026-05-24 08:30 PT",
            ),
        )

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

    def is_tracked(self, user_id: str, ticker: str) -> bool:
        self.calls.append(("tracked", f"{user_id}:{ticker}"))
        return ticker.upper() in self.tracked_tickers

    def load_ticker_note(self, user_id: str, ticker: str):
        self.calls.append(("load-note", f"{user_id}:{ticker}"))
        if ticker.upper() != self.note["ticker"]:
            return None
        return self.note

    def list_ticker_notes(self, user_id: str):
        self.calls.append(("list-notes", user_id))
        return [self.note]

    def list_journal_entries(self, user_id: str, limit: int = 12, offset: int = 0):
        self.calls.append(("list-journal", user_id))
        return []

    def save_ticker_note(self, user_id: str, payload: dict, updated_at: str) -> None:
        self.calls.append(("save-note", f"{user_id}:{payload['ticker']}"))
        self.note = {
            "ticker": payload["ticker"].upper(),
            "updated_at": updated_at,
            "payload": payload,
        }

    def load_focus_queue_entry(self, user_id: str, ticker: str):
        self.calls.append(("load-focus-queue", f"{user_id}:{ticker}"))
        return self.focus_queue_entry.model_copy(
            update={"ticker": ticker.upper(), "payload": self.focus_queue_entry.payload.model_copy(update={"ticker": ticker.upper()}), "generated_payload": self.focus_queue_entry.generated_payload.model_copy(update={"ticker": ticker.upper()})}
        )

    def list_focus_queue_entries(self, user_id: str):
        self.calls.append(("list-focus-queue", user_id))
        return [self.focus_queue_entry]

    def save_focus_queue_entry(self, user_id: str, payload: dict, updated_at: str) -> None:
        self.calls.append(("save-focus-queue", f"{user_id}:{payload['ticker']}"))
        entry_payload = FocusQueueEntryPayload.model_validate(payload)
        self.focus_queue_entry = FocusQueueEntryView(
            ticker=entry_payload.ticker,
            updated_at=updated_at,
            source="saved",
            payload=entry_payload,
            generated_payload=self.focus_queue_entry.generated_payload.model_copy(
                update={"ticker": entry_payload.ticker}
            ),
        )

    def delete_focus_queue_entry(self, user_id: str, ticker: str) -> bool:
        self.calls.append(("delete-focus-queue", f"{user_id}:{ticker}"))
        self.focus_queue_entry = FocusQueueEntryView(
            ticker=ticker.upper(),
            updated_at="",
            source="generated",
            payload=self.focus_queue_entry.generated_payload.model_copy(
                update={"ticker": ticker.upper()}
            ),
            generated_payload=self.focus_queue_entry.generated_payload.model_copy(
                update={"ticker": ticker.upper()}
            ),
        )
        return True

    def list_leader_holdings(self, user_id: str):
        self.calls.append(("list-leader-holdings", user_id))
        return [self.leader_holding]

    def save_leader_holding(self, user_id: str, payload: dict, updated_at: str) -> None:
        self.calls.append(("save-leader-holding", f"{user_id}:{payload['ticker']}"))
        self.leader_holding = StoredLeaderHolding(
            ticker=str(payload["ticker"]).upper(),
            updated_at=updated_at,
            payload=LeaderHoldingPayload.model_validate(payload),
        )

    def delete_leader_holding(self, user_id: str, ticker: str) -> bool:
        self.calls.append(("delete-leader-holding", f"{user_id}:{ticker}"))
        return True

    def load_urgency_settings(self, user_id: str):
        self.calls.append(("load-urgency", user_id))
        return self.urgency_settings["payload"]

    def save_urgency_settings(self, user_id: str, payload: dict, updated_at: str) -> None:
        self.calls.append(("save-urgency", user_id))
        self.urgency_settings = {
            "updated_at": updated_at,
            "payload": payload,
        }

    async def build_end_of_day_digest(self, user_id: str, alerts: list[dict], journal: list[dict]):
        self.calls.append(("build-digest", user_id))
        return self.digest

    def render_end_of_day_digest_text(self, digest: EndOfDayDigest) -> str:
        self.calls.append(("render-digest", digest.user_id))
        return digest.summary


class RouteTests(unittest.TestCase):
    def make_client(self, dashboard_state: FakeDashboardState) -> TestClient:
        app = FastAPI()
        register_routes(app)
        app.state.dashboard_state = dashboard_state
        app.state.alert_engine = SimpleNamespace(list_triggered_alerts=lambda *args, **kwargs: [])
        app.state.cache = SimpleNamespace(ping=lambda: True)
        app.state.settings = SimpleNamespace(market_data_provider="alpaca")
        app.state.notifier = SimpleNamespace(send=lambda channel, title, body: dashboard_state.calls.append(("send-digest", channel)))
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

    def test_retry_watchlist_ticker_rehydrates_tracked_symbol(self) -> None:
        delayed_snapshot = build_snapshot("NFLX", data_status="delayed", current_price=421.55)
        state = FakeDashboardState(
            validation=TickerValidationResult(
                ticker="NFLX",
                is_valid=True,
                can_add=True,
                display_name="Netflix, Inc. Common Stock",
                feed_status="delayed",
                source="alpaca_assets",
                message="NFLX has delayed bootstrap coverage.",
            ),
            snapshot=delayed_snapshot,
        )
        client = self.make_client(state)

        response = client.post("/api/watchlist/demo-user/NFLX/retry")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            state.calls,
            [
                ("tracked", "demo-user:NFLX"),
                ("hydrate", "NFLX"),
                ("snapshot", "demo-user"),
            ],
        )

    def test_retry_watchlist_ticker_rejects_untracked_symbol(self) -> None:
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
            snapshot=DashboardSnapshot(
                user_id="demo-user",
                updated_at=datetime(2026, 5, 23, tzinfo=timezone.utc),
                stocks=[],
            ),
        )
        state.tracked_tickers = set()
        client = self.make_client(state)

        response = client.post("/api/watchlist/demo-user/NFLX/retry")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Ticker is not on the watchlist.")
        self.assertEqual(state.calls, [("tracked", "demo-user:NFLX")])

    def test_get_ticker_note_returns_empty_payload_when_missing(self) -> None:
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
        )
        client = self.make_client(state)

        response = client.get("/api/ticker-notes/demo-user/AMD")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["ticker"], "AMD")
        self.assertEqual(payload["payload"]["thesis"], "")
        self.assertEqual(state.calls, [("load-note", "demo-user:AMD")])

    def test_save_ticker_note_persists_payload(self) -> None:
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
        )
        client = self.make_client(state)

        response = client.post(
            "/api/ticker-notes",
            json={
                "user_id": "demo-user",
                "note": {
                    "ticker": "NFLX",
                    "thesis": "Weekly breakout candidate",
                    "notes": "Needs volume confirmation above prior high.",
                    "strategyTag": "Breakout",
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(state.calls[0][0], "save-note")
        self.assertEqual(state.note["payload"]["strategyTag"], "Breakout")

    def test_list_focus_queue_entries_returns_generated_payload(self) -> None:
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
        )
        client = self.make_client(state)

        response = client.get("/api/focus-queue/demo-user")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload[0]["ticker"], "NFLX")
        self.assertEqual(payload[0]["payload"]["bucket"], "monitor")
        self.assertEqual(state.calls, [("list-focus-queue", "demo-user")])

    def test_save_focus_queue_entry_persists_user_override(self) -> None:
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
        )
        client = self.make_client(state)

        response = client.post(
            "/api/focus-queue",
            json={
                "user_id": "demo-user",
                "entry": {
                    "ticker": "NFLX",
                    "bucket": "today_focus",
                    "whyOnList": "Top breakout candidate for the open.",
                    "triggerCondition": "Stay above the opening range high with volume.",
                    "invalidationCondition": "Drop it if it loses VWAP and relative strength fades.",
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(state.calls[0], ("save-focus-queue", "demo-user:NFLX"))
        self.assertEqual(state.focus_queue_entry.payload.bucket, "today_focus")

    def test_list_leader_holdings_returns_saved_payload(self) -> None:
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
        )
        client = self.make_client(state)

        response = client.get("/api/leader-holdings/demo-user")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload[0]["ticker"], "NFLX")
        self.assertEqual(payload[0]["payload"]["positionStatus"], "holding")
        self.assertEqual(state.calls, [("list-leader-holdings", "demo-user")])

    def test_save_leader_holding_persists_payload(self) -> None:
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
        )
        client = self.make_client(state)

        response = client.post(
            "/api/leader-holdings",
            json={
                "user_id": "demo-user",
                "holding": {
                    "ticker": "NVDA",
                    "positionStatus": "adding",
                    "conviction": "heavy",
                    "timeHorizon": "mid",
                    "entryZone": "114-118",
                    "thesis": "AI leader staying in control above key support.",
                    "invalidatedWhen": "Breaks major support with semis rolling over.",
                    "lastUpdatedAt": "2026-05-24 09:10 PT",
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(state.calls[0], ("save-leader-holding", "demo-user:NVDA"))
        self.assertEqual(state.leader_holding.payload.conviction, "heavy")

    def test_delete_leader_holding_removes_payload(self) -> None:
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
        )
        client = self.make_client(state)

        response = client.delete("/api/leader-holdings/demo-user/NFLX")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(state.calls[0], ("delete-leader-holding", "demo-user:NFLX"))

    def test_restore_generated_focus_queue_entry_removes_saved_override(self) -> None:
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
        )
        state.focus_queue_entry = FocusQueueEntryView(
            ticker="NFLX",
            updated_at="2026-05-24T08:00:00Z",
            source="saved",
            payload=FocusQueueEntryPayload(
                ticker="NFLX",
                bucket="today_focus",
                whyOnList="User override.",
                triggerCondition="User trigger.",
                invalidationCondition="User invalidation.",
            ),
            generated_payload=FocusQueueEntryPayload(
                ticker="NFLX",
                bucket="monitor",
                whyOnList="Generated note.",
                triggerCondition="Generated trigger.",
                invalidationCondition="Generated invalidation.",
            ),
        )
        client = self.make_client(state)

        response = client.delete("/api/focus-queue/demo-user/NFLX")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(state.calls[0], ("delete-focus-queue", "demo-user:NFLX"))
        self.assertEqual(state.focus_queue_entry.source, "generated")
        self.assertEqual(state.focus_queue_entry.payload.bucket, "monitor")

    def test_list_ticker_notes_returns_saved_notes(self) -> None:
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
        )
        state.note = {
            "ticker": "NVDA",
            "updated_at": "2026-05-23T23:42:00Z",
            "payload": {
                "ticker": "NVDA",
                "thesis": "AI leadership",
                "notes": "Watch for continuation above range highs.",
                "strategyTag": "Breakout",
            },
        }
        client = self.make_client(state)

        response = client.get("/api/ticker-notes/demo-user")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["ticker"], "NVDA")
        self.assertEqual(payload[0]["payload"]["strategyTag"], "Breakout")
        self.assertEqual(state.calls, [("list-notes", "demo-user")])

    def test_get_urgency_settings_returns_current_formula(self) -> None:
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
        )
        client = self.make_client(state)

        response = client.get("/api/urgency-settings/demo-user")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["payload"]["priceWeightPct"], 65.0)
        self.assertEqual(state.calls, [("load-urgency", "demo-user")])

    def test_save_urgency_settings_persists_formula(self) -> None:
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
        )
        client = self.make_client(state)

        response = client.post(
            "/api/urgency-settings",
            json={
                "user_id": "demo-user",
                "settings": {
                    "priceWeightPct": 55,
                    "sentimentWeightPct": 45,
                    "priceMoveScale": 6,
                    "lowThreshold": 35,
                    "highThreshold": 75,
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(state.calls[0], ("save-urgency", "demo-user"))
        self.assertEqual(state.urgency_settings["payload"]["highThreshold"], 75)

    def test_get_end_of_day_digest_returns_preview_payload(self) -> None:
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
        )
        client = self.make_client(state)

        response = client.get("/api/digest/demo-user")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["headline"], "End-of-Day Digest")
        self.assertEqual(
            state.calls,
            [("list-journal", "demo-user"), ("build-digest", "demo-user")],
        )

    def test_send_end_of_day_digest_uses_notifier(self) -> None:
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
        )
        client = self.make_client(state)

        response = client.post("/api/digest/demo-user/send?channel=discord")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            state.calls,
            [
                ("list-journal", "demo-user"),
                ("build-digest", "demo-user"),
                ("render-digest", "demo-user"),
                ("send-digest", "discord"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
