# Market Sentinel Dashboard

A full-stack stock-monitoring and trading-workflow tool built as an independent portfolio project. It combines real-time Kafka-backed price streaming, a two-mode market scanner, an intraday orderflow confirmation engine, a structured trade lifecycle, an alert engine, and a suite of research panels — all running locally with a single `docker compose up --build`.

## Features

### Watchlist & Live Prices
- Urgency-ranked watchlist cards with mini sparklines and 52-week range bars
- Real-time price updates over WebSocket (Kafka → FastAPI → React), no polling
- Market overview strip for SPY, QQQ, and IWM
- Per-symbol candlestick/line chart modal with selectable history ranges (5m → 1Y)
- Dynamic subscribe/unsubscribe from the Alpaca market feed as the watchlist changes
- Ticker validation against the Alpaca asset API before any state mutation

### Two-Mode Market Scanner
**Bottom-Building scan** — identifies stocks forming a base near 52-week lows before a potential markup phase.
- Scans S&P 500 or Nasdaq 100 universe (460 / 100 tickers)
- 100-point scoring across five daily signals:

| Signal | Weight | Logic |
|--------|--------|-------|
| Bottom position | 25 | Price in bottom 35% of 52-week range |
| Volume surge | 25 | 5-day avg volume > 25-day avg × 1.3 with healthy price action |
| RSI recovery | 20 | RSI was ≤35 in past 30 days, now 40–60 and trending up |
| MA cross | 15 | SMA5 crossing above SMA20, or price reclaiming SMA20 |
| MACD signal | 15 | Histogram rising 3 consecutive bars, or zero-line cross |

**Breakout / Pullback scan** — identifies momentum setups in trending stocks, translated directly from a TradingView Pine Script model.
- Breakout setup: price clears 20-day high with volume ≥ 1.8×, close strength ≥ 72%, daily return 2.5–9%, SMA5 > SMA20
- Pullback setup: price pulls back ≤ 6% after a prior strong impulse bar (≥ 1.75%), holding above SMA5 × 0.985
- Market filter: fetches QQQ before the scan and checks `close > SMA10 > SMA30` plus `new 20-day high OR daily return ≥ 1%`
- Both setups are strict AND conditions — non-qualifying stocks are excluded, not ranked low
- Score (0–100) ranks quality within qualifying stocks

### Intraday Orderflow Confirmation
Second-level filter that runs on scan results using yfinance 1-minute data (no Alpaca required).

Five intraday signals:
- **Gap check** — opening gap within a healthy range
- **Breakout hold** — price stayed above breakout level for ≥ 20 minutes
- **Orderflow** — detected aggressive buy sequences in bid/ask dynamics
- **Pullback quality** — intraday pullback ≤ 1.5% from session high
- **Spoofing filter** — no large bid replenishment patterns that suggest manipulation

When confirmed (≥ 4/5 signals), the trade plan auto-populates with the precise intraday entry, stop, and target instead of daily-close estimates.

### Trade Lifecycle
Full pipeline from idea to closed review:

`idea` → `planned` → `armed` → `entered` → `exited` → `reviewed`

- Per-stage notes and timestamps
- Entry, stop, target, actual entry, actual exit
- Setup type: breakout, pullback, mean-reversion, trend-continuation, event-driven
- Outcome tagging: open / win / loss / scratch
- Mistake tag taxonomy for post-trade analysis

### Alert Engine
- Per-ticker alert rules with condition (price/urgency), threshold, and cooldown
- Alerts fire into a task inbox with status tracking: pending → snoozed / dismissed / acted
- Snooze with a time window; acted alerts are linked to a trade record
- Alert utility metrics: act rate per condition type

### Research Panels
- **Focus Queue** — classify tickers as `today_focus`, `monitor`, or `ignore` with trigger and invalidation conditions
- **Leader Holdings** — track conviction levels (light/standard/heavy), position status, and thesis for high-conviction names
- **Catalyst Calendar** — log earnings, FOMC, CPI, NFP, ex-dividend, splits, options expiry, and custom news tags by date
- **Ticker Notes** — free-form thesis and strategy tagging per symbol

