from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect

from app.domain.models import (
    SaveJournalEntryRequest,
    SaveAlertRuleRequest,
    SaveTradePlanDraftRequest,
    StoredAlertRule,
    StoredJournalEntry,
    StoredTriggeredAlert,
    StoredTradePlanDraft,
    TickerValidationResult,
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
        app.state.dashboard_state.add_to_watchlist(payload.user_id, payload.ticker)
        await app.state.dashboard_state.hydrate_watchlist_ticker(payload.ticker)
        return app.state.dashboard_state.build_snapshot(payload.user_id)

    @app.delete("/api/watchlist/{user_id}/{ticker}")
    async def remove_from_watchlist(user_id: str, ticker: str):
        app.state.dashboard_state.remove_from_watchlist(user_id, ticker)
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
