from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, Date, DateTime, Integer, SmallInteger, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DelayObservation(Base):
    """Flattened, deduplicated record of an observed stop arrival/departure delay.

    Populated by an aggregation task that consumes TripUpdate/StopTimeUpdate rows.
    The (trip_id, stop_id, service_date) tuple is the natural key.
    """

    __tablename__ = "delay_observations"
    __table_args__ = (
        UniqueConstraint("trip_id", "stop_id", "service_date", name="uq_delay_obs_natural"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    route_id: Mapped[str] = mapped_column(Text, nullable=False)
    trip_id: Mapped[str] = mapped_column(Text, nullable=False)
    stop_id: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    service_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    hour_of_day: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