### Daily Workflow
- Session switcher: pre-market / live / close
- End-of-day digest with account metrics summary
- **Review panel** — aggregate win rate, average winner R / loser R, performance by setup type and session bucket, alert utility breakdown, mistake frequency analysis

---

## Architecture

```text
Browser (React + Vite)
        │  REST + WebSocket
        ▼
┌───────────────────────────────────────────┐
│  backend  (FastAPI + aiokafka)            │
│  ┌──────────────┐  ┌────────────────────┐ │
│  │ REST API      │  │ WS hub             │ │
│  │ 40+ endpoints │  │ fan-out to clients │ │
│  └──────┬───────┘  └────────┬───────────┘ │
│         │                   │ consume      │
│  ┌──────▼───────────────────▼───────────┐ │
│  │  SQLite (persist)  │  Redis (cache)  │ │
│  └─────────────────────────────────────┘ │
│                       │                   │
│  ScannerService ◄──── │ Alpaca bars API   │
│  IntradayService ◄─── │ yfinance 1m data  │
│  AlertEngine           │                   │
└────────────────────────┼───────────────────┘
                         │ Kafka consume
                         ▼
                  ┌─────────────┐
                  │  Redpanda   │  (Kafka-compatible broker)
                  └──────┬──────┘
                         │ publish
                         ▼
              ┌──────────────────────┐
              │  market-feed service │
              │  Alpaca WebSocket    │
              │  or synthetic mode   │
              └──────────┬───────────┘
                         │ Redis read
                         ▼
                  active ticker set
                  (updated by backend
                  as watchlist changes)
```

---

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + TypeScript + Vite + Nginx |
| Backend | FastAPI + aiokafka + httpx + Pydantic v2 |
| Scanner data | Alpaca market data API (daily bars) |
| Intraday data | yfinance + pandas (1-minute bars) |
| Persistence | SQLite via `sqlite3` stdlib |
| Cache / coordination | Redis |
| Event bus | Redpanda (Kafka API compatible) |
| Deployment | Docker Compose (5 services) |

---

## Run Locally

```bash
cp .env.example .env
```

Edit `.env` and choose a mode:

### Demo mode (no credentials required)

Set `DEMO_MODE=true` to run the complete dashboard with zero API credentials. Both scanners and the intraday confirmation engine return pre-canned results with a realistic animated progress bar so every UI flow is fully exercisable offline.

```env
DEMO_MODE=true
MARKET_DATA_PROVIDER=synthetic
```

### Live mode (Alpaca credentials)

| Variable | Description |
|----------|-------------|
| `DEMO_MODE` | `false` (default) — use real Alpaca data |
| `MARKET_DATA_PROVIDER` | `alpaca` for live streaming, `synthetic` for offline prices |
| `APCA_API_KEY_ID` | Alpaca API key (required for scanner and live watchlist) |
| `APCA_API_SECRET_KEY` | Alpaca API secret |
| `ALPACA_DATA_URL` | Alpaca data base URL (default: `https://data.alpaca.markets`) |
| `ALPACA_FEED` | `iex` (free) or `sip` (paid subscription) |

Start everything:

```bash
docker compose up --build
```

Open:
- Dashboard: `http://localhost:3000`
- Backend health: `http://localhost:8000/health`
- Market overview: `http://localhost:8000/api/market-overview`

> In live mode the daily scanner requires a valid Alpaca API key. The intraday confirmation engine uses yfinance and works without any API credentials.

---

## Verification Checklist

After the stack comes up:

1. Header shows `Market Open/Closed` and `WebSocket live`
2. Watchlist cards update in real time without refreshing
3. `Open Chart` → switch between history ranges (5m, 1D, 1M, 1Y)
4. **Scanner tab** → click `S&P 500 日线扫描` → observe progress bar → results table appears
5. From scanner results → click `日内验证全部` → intraday badges update per row
6. Switch scanner mode to `突破/回调` → run breakout scan → setup-type badges (突破/回调) visible
7. `Seed Trade Plan` from a scanner result → entry/stop/target pre-filled
8. Add an invalid ticker (`AMAZ`) → validation blocks it
9. **Trades tab** → create a trade, advance stages, add outcome
10. **Review tab** → win rate and setup breakdown update after trades are closed

