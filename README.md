# Market Sentinel Dashboard

Independent stock-monitoring dashboard that showcases a deployable event-driven architecture with Kafka-style streaming, WebSocket fan-out, and a realtime watchlist UI.

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
- open per-ticker range charts from the dashboard
- seed a lightweight trade-plan draft directly from a selected stock card
- add and remove tickers from the watchlist in the running app

## Architecture

```text
+-------------------+        Kafka topic         +------------------+
| market-feed       |  ----------------------->  | backend          |
| synthetic ticker  |                            | FastAPI +        |
| publisher         |                            | WebSocket bridge |
+-------------------+                            +--------+---------+
                                                          |
                                                          | REST + WS
                                                          v
                                                 +------------------+
                                                 | frontend         |
                                                 | React dashboard  |
                                                 +------------------+
```

## What This Demonstrates

- Event-driven updates instead of request-only polling
- Separation between data producer, API layer, and UI
- Docker-first local deployment
- Real-time UI state reconciliation from WebSocket events
- A dashboard-to-workflow bridge through trade-plan seed generation

## UI Highlights

- top-level environment badges for market status, WebSocket health, and deployment stack
- urgency-ranked stock cards with mini history sparklines
- selected-position panel for focused inspection
- range-based history modal for per-symbol exploration
- trade-plan seed workspace with entry, stop, target, and thesis defaults

## Stack

- `frontend`: React + TypeScript + Vite + Nginx
- `backend`: FastAPI + `aiokafka`
- `event bus`: Redpanda in Kafka API mode
- `market-feed`: Python publisher that emits synthetic market events

## Run Locally

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
5. Add a ticker such as `AMZN` and remove it again

## Services

- `frontend`
  - Serves the dashboard UI on port `3000`
  - Proxies `/api/*` and `/ws/*` to the backend
- `backend`
  - Exposes dashboard APIs on port `8000`
  - Consumes Kafka events and rebroadcasts them to browser clients
- `market-feed`
  - Publishes synthetic price updates into the Kafka topic
- `redpanda`
  - Single-node Kafka-compatible broker

## API Surface

- `GET /api/dashboard/{user_id}`
- `POST /api/watchlist`
- `DELETE /api/watchlist/{user_id}/{ticker}`
- `GET /api/market-overview`
- `GET /api/stocks/{ticker}/history?range=1M`
- `WS /ws/dashboard`

## Design Notes

- The current version uses synthetic market events so the whole stack stays portable and demo-friendly.
- Watchlists are stored in memory to keep the setup minimal.
- Redpanda is used here for Kafka-compatible local development without introducing a heavier cluster setup.
- The chart view and trade-plan seed flow are intentionally scoped to showcase product thinking without expanding into a full brokerage or execution platform.

## Next Improvements

- persist watchlists and drafts in Redis or MongoDB
- replace the synthetic publisher with a real market data ingestion service
- add auth and user-specific websocket channels
- expand the trade-plan workflow into stored drafts and review states
- split event domains into market, sentiment, and alert topics
