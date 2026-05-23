from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock
from uuid import uuid4


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
            self._ensure_alert_rules_table(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS triggered_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    triggered_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS journal_entries (
                    entry_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ticker_notes (
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
                CREATE TABLE IF NOT EXISTS urgency_settings (
                    user_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    price REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_price_history_ticker ON price_history(ticker)"
            )
            conn.commit()

    def _ensure_alert_rules_table(self, conn: sqlite3.Connection) -> None:
        table_exists = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'alert_rules'
            """
        ).fetchone()

        if table_exists is None:
            conn.execute(
                """
                CREATE TABLE alert_rules (
                    rule_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            return

        columns = conn.execute("PRAGMA table_info(alert_rules)").fetchall()
        column_names = {row["name"] for row in columns}
        if "rule_id" in column_names:
            return

        conn.execute("ALTER TABLE alert_rules RENAME TO alert_rules_legacy")
        conn.execute(
            """
            CREATE TABLE alert_rules (
                rule_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        legacy_rows = conn.execute(
            """
            SELECT user_id, ticker, payload_json, updated_at
            FROM alert_rules_legacy
            """
        ).fetchall()

        for row in legacy_rows:
            payload = json.loads(row["payload_json"])
            rule_id = payload.get("ruleId") or f"rule_{uuid4().hex[:12]}"
            payload["ruleId"] = rule_id
            conn.execute(
                """
                INSERT INTO alert_rules (rule_id, user_id, ticker, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    rule_id,
                    row["user_id"],
                    row["ticker"],
                    json.dumps(payload),
                    row["updated_at"],
                ),
            )

        conn.execute("DROP TABLE alert_rules_legacy")

    def load_watchlist(self, user_id: str) -> list[str]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT ticker FROM watchlists WHERE user_id = ? ORDER BY ticker",
                (user_id,),
            ).fetchall()
            return [row["ticker"] for row in rows]

    def list_all_watchlist_tickers(self) -> list[str]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT ticker FROM watchlists ORDER BY ticker"
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
        self, user_id: str, payload: dict, updated_at: str
    ) -> str:
        rule_id = str(payload.get("ruleId") or f"rule_{uuid4().hex[:12]}")
        payload["ruleId"] = rule_id
        ticker = str(payload["ticker"]).upper()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO alert_rules (rule_id, user_id, ticker, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(rule_id)
                DO UPDATE SET payload_json = excluded.payload_json, updated_at = excluded.updated_at
                """,
                (rule_id, user_id, ticker, json.dumps(payload), updated_at),
            )
            conn.commit()
            return rule_id

    def list_alert_rules(self, user_id: str) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT rule_id, ticker, payload_json, updated_at
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
                        "rule_id": row["rule_id"],
                        "ticker": row["ticker"],
                        "updated_at": row["updated_at"],
                        "payload": json.loads(row["payload_json"]),
                    }
                )
            return rules

    def list_all_alert_rules(self) -> list[dict]:
        """Return all alert rules across every user, used by the alert engine."""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT rule_id, user_id, ticker, payload_json, updated_at
                FROM alert_rules
                ORDER BY updated_at DESC
                """
            ).fetchall()
            rules: list[dict] = []
            for row in rows:
                rules.append(
                    {
                        "rule_id": row["rule_id"],
                        "user_id": row["user_id"],
                        "ticker": row["ticker"],
                        "updated_at": row["updated_at"],
                        "payload": json.loads(row["payload_json"]),
                    }
                )
            return rules

    def set_alert_rule_enabled(
        self, user_id: str, rule_id: str, enabled: bool, updated_at: str
    ) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json
                FROM alert_rules
                WHERE user_id = ? AND rule_id = ?
                """,
                (user_id, rule_id),
            ).fetchone()
            if row is None:
                return None

            payload = json.loads(row["payload_json"])
            payload["enabled"] = enabled
            payload["ruleId"] = rule_id

            conn.execute(
                """
                UPDATE alert_rules
                SET payload_json = ?, updated_at = ?
                WHERE user_id = ? AND rule_id = ?
                """,
                (json.dumps(payload), updated_at, user_id, rule_id),
            )
            conn.commit()
            return payload

    def delete_alert_rule(self, user_id: str, rule_id: str) -> bool:
        with self._lock, self._connect() as conn:
            result = conn.execute(
                """
                DELETE FROM alert_rules
                WHERE user_id = ? AND rule_id = ?
                """,
                (user_id, rule_id),
            )
            conn.commit()
            return result.rowcount > 0

    def save_triggered_alert(
        self, user_id: str, ticker: str, payload: dict, triggered_at: str
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO triggered_alerts (user_id, ticker, payload_json, triggered_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, ticker.upper(), json.dumps(payload), triggered_at),
            )
            conn.commit()

    def list_triggered_alerts(self, user_id: str, limit: int = 20, offset: int = 0) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT ticker, payload_json, triggered_at
                FROM triggered_alerts
                WHERE user_id = ?
                ORDER BY triggered_at DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, limit, offset),
            ).fetchall()
            alerts: list[dict] = []
            for row in rows:
                alerts.append(
                    {
                        "ticker": row["ticker"],
                        "triggered_at": row["triggered_at"],
                        "payload": json.loads(row["payload_json"]),
                    }
                )
            return alerts

    def save_journal_entry(self, user_id: str, payload: dict, updated_at: str) -> str:
        entry_id = str(payload.get("entryId") or f"journal_{uuid4().hex[:12]}")
        payload["entryId"] = entry_id
        ticker = str(payload["ticker"]).upper()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO journal_entries (entry_id, user_id, ticker, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(entry_id)
                DO UPDATE SET payload_json = excluded.payload_json, updated_at = excluded.updated_at
                """,
                (entry_id, user_id, ticker, json.dumps(payload), updated_at),
            )
            conn.commit()
            return entry_id

    def list_journal_entries(self, user_id: str, limit: int = 12, offset: int = 0) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT entry_id, ticker, payload_json, updated_at
                FROM journal_entries
                WHERE user_id = ?
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, limit, offset),
            ).fetchall()
            entries: list[dict] = []
            for row in rows:
                entries.append(
                    {
                        "entry_id": row["entry_id"],
                        "ticker": row["ticker"],
                        "updated_at": row["updated_at"],
                        "payload": json.loads(row["payload_json"]),
                    }
                )
            return entries

    def save_ticker_note(self, user_id: str, ticker: str, payload: dict, updated_at: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ticker_notes (user_id, ticker, payload_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, ticker)
                DO UPDATE SET payload_json = excluded.payload_json, updated_at = excluded.updated_at
                """,
                (user_id, ticker.upper(), json.dumps(payload), updated_at),
            )
            conn.commit()

    def load_ticker_note(self, user_id: str, ticker: str) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT ticker, payload_json, updated_at
                FROM ticker_notes
                WHERE user_id = ? AND ticker = ?
                """,
                (user_id, ticker.upper()),
            ).fetchone()
            if row is None:
                return None
            return {
                "ticker": row["ticker"],
                "updated_at": row["updated_at"],
                "payload": json.loads(row["payload_json"]),
            }

    def list_ticker_notes(self, user_id: str) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT ticker, payload_json, updated_at
                FROM ticker_notes
                WHERE user_id = ?
                ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()
            notes: list[dict] = []
            for row in rows:
                notes.append(
                    {
                        "ticker": row["ticker"],
                        "updated_at": row["updated_at"],
                        "payload": json.loads(row["payload_json"]),
                    }
                )
            return notes

    def save_urgency_settings(self, user_id: str, payload: dict, updated_at: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO urgency_settings (user_id, payload_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id)
                DO UPDATE SET payload_json = excluded.payload_json, updated_at = excluded.updated_at
                """,
                (user_id, json.dumps(payload), updated_at),
            )
            conn.commit()

    def load_urgency_settings(self, user_id: str) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json, updated_at
                FROM urgency_settings
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
            if row is None:
                return None
            return {
                "updated_at": row["updated_at"],
                "payload": json.loads(row["payload_json"]),
            }


    def save_price_history_bulk(self, ticker: str, prices: list[float]) -> None:
        """Replace the stored price sequence for a ticker with the current in-memory deque."""
        ticker_upper = ticker.upper()
        with self._lock, self._connect() as conn:
            conn.execute(
                "DELETE FROM price_history WHERE ticker = ?",
                (ticker_upper,),
            )
            if prices:
                conn.executemany(
                    "INSERT INTO price_history (ticker, price) VALUES (?, ?)",
                    [(ticker_upper, price) for price in prices],
                )
            conn.commit()

    def load_price_history(self, ticker: str, limit: int = 180) -> list[float]:
        """Return up to `limit` most recent prices for a ticker in chronological order."""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT price FROM price_history
                WHERE ticker = ?
                ORDER BY id ASC
                """,
                (ticker.upper(),),
            ).fetchall()
        prices = [row["price"] for row in rows]
        return prices[-limit:] if len(prices) > limit else prices

    def list_tickers_with_history(self) -> list[str]:
        """Return all tickers that have at least one persisted price point."""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT ticker FROM price_history"
            ).fetchall()
        return [row["ticker"] for row in rows]


__all__ = ["SQLiteStore"]
