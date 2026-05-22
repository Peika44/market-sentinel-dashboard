from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
    kafka_topic: str = os.getenv("KAFKA_TOPIC", "market-prices")
    default_user_id: str = os.getenv("DEFAULT_USER_ID", "demo-user")
    sqlite_db_path: str = os.getenv("SQLITE_DB_PATH", "/data/market_sentinel.db")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    market_data_provider: str = os.getenv("MARKET_DATA_PROVIDER", "synthetic")
    alpaca_api_key: str = os.getenv("APCA_API_KEY_ID", "")
    alpaca_secret_key: str = os.getenv("APCA_API_SECRET_KEY", "")
    alpaca_feed: str = os.getenv("ALPACA_FEED", "iex")
    alpaca_data_url: str = os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets")
    discord_webhook_url: str = os.getenv("DISCORD_WEBHOOK_URL", "")


settings = Settings()

__all__ = ["Settings", "settings"]
