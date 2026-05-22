# Product Roadmap

## Goal

Evolve `market-sentinel-dashboard` from a public showcase dashboard into a daily market-monitoring and decision-support tool.

The intended progression is:

1. Showcase dashboard
2. Stable daily watchlist tool
3. Trading decision assistant
4. Semi-automated workflow platform

The project should not jump directly into execution automation. The priority is to become useful in a real daily trading workflow first.

## Phase 1: From Demo to Daily Tool

Focus on core product reliability and utility.

### Objectives

- replace synthetic-only behavior with real user state
- preserve data between restarts
- make the dashboard usable as a daily workspace
- keep the stack simple enough to run locally with Docker

### Work Items

1. Real market data integration
   - replace the synthetic market publisher with a real market data ingestion path
   - support quotes, chart history, and market overview for a single market first

2. Persistence
   - persist watchlists
   - persist trade plan drafts
   - persist alert rules
   - persist user notes or ticker theses

3. Alert loop
   - support basic price and urgency alerts
   - add cooldown handling
   - add one outbound notification channel

4. Workflow structure
   - watchlist
   - ticker thesis
   - entry / stop / target
   - trade-plan draft
   - daily review notes

5. Stability
   - retry and backoff
   - health checks
   - data staleness detection
   - better logging

### Immediate implementation order

1. Persist watchlists and trade plan drafts
2. Persist alert rules
3. Add staleness and last-updated indicators
4. Replace synthetic chart/history behavior with real data
5. Add a minimal alert engine

## Phase 2: Structured Trading Workflow

Turn the dashboard into a tool that supports a repeatable routine.

### Objectives

- reduce tab switching
- capture reasoning alongside price action
- support pre-market, intraday, and post-market usage

### Work Items

- pre-market watchlist builder
- ticker notes and thesis tracking
- strategy groupings
- configurable urgency formula
- daily market summary
- session views: pre-market / live / close

## Phase 3: Stronger Alerting

Add monitoring that reduces the need to stare at the screen continuously.

### Work Items

- price breakout alerts
- volume spike alerts
- gap alerts
- urgency-threshold alerts
- end-of-day digest
- delivery via email, Telegram, Slack, or Discord

## Phase 4: Research and Feedback Loop

Use the tool to improve decisions over time rather than only display current state.

### Work Items

- trade journal
- thesis versus outcome tracking
- setup win-rate metrics
- alert usefulness metrics
- backtest and forward-test linkage

## Current Rule of Thumb

The project is moving in the right direction if it helps reduce the number of tools and browser tabs needed during a normal trading session.
