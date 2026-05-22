from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock


class SQLiteStore:
    def __init__(self, db_path: str) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS watchlists (
                    user_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    PRIMARY KEY (user_id, ticker)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_plan_drafts (
                    user_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, ticker)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alert_rules (
                    user_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, ticker)
                )
                """
            )
            conn.commit()

    def load_watchlist(self, user_id: str) -> list[str]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT ticker FROM watchlists WHERE user_id = ? ORDER BY ticker",
                (user_id,),
            ).fetchall()
            return [row["ticker"] for row in rows]

    def replace_watchlist(self, user_id: str, tickers: list[str]) -> None:
        normalized = sorted({ticker.upper() for ticker in tickers})
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM watchlists WHERE user_id = ?", (user_id,))
            conn.executemany(
                "INSERT INTO watchlists (user_id, ticker) VALUES (?, ?)",
                [(user_id, ticker) for ticker in normalized],
            )
            conn.commit()

    def save_trade_plan_draft(
        self, user_id: str, ticker: str, payload: dict, updated_at: str
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO trade_plan_drafts (user_id, ticker, payload_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, ticker)
                DO UPDATE SET payload_json = excluded.payload_json, updated_at = excluded.updated_at
                """,
                (user_id, ticker.upper(), json.dumps(payload), updated_at),
            )
            conn.commit()

    def list_trade_plan_drafts(self, user_id: str) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT ticker, payload_json, updated_at
                FROM trade_plan_drafts
                WHERE user_id = ?
                ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()
            drafts: list[dict] = []
            for row in rows:
                drafts.append(
                    {
                        "ticker": row["ticker"],
                        "updated_at": row["updated_at"],
                        "payload": json.loads(row["payload_json"]),
                    }
                )
            return drafts

    def save_alert_rule(
        self, user_id: str, ticker: str, payload: dict, updated_at: str
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO alert_rules (user_id, ticker, payload_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, ticker)
                DO UPDATE SET payload_json = excluded.payload_json, updated_at = excluded.updated_at
                """,
                (user_id, ticker.upper(), json.dumps(payload), updated_at),
            )
            conn.commit()

    def list_alert_rules(self, user_id: str) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT ticker, payload_json, updated_at
                FROM alert_rules
                WHERE user_id = ?
                ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()
            rules: list[dict] = []
            for row in rows:
                rules.append(
                    {
                        "ticker": row["ticker"],
                        "updated_at": row["updated_at"],
                        "payload": json.loads(row["payload_json"]),
                    }
                )
            return rules
