from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RouteDelayStats(Base):
    """Trailing-window aggregate per route, refreshed by the feature pipeline."""

    __tablename__ = "route_delay_stats"

    route_id: Mapped[str] = mapped_column(Text, primary_key=True)
    window_start: Mapped[dt.date] = mapped_column(Date, nullable=False)
    window_end: Mapped[dt.date] = mapped_column(Date, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_delay_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    p50_delay_seconds: Mapped[float | None] = mapped_column(Float)
    p90_delay_seconds: Mapped[float | None] = mapped_column(Float)
    refreshed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TrainingFeature(Base):
    """One row per delay observation, joined with weather/holiday/route-history features.

    This is the materialized output of the feature pipeline. Columns are grouped as:
    - identifiers + label                          -> for grouping/splitting
    - calendar features (hour/dow/month/holiday)   -> bucketed categorical
    - weather features                             -> nullable, nearest-prior reading
    - route-level history                          -> denormalized from route_delay_stats

    A downstream trainer can stream rows by `observed_at` and treat `delay_seconds`
    as the regression target.
    """

    __tablename__ = "training_features"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    observation_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("delay_observations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    route_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    trip_id: Mapped[str] = mapped_column(Text, nullable=False)
    stop_id: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    service_date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)

    # ---- calendar features
    hour_of_day: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_weekend: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_public_holiday: Mapped[bool] = mapped_column(Boolean, nullable=False)
    month: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    # ---- weather features (averaged across SEQ stations, nearest-prior reading)
    air_temp_c: Mapped[float | None] = mapped_column(Float)
    rainfall_mm: Mapped[float | None] = mapped_column(Float)
    humidity_pct: Mapped[float | None] = mapped_column(Float)

    # ---- route-level history
    route_avg_delay_30d_s: Mapped[float | None] = mapped_column(Float)
    route_p50_delay_30d_s: Mapped[float | None] = mapped_column(Float)
    route_p90_delay_30d_s: Mapped[float | None] = mapped_column(Float)

    # ---- label
    delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False)

    materialized_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
