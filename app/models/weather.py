from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, DateTime, Float, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WeatherObservation(Base):
    """One row per (station, observed_at) — populated by the BOM ingester."""

    __tablename__ = "weather_observations"
    __table_args__ = (
        UniqueConstraint("station_id", "observed_at", name="uq_weather_natural"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    station_id: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    air_temp_c: Mapped[float | None] = mapped_column(Float)
    rainfall_mm: Mapped[float | None] = mapped_column(Float)
    humidity_pct: Mapped[float | None] = mapped_column(Float)
    wind_speed_kmh: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str | None] = mapped_column(Text)
