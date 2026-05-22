# Market Sentinel Dashboard

Independent stock-monitoring dashboard that preserves the architecture signal of a larger event-driven trading application while staying small enough to deploy with one command.

This repository is a clean public showcase of:

- Dockerized deployment with `docker compose`
- Kafka-compatible event streaming via Redpanda
- FastAPI backend with WebSocket fan-out
- React dashboard for watchlist monitoring and urgency ranking

It is intentionally scoped to the dashboard experience instead of reproducing a full private course platform.

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

## What This Shows

- Event-driven updates instead of request-only polling
- Separation between data producer, API layer, and UI
- Docker-first local deployment
- Real-time UI state reconciliation from WebSocket events

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
- `WS /ws/dashboard`

## Deployment Notes

The current version keeps watchlists in memory and uses synthetic market data so the whole stack stays easy to demo. The next production-like upgrades would be:

- persist watchlists in Redis or MongoDB
- replace synthetic publisher with a real market data ingestion service
- add auth and user-specific websocket channels
- move from one shared topic to multiple topic domains
