from __future__ import annotations

import datetime as dt

from app.schemas.common import ORMModel


class TrainingFeatureOut(ORMModel):
    id: int
    observation_id: int
    route_id: str
    trip_id: str
    stop_id: str
    observed_at: dt.datetime
    service_date: dt.date
    hour_of_day: int
    day_of_week: int
    is_weekend: bool
    is_public_holiday: bool
    month: int
    air_temp_c: float | None = None
    rainfall_mm: float | None = None
    humidity_pct: float | None = None
    route_avg_delay_30d_s: float | None = None
    route_p50_delay_30d_s: float | None = None
    route_p90_delay_30d_s: float | None = None
    delay_seconds: int
    materialized_at: dt.datetime


class FeaturePipelineRunResult(ORMModel):
    route_stats: int
    training_features: int
