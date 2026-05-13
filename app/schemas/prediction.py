from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class PredictionRequest(BaseModel):
    route_id: str
    stop_id: str
    target_time: dt.datetime = Field(
        description="Local-clock time the rider plans to board. Used to derive hour/dow buckets."
    )


class PredictionOut(ORMModel):
    route_id: str
    stop_id: str
    target_time: dt.datetime
    predicted_delay_seconds: int
    sample_size: int = Field(description="Number of historical observations the prediction is based on.")
    confidence: float = Field(ge=0.0, le=1.0)
    method: str = Field(
        description="Which estimator produced the value (e.g. `bucket_mean`, `route_fallback`)."
    )
    p50_delay_seconds: int | None = None
    p90_delay_seconds: int | None = None
