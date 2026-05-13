from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # `protected_namespaces=()` lets us keep MODEL_* env vars without Pydantic
    # warning that `model_artifact_path` etc. shadow its `model_*` API
    # (model_dump, model_validate, …). The fields are env-driven, not BaseModel
    # methods, so the collision is purely cosmetic.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=(),
    )

    # ---- App ----
    app_env: Literal["development", "test", "production"] = "development"
    app_log_level: str = "INFO"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_cors_origins: list[str] = Field(default_factory=list)

    # ---- DB ----
    # No defaults: credentials must come from .env so no literal password is
    # committed (GitGuardian flags hardcoded connection strings).
    database_url: str = ""
    database_sync_url: str = ""
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
    gtfs_rt_poll_interval: int = 60
    gtfs_static_refresh_hours: int = 24
    gtfs_request_timeout_seconds: float = 30.0

    # ---- Predictor ----
    predictor_history_days: int = 14
    predictor_min_observations: int = 5
    predictor_cache_ttl_seconds: int = 60

    # ---- BOM weather ----
    # Default to Brisbane (city + airport) — both report half-hourly observations.
    bom_station_ids: list[str] = Field(default_factory=lambda: ["94576", "94578"])
    # BOM blocks default httpx user-agents with HTTP 403; supply something descriptive.
    bom_user_agent: str = (
        "transport-delay-predictor/0.1 (+https://github.com/proteek-dev/Transport-Delay-Predictor)"
    )
    bom_poll_interval_seconds: int = 1800  # 30 min — matches BOM cadence

    # ---- Public holidays (Nager.Date) ----
    nager_holidays_url: HttpUrl = "https://date.nager.at/api/v3"  # type: ignore[assignment]

    # ---- Feature pipeline ----
    feature_window_days: int = 30
    feature_rebuild_interval_seconds: int = 21600  # 6 hours

    # ---- ML model (XGBoost delay predictor) ----
    model_artifact_path: str = "/srv/models/delay_predictor.joblib"
    model_training_window_days: int = 30
    model_min_training_samples: int = 200
    model_test_size: float = 0.2
    model_n_estimators: int = 400
    model_max_depth: int = 6
    model_learning_rate: float = 0.05
    # Daily retrain time (UTC). 02:30 UTC = 12:30 AEST — well outside peak travel.
    model_retrain_hour_utc: int = 2
    model_retrain_minute_utc: int = 30

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
