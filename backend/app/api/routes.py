from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect

from app.domain.models import (
    SaveCatalystEventRequest,
    EndOfDayDigest,
    FocusQueueEntryView,
    ReviewMetrics,
    SaveLeaderHoldingRequest,
    SaveFocusQueueEntryRequest,
    SaveJournalEntryRequest,
    SaveAlertRuleRequest,
    SaveTickerNoteRequest,
    SaveUrgencySettingsRequest,
    SaveTradePlanDraftRequest,
    SaveTradeRequest,
    StoredCatalystEvent,
    StoredLeaderHolding,
    StoredAlertRule,
    StoredJournalEntry,
    StoredTickerNote,
    StoredTrade,
    StoredTriggeredAlert,
    StoredTradePlanDraft,
    StoredUrgencySettings,
    ThesisOutcomeSummary,
    TickerValidationResult,
    UpdateAlertTaskRequest,
    WatchlistMutation,
)


def register_routes(app: FastAPI) -> None:
    @app.get("/health")
    async def health() -> dict[str, object]:
        cache_ok = app.state.cache.ping()
        websocket_clients = len(app.state.websocket_hub._connections)
        return {
            "status": "ok",
            "service": "backend",
            "provider": app.state.settings.market_data_provider,
            "feed": getattr(app.state.settings, "alpaca_feed", None),
            "cache": "ok" if cache_ok else "degraded",
            "websocket_clients": websocket_clients,
        }

    @app.get("/api/dashboard/{user_id}")
    async def get_dashboard(user_id: str):
        return app.state.dashboard_state.build_snapshot(user_id)

    @app.get("/api/market-overview")
    async def get_market_overview():
        return {"indices": await app.state.dashboard_state.build_overview()}

    @app.get("/api/tickers/validate", response_model=TickerValidationResult)
    async def validate_ticker(ticker: str):
        return await app.state.dashboard_state.validate_ticker(ticker)

    @app.post("/api/watchlist")
    async def add_to_watchlist(payload: WatchlistMutation):
        validation = await app.state.dashboard_state.validate_ticker(payload.ticker)
        if not validation.can_add:
            raise HTTPException(status_code=400, detail=validation.message)
        app.state.dashboard_state.add_to_watchlist(
            payload.user_id,
            payload.ticker,
            validation,
        )
        await app.state.dashboard_state.hydrate_watchlist_ticker(payload.ticker)
        return app.state.dashboard_state.build_snapshot(payload.user_id)

    @app.delete("/api/watchlist/{user_id}/{ticker}")
    async def remove_from_watchlist(user_id: str, ticker: str):
        app.state.dashboard_state.remove_from_watchlist(user_id, ticker)
        return app.state.dashboard_state.build_snapshot(user_id)

    @app.post("/api/watchlist/{user_id}/{ticker}/retry")
    async def retry_watchlist_ticker(user_id: str, ticker: str):
        if not app.state.dashboard_state.is_tracked(user_id, ticker):
            raise HTTPException(status_code=404, detail="Ticker is not on the watchlist.")
        await app.state.dashboard_state.hydrate_watchlist_ticker(ticker)
        return app.state.dashboard_state.build_snapshot(user_id)

    @app.get("/api/trade-plan-drafts/{user_id}", response_model=list[StoredTradePlanDraft])
    async def list_trade_plan_drafts(user_id: str):
        rows = app.state.dashboard_state.list_trade_plan_drafts(user_id)
        return [
            StoredTradePlanDraft(
                ticker=row["ticker"],
                updated_at=row["updated_at"],
                payload=row["payload"],
            )
            for row in rows
        ]

    @app.post("/api/trade-plan-drafts")
    async def save_trade_plan_draft(payload: SaveTradePlanDraftRequest):
        updated_at = datetime.now(timezone.utc).isoformat()
        app.state.dashboard_state.save_trade_plan_draft(
            payload.user_id,
            payload.draft.model_dump(),
            updated_at,
        )
        return {"ok": True, "updated_at": updated_at}

    @app.get("/api/alert-rules/{user_id}", response_model=list[StoredAlertRule])
    async def list_alert_rules(user_id: str):
        rows = app.state.dashboard_state.list_alert_rules(user_id)
        return [
            StoredAlertRule(
                rule_id=row["rule_id"],
                ticker=row["ticker"],
                updated_at=row["updated_at"],
                payload=row["payload"],
            )
            for row in rows
        ]

    @app.post("/api/alert-rules")
    async def save_alert_rule(payload: SaveAlertRuleRequest):
        updated_at = datetime.now(timezone.utc).isoformat()
        app.state.dashboard_state.save_alert_rule(
            payload.user_id,
            payload.rule.model_dump(),
            updated_at,
        )
        return {"ok": True, "updated_at": updated_at}

    @app.patch("/api/alert-rules/{user_id}/{rule_id}")
    async def update_alert_rule_enabled(user_id: str, rule_id: str, enabled: bool):
        updated_at = datetime.now(timezone.utc).isoformat()
        payload = app.state.dashboard_state.set_alert_rule_enabled(
            user_id,
            rule_id,
            enabled,
            updated_at,
        )
        if payload is None:
            return {"ok": False, "message": "Alert rule not found"}
        return {"ok": True, "updated_at": updated_at, "payload": payload}

    @app.delete("/api/alert-rules/{user_id}/{rule_id}")
    async def delete_alert_rule(user_id: str, rule_id: str):
        deleted = app.state.dashboard_state.delete_alert_rule(user_id, rule_id)
        if not deleted:
            return {"ok": False, "message": "Alert rule not found"}
        return {"ok": True, "rule_id": rule_id}

    @app.get("/api/triggered-alerts/{user_id}", response_model=list[StoredTriggeredAlert])
    async def list_triggered_alerts(user_id: str, limit: int = 20, offset: int = 0):
        rows = app.state.alert_engine.list_triggered_alerts(user_id, limit=limit, offset=offset)
        return [
            StoredTriggeredAlert(
                ticker=row["ticker"],
                triggered_at=row["triggered_at"],
                payload=row["payload"],
            )
            for row in rows
        ]

    @app.patch("/api/triggered-alerts/{user_id}/{alert_id}")
    async def update_alert_task_status(user_id: str, alert_id: str, body: UpdateAlertTaskRequest):
        updated = app.state.alert_engine.update_alert_task_status(
            user_id, alert_id, body.task_status, body.snoozed_until
        )
        return {"ok": updated, "alert_id": alert_id}

    @app.get("/api/journal-entries/{user_id}", response_model=list[StoredJournalEntry])
    async def list_journal_entries(user_id: str, limit: int = 12, offset: int = 0):
        rows = app.state.dashboard_state.list_journal_entries(user_id, limit=limit, offset=offset)
        return [
            StoredJournalEntry(
                entry_id=row["entry_id"],
                ticker=row["ticker"],
                updated_at=row["updated_at"],
                payload=row["payload"],
            )
            for row in rows
        ]

    @app.post("/api/journal-entries")
    async def save_journal_entry(payload: SaveJournalEntryRequest):
        updated_at = datetime.now(timezone.utc).isoformat()
        app.state.dashboard_state.save_journal_entry(
            payload.user_id,
            payload.entry.model_dump(),
            updated_at,
        )
        return {"ok": True, "updated_at": updated_at}

    @app.get("/api/ticker-notes/{user_id}/{ticker}", response_model=StoredTickerNote)
    async def get_ticker_note(user_id: str, ticker: str):
        row = app.state.dashboard_state.load_ticker_note(user_id, ticker)
        if row is None:
            return StoredTickerNote(
                ticker=ticker.upper(),
                updated_at="",
                payload={
                    "ticker": ticker.upper(),
                    "thesis": "",
                    "notes": "",
                    "strategyTag": "",
                },
            )
        return StoredTickerNote(
            ticker=row["ticker"],
            updated_at=row["updated_at"],
            payload=row["payload"],
        )

    @app.get("/api/ticker-notes/{user_id}", response_model=list[StoredTickerNote])
    async def list_ticker_notes(user_id: str):
        rows = app.state.dashboard_state.list_ticker_notes(user_id)
        return [
            StoredTickerNote(
                ticker=row["ticker"],
                updated_at=row["updated_at"],
                payload=row["payload"],
            )
            for row in rows
        ]

    @app.post("/api/ticker-notes")
    async def save_ticker_note(payload: SaveTickerNoteRequest):
        updated_at = datetime.now(timezone.utc).isoformat()
        app.state.dashboard_state.save_ticker_note(
            payload.user_id,
            payload.note.model_dump(),
            updated_at,
        )
        return {"ok": True, "updated_at": updated_at}

    @app.get("/api/focus-queue/{user_id}", response_model=list[FocusQueueEntryView])
    async def list_focus_queue_entries(user_id: str):
        return app.state.dashboard_state.list_focus_queue_entries(user_id)

    @app.get("/api/focus-queue/{user_id}/{ticker}", response_model=FocusQueueEntryView)
    async def get_focus_queue_entry(user_id: str, ticker: str):
        return app.state.dashboard_state.load_focus_queue_entry(user_id, ticker)

    @app.post("/api/focus-queue")
    async def save_focus_queue_entry(payload: SaveFocusQueueEntryRequest):
        updated_at = datetime.now(timezone.utc).isoformat()
        app.state.dashboard_state.save_focus_queue_entry(
            payload.user_id,
            payload.entry.model_dump(),
            updated_at,
        )
        return {"ok": True, "updated_at": updated_at}

    @app.delete("/api/focus-queue/{user_id}/{ticker}")
    async def restore_generated_focus_queue_entry(user_id: str, ticker: str):
        deleted = app.state.dashboard_state.delete_focus_queue_entry(user_id, ticker)
        return {"ok": True, "restored": deleted, "ticker": ticker.upper()}

    @app.get("/api/leader-holdings/{user_id}", response_model=list[StoredLeaderHolding])
    async def list_leader_holdings(user_id: str):
        return app.state.dashboard_state.list_leader_holdings(user_id)

    @app.post("/api/leader-holdings")
    async def save_leader_holding(payload: SaveLeaderHoldingRequest):
        updated_at = datetime.now(timezone.utc).isoformat()
        app.state.dashboard_state.save_leader_holding(
            payload.user_id,
            payload.holding.model_dump(),
            updated_at,
        )
        return {"ok": True, "updated_at": updated_at}

    @app.delete("/api/leader-holdings/{user_id}/{ticker}")
    async def delete_leader_holding(user_id: str, ticker: str):
        deleted = app.state.dashboard_state.delete_leader_holding(user_id, ticker)
        return {"ok": deleted, "ticker": ticker.upper()}

    @app.get("/api/catalyst-events/{user_id}", response_model=list[StoredCatalystEvent])
    async def list_catalyst_events(user_id: str):
        return app.state.dashboard_state.list_catalyst_events(user_id)

    @app.post("/api/catalyst-events")
    async def save_catalyst_event(payload: SaveCatalystEventRequest):
        updated_at = datetime.now(timezone.utc).isoformat()
        app.state.dashboard_state.save_catalyst_event(
            payload.user_id,
            payload.event.model_dump(),
            updated_at,
        )
        return {"ok": True, "updated_at": updated_at}

    @app.delete("/api/catalyst-events/{user_id}/{event_id}")
    async def delete_catalyst_event(user_id: str, event_id: str):
        deleted = app.state.dashboard_state.delete_catalyst_event(user_id, event_id)
        return {"ok": deleted, "event_id": event_id}

    @app.get("/api/thesis-outcome/{user_id}/{ticker}", response_model=ThesisOutcomeSummary)
    async def get_thesis_outcome_summary(user_id: str, ticker: str):
        return app.state.dashboard_state.build_thesis_outcome_summary(user_id, ticker)

    @app.get("/api/urgency-settings/{user_id}", response_model=StoredUrgencySettings)
    async def get_urgency_settings(user_id: str):
        current = app.state.dashboard_state.load_urgency_settings(user_id)
        return StoredUrgencySettings(
            updated_at="",
            payload=current,
        )

    @app.post("/api/urgency-settings")
    async def save_urgency_settings(payload: SaveUrgencySettingsRequest):
        updated_at = datetime.now(timezone.utc).isoformat()
        app.state.dashboard_state.save_urgency_settings(
            payload.user_id,
            payload.settings.model_dump(),
            updated_at,
        )
        return {"ok": True, "updated_at": updated_at}

    @app.get("/api/digest/{user_id}", response_model=EndOfDayDigest)
    async def get_end_of_day_digest(user_id: str):
        alerts = app.state.alert_engine.list_triggered_alerts(user_id, limit=5, offset=0)
        journal = app.state.dashboard_state.list_journal_entries(user_id, limit=3, offset=0)
        return await app.state.dashboard_state.build_end_of_day_digest(user_id, alerts, journal)

    @app.post("/api/digest/{user_id}/send")
    async def send_end_of_day_digest(user_id: str, channel: str = "discord"):
        alerts = app.state.alert_engine.list_triggered_alerts(user_id, limit=5, offset=0)
        journal = app.state.dashboard_state.list_journal_entries(user_id, limit=3, offset=0)
        digest = await app.state.dashboard_state.build_end_of_day_digest(user_id, alerts, journal)
        body = app.state.dashboard_state.render_end_of_day_digest_text(digest)
        app.state.notifier.send(channel, f"End-of-Day Digest · {user_id}", body)
        return {"ok": True, "channel": channel, "generated_at": digest.generated_at}

    @app.get("/api/review-metrics/{user_id}", response_model=ReviewMetrics)
    async def get_review_metrics(user_id: str):
        alerts = app.state.alert_engine.list_triggered_alerts(user_id, limit=500, offset=0)
        return app.state.dashboard_state.build_review_metrics(user_id, alerts)

    @app.get("/api/trades/{user_id}", response_model=list[StoredTrade])
    async def list_trades(user_id: str):
        return app.state.dashboard_state.list_trades(user_id)

    @app.post("/api/trades")
    async def save_trade(body: SaveTradeRequest):
        updated_at = datetime.now(timezone.utc).isoformat()
        trade_id = app.state.dashboard_state.save_trade(
            body.user_id, body.trade.model_dump(), updated_at
        )
        return {"ok": True, "trade_id": trade_id}

    @app.delete("/api/trades/{user_id}/{trade_id}")
    async def delete_trade(user_id: str, trade_id: str):
        deleted = app.state.dashboard_state.delete_trade(user_id, trade_id)
        return {"ok": deleted, "trade_id": trade_id}

    @app.get("/api/stocks/{ticker}/history")
    async def get_stock_history(ticker: str, range: str = "1M"):
        return {
            "ticker": ticker.upper(),
            "range": range,
            "candles": await app.state.dashboard_state.build_history(ticker, range),
        }

    @app.websocket("/ws/dashboard")
    async def dashboard_socket(websocket: WebSocket) -> None:
        await app.state.websocket_hub.connect(websocket)
        try:
            while True:
                msg = await websocket.receive_text()
                if msg == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            app.state.websocket_hub.disconnect(websocket)
