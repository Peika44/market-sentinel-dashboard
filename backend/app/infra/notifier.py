from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from app.core.config import settings

logger = logging.getLogger("market_sentinel_notifier")

# Discord embed sidebar color per condition type
_CONDITION_COLORS: dict[str, int] = {
    # Bullish / target conditions — green
    "price_change_above": 0x2ECC71,
    "gap_up_above": 0x2ECC71,
    "target_hit": 0x2ECC71,
    "breakout_above_recent_high": 0x2ECC71,
    # Bearish / stop conditions — red
    "price_change_below": 0xE74C3C,
    "gap_down_below": 0xE74C3C,
    "drop_below_stop": 0xE74C3C,
    "breakdown_below_recent_low": 0xE74C3C,
    # Urgency / composite — orange
    "urgency_above": 0xE67E22,
    # Volume — blue
    "volume_above": 0x3498DB,
}
_DEFAULT_COLOR = 0x95A5A6  # grey


class Notifier:
    async def send(
        self,
        channel: str,
        title: str,
        body: str,
        *,
        condition: str = "",
        snapshot_price: float | None = None,
        snapshot_change_pct: float | None = None,
        threshold: str = "",
    ) -> None:
        normalized = channel.strip().lower()
        if normalized == "discord":
            await self._send_discord(
                title,
                body,
                condition=condition,
                snapshot_price=snapshot_price,
                snapshot_change_pct=snapshot_change_pct,
                threshold=threshold,
            )
        else:
            logger.info("notifier SKIP channel=%s title=%s", channel, title)

    async def _send_discord(
        self,
        title: str,
        body: str,
        *,
        condition: str = "",
        snapshot_price: float | None = None,
        snapshot_change_pct: float | None = None,
        threshold: str = "",
    ) -> None:
        if not settings.discord_webhook_url:
            logger.info("notifier DISCORD skipped: webhook URL not configured")
            return

        color = _CONDITION_COLORS.get(condition, _DEFAULT_COLOR)
        now_ts = datetime.now(timezone.utc).strftime("%H:%M UTC")

        fields: list[dict] = []
        if snapshot_price is not None:
            fields.append({"name": "Price", "value": f"${snapshot_price:,.2f}", "inline": True})
        if snapshot_change_pct is not None:
            sign = "+" if snapshot_change_pct >= 0 else ""
            fields.append({"name": "Change", "value": f"{sign}{snapshot_change_pct:.2f}%", "inline": True})
        if threshold:
            fields.append({"name": "Threshold", "value": threshold, "inline": True})
        fields.append({"name": "Time", "value": now_ts, "inline": True})

        embed: dict = {
            "title": title,
            "description": body,
            "color": color,
            "fields": fields,
            "footer": {"text": "Market Sentinel"},
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    settings.discord_webhook_url, json={"embeds": [embed]}
                )
                response.raise_for_status()
            logger.info("notifier DISCORD sent title=%s", title)
        except Exception as exc:
            logger.warning("notifier DISCORD failed: %s", exc)


__all__ = ["Notifier"]