---

## API Surface

### Watchlist & Dashboard
```
GET  /api/dashboard/{user_id}
GET  /api/market-overview
GET  /api/tickers/validate?ticker=NVDA
POST /api/watchlist
DELETE /api/watchlist/{user_id}/{ticker}
GET  /api/stocks/{ticker}/history?range=1M
```

### Scanner
```
POST /api/scanner/run
GET  /api/scanner/status/{user_id}
POST /api/scanner/breakout/run
GET  /api/scanner/breakout/status/{user_id}
POST /api/intraday/run
GET  /api/intraday/status/{user_id}
```

### Trade Workflow
```
GET    /api/trade-plan-drafts/{user_id}
PUT    /api/trade-plan-drafts/{user_id}/{ticker}
DELETE /api/trade-plan-drafts/{user_id}/{ticker}
GET    /api/trades/{user_id}
PUT    /api/trades/{user_id}
DELETE /api/trades/{user_id}/{trade_id}
GET    /api/review-metrics/{user_id}
GET    /api/end-of-day-digest/{user_id}
GET    /api/thesis-outcomes/{user_id}
```

### Alerts
```
GET    /api/alert-rules/{user_id}
PUT    /api/alert-rules/{user_id}
DELETE /api/alert-rules/{user_id}/{rule_id}
GET    /api/triggered-alerts/{user_id}
POST   /api/triggered-alerts/{user_id}/update-task
```

### Research Panels
```
GET /PUT /api/journal/{user_id}
GET /PUT /api/ticker-notes/{user_id}
GET /PUT /DELETE /api/focus-queue/{user_id}
GET /PUT /DELETE /api/leader-holdings/{user_id}
GET /PUT /DELETE /api/catalyst-events/{user_id}
GET /PUT /api/urgency-settings/{user_id}
```

### WebSocket
```
WS /ws/dashboard
```

---

## Engineering Decisions

**Scanner runs in background tasks, not threads.** `asyncio.create_task` launches the scan worker; `asyncio.Semaphore(15)` limits concurrent Alpaca requests. The frontend polls every 2 seconds until `status == "completed"`.

**Intraday confirmation is isolated from the daily scanner.** It runs on demand after the daily scan completes, using yfinance 1-minute data with no Alpaca dependency. All pandas/yfinance calls are wrapped in `loop.run_in_executor(None, ...)` to avoid blocking the event loop.

**Breakout scanner translates Pine Script conditions exactly.** Both breakout and pullback setups use the same AND-gate logic as the TradingView model rather than a fuzzy score. Non-qualifying stocks return `None` rather than a low score, so the result set only contains actual signal candidates.

**SQLite over PostgreSQL.** All persistent state (watchlists, trade plans, alert rules, journal entries, price history) lives in a single SQLite file. This keeps the stack self-contained for local development and portfolio demos without a separate database service.

**Redis as a coordination channel, not a message bus.** The backend publishes the active ticker set to Redis as a sorted set; the market-feed service reads it to manage Alpaca WebSocket subscriptions. Redpanda carries the actual event messages.

**No auth in the current build.** All endpoints use a hardcoded `demo-user` ID. Adding per-user authentication and WebSocket channel isolation is the intended next layer.

---

## Services

| Service | Port | Role |
|---------|------|------|
| `frontend` | 3000 | React SPA served by Nginx; proxies `/api/*` and `/ws/*` to backend |
| `backend` | 8000 | FastAPI: REST APIs, WebSocket hub, scanner engine, alert engine |
| `market-feed` | — | Alpaca/synthetic market event publisher → Redpanda |
| `redis` | 6379 | Active ticker coordination; short-lived response cache |
| `redpanda` | 9092 | Kafka-compatible single-node broker |

---

## Next Steps

- Integration tests for scanner scoring, ticker validation, and WebSocket state reconciliation
- Auth layer with per-user WebSocket channels
- Notification delivery for triggered alerts (email, Telegram, Discord)
- Backtest panel linking scanner signals to historical trade outcomes
