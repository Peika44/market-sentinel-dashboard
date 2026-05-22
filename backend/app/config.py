from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
    kafka_topic: str = os.getenv("KAFKA_TOPIC", "market-prices")
    default_user_id: str = os.getenv("DEFAULT_USER_ID", "demo-user")


settings = Settings()

