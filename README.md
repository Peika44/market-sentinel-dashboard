# Market Sentinel Dashboard

Independent stock-monitoring dashboard that showcases a deployable event-driven architecture with Kafka-style streaming, WebSocket fan-out, Redis-coordinated symbol subscriptions, and a realtime watchlist UI.

This repository is a clean public showcase of the dashboard experience I independently rebuilt for GitHub. It keeps the engineering signal of a larger realtime trading system while staying small enough to run locally with one command.

## Why This Project Exists

I wanted a public repo that demonstrates:

- Dockerized deployment with `docker compose`
- Kafka-compatible event streaming via Redpanda
- FastAPI backend with WebSocket fan-out
- React dashboard for watchlist monitoring and urgency ranking

Instead of publishing a private course team repository, I rebuilt the dashboard-facing workflow as an independent portfolio project.

## What You Can Do

- monitor a live watchlist sorted by urgency score
- track market overview cards for `SPY`, `QQQ`, and `IWM`
- watch realtime price updates arrive through a Kafka-backed event pipeline
- validate tickers against Alpaca assets before adding them to the watchlist
- dynamically subscribe and unsubscribe market-feed symbols as the watchlist changes
- open per-ticker range charts from the dashboard
- seed a lightweight trade-plan draft directly from a selected stock card
- add and remove tickers from the watchlist in the running app

## Architecture

```text
+---------------------+     Redis active tickers     +---------------------+
| frontend            |  -------------------------->  | backend             |
| React dashboard     |                               | FastAPI + SQLite +  |
| ticker validation   |  <--------------------------  | WebSocket bridge    |
+----------+----------+        REST + WS              +----------+----------+
           |                                                         |
           |                                                         | Kafka topic
           v                                                         v
  +-------------------+                                    +-------------------+
  | Alpaca assets +   |                                    | market-feed       |
  | market data APIs  | <-------- dynamic subscribe ------ | Alpaca / synthetic|
  +-------------------+           via Redis target set     | publisher         |
                                                           +---------+---------+
                                                                     |
                                                                     v
                                                               +-----------+
                                                               | Redpanda  |
                                                               +-----------+
```

## What This Demonstrates

- Event-driven updates instead of request-only polling
- Separation between data producer, API layer, and UI
- Docker-first local deployment
- Real-time UI state reconciliation from WebSocket events
- Dynamic market-feed subscription management driven by active watchlist symbols
- Ticker validation against an external asset API before state mutation
- A dashboard-to-workflow bridge through trade-plan seed generation

## UI Highlights

- top-level environment badges for market status, WebSocket health, and deployment stack
- urgency-ranked stock cards with mini history sparklines
- selected-position panel for focused inspection
- range-based history modal for per-symbol exploration
- trade-plan seed workspace with entry, stop, target, and thesis defaults
- explicit waiting-state treatment for newly added symbols that have not received a first live tick yet

## Stack

- `frontend`: React + TypeScript + Vite + Nginx
- `backend`: FastAPI + `aiokafka` + SQLite + Redis cache coordination
- `event bus`: Redpanda in Kafka API mode
- `market-feed`: Python publisher that streams Alpaca or synthetic market events
- `market data`: Alpaca assets API + market data API
- `cache/coordination`: Redis

## Run Locally

Create a local env file first:

```bash
cp .env.example .env
```

Then choose one of these modes:

- `alpaca`
  - Set `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY`
  - Keeps ticker validation and live market-feed behavior aligned with the deployed setup
- `synthetic`
  - Set `MARKET_DATA_PROVIDER=synthetic`
  - Lets the stack run without external credentials

Start the stack:

```bash
docker compose up --build
```

Then open:

- Dashboard: `http://localhost:3000`
- Backend health: `http://localhost:8000/health`
- Market overview API: `http://localhost:8000/api/market-overview`

## Local Verification Checklist

After the stack comes up, verify these flows in the browser:

1. Confirm the header shows `Market Open/Closed` and `WebSocket live`
2. Confirm stock cards update over time without refreshing the page
3. Click `Open Chart` on a ticker and switch between history ranges
4. Click `Seed Trade Plan` and confirm the draft fields are prefilled
5. Add a valid ticker and confirm it enters either `live` or `waiting for first market tick` state
6. Remove that ticker and confirm it disappears from the watchlist without a page refresh
7. Try an invalid ticker such as `AMAZ` and confirm validation blocks it before mutation

## Services

- `frontend`
  - Serves the dashboard UI on port `3000`
  - Proxies `/api/*` and `/ws/*` to the backend
- `backend`
  - Exposes dashboard APIs on port `8000`
  - Consumes Kafka events and rebroadcasts them to browser clients
  - Persists watchlists, drafts, alerts, journal entries, and price history in SQLite
  - Publishes the active ticker set to Redis for market-feed coordination
- `market-feed`
  - Reads the active ticker set from Redis
  - Subscribes and unsubscribes Alpaca symbols dynamically
  - Publishes market events into the Kafka topic
- `redis`
  - Stores active ticker coordination state and short-lived caches
- `redpanda`
  - Single-node Kafka-compatible broker

## API Surface

- `GET /api/dashboard/{user_id}`
- `GET /api/tickers/validate?ticker=NVDA`
- `POST /api/watchlist`
- `DELETE /api/watchlist/{user_id}/{ticker}`
- `GET /api/market-overview`
- `GET /api/stocks/{ticker}/history?range=1M`
- `WS /ws/dashboard`

## Design Notes

- The default checked-in env shape is Alpaca-backed, but the codebase can still run in `synthetic` mode for offline demos.
- Watchlists, drafts, alerts, journal entries, and persisted history are stored in SQLite instead of memory-only state.
- Redpanda is used here for Kafka-compatible local development without introducing a heavier cluster setup.
- Redis coordinates the currently active ticker universe between backend and market-feed.
- Newly added symbols can appear in a `waiting` state until the first usable market tick arrives.
- Feed coverage depends on the configured Alpaca feed. A valid asset may not immediately produce a first tick on every feed.
- The chart view and trade-plan seed flow are intentionally scoped to showcase product thinking without expanding into a full brokerage or execution platform.

## Next Improvements

- improve first-tick bootstrap for symbols that validate successfully but have sparse current-feed coverage
- add tests around ticker validation, waiting-state transitions, and dynamic subscribe/unsubscribe behavior
- add auth and user-specific websocket channels
- expand the trade-plan workflow into stored drafts and review states
- split event domains into market, sentiment, and alert topics
