from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://booking:booking@localhost:5432/booking"
    redis_url: str = "redis://redis:6379/0"
    redis_enabled: bool = False

    web_concurrency: int = 2
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_timeout_seconds: int = 5
    db_lock_timeout_ms: int = 2000

    hold_ttl_seconds: int = 120
    payment_delay_seconds: int = 10
    payment_retry_window_seconds: int = 60
    max_payment_attempts: int = 3
    sweep_interval_seconds: int = 5
    seat_price: int = 500


@lru_cache
def get_settings() -> Settings:
    return Settings()
