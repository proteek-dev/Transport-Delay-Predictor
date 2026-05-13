from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- App ----
    app_env: Literal["development", "test", "production"] = "development"
    app_log_level: str = "INFO"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_cors_origins: list[str] = Field(default_factory=list)

    # ---- DB ----
    database_url: str = "postgresql+asyncpg://tdp:tdp@postgres:5432/tdp"
    database_sync_url: str = "postgresql+psycopg://tdp:tdp@postgres:5432/tdp"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle_seconds: int = 1800

    # ---- Redis ----
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # ---- GTFS ----
    gtfs_static_url: HttpUrl = "https://gtfsrt.api.translink.com.au/GTFS/SEQ_GTFS.zip"  # type: ignore[assignment]
    gtfs_rt_trip_updates_url: HttpUrl = (  # type: ignore[assignment]
        "https://gtfsrt.api.translink.com.au/api/realtime/SEQ/TripUpdates"
    )
    gtfs_rt_vehicle_positions_url: HttpUrl = (  # type: ignore[assignment]
        "https://gtfsrt.api.translink.com.au/api/realtime/SEQ/VehiclePositions"
    )
    gtfs_rt_alerts_url: HttpUrl = (  # type: ignore[assignment]
        "https://gtfsrt.api.translink.com.au/api/realtime/SEQ/Alerts"
    )
    gtfs_rt_poll_interval: int = 30
    gtfs_static_refresh_hours: int = 24
    gtfs_request_timeout_seconds: float = 30.0

    # ---- Predictor ----
    predictor_history_days: int = 14
    predictor_min_observations: int = 5
    predictor_cache_ttl_seconds: int = 60

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
