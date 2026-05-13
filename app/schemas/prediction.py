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
    sample_size: int = Field(
        description="Number of historical observations the prediction is based on.",
    )
    confidence: float = Field(ge=0.0, le=1.0)
    method: str = Field(
        description="Which estimator produced the value (e.g. `bucket_mean`, `route_fallback`)."
    )
    p50_delay_seconds: int | None = None
    p90_delay_seconds: int | None = None


class PredictionInterval(BaseModel):
    lower_seconds: int = Field(
        description="Lower bound of the empirical confidence interval, in seconds.",
    )
    upper_seconds: int = Field(
        description="Upper bound of the empirical confidence interval, in seconds.",
    )
    level: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Coverage level (e.g. 0.8 = empirical p10..p90 from the matching bucket).",
    )


class PredictWithIntervalOut(BaseModel):
    route_id: str
    stop_id: str
    datetime: dt.datetime = Field(
        description="The local-clock instant the prediction was requested for.",
    )
    predicted_delay_seconds: int = Field(description="Point estimate of the delay, in seconds.")
    confidence_interval: PredictionInterval | None = Field(
        default=None,
        description="Empirical [p10, p90] from the matching bucket, or null if too few samples.",
    )
    method: str = Field(
        description=(
            "Source of the point estimate: ml_model, bucket_mean, route_fallback, or no_data."
        ),
    )
    sample_size: int = Field(
        ge=0,
        description="Number of historical observations supporting the prediction.",
    )
    confidence: float = Field(ge=0.0, le=1.0)
