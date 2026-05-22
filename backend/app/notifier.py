from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger("market_sentinel_notifier")


class Notifier:
    def send(self, channel: str, title: str, body: str) -> None:
        normalized = channel.strip().lower()
        if normalized == "discord":
            self._send_discord(title, body)
        else:
            logger.info("notifier SKIP channel=%s title=%s", channel, title)

    def _send_discord(self, title: str, body: str) -> None:
        if not settings.discord_webhook_url:
            logger.info("notifier DISCORD skipped because webhook is not configured")
            return

        payload = {
            "embeds": [
                {
                    "title": title,
                    "description": body,
                }
            ]
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(settings.discord_webhook_url, json=payload)
                response.raise_for_status()
            logger.info("notifier DISCORD sent title=%s", title)
        except Exception as exc:
            logger.warning("notifier DISCORD failed: %s", exc)
