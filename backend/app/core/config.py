from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://fishuser:fishpass123@localhost:5432/fish_stress_db"

    # MQTT (for connecting to Yashwanth's ESP32 data)
    MQTT_BROKER_IP: str = "localhost"
    MQTT_PORT: int = 1883

    # Security
    SECRET_KEY: str = "fish-stress-detection-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Alert channels
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None
    ALERT_EMAIL: Optional[str] = None
    EMAIL_PASSWORD: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Single instance used everywhere in the app
settings = Settings()