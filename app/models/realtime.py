from __future__ import annotations

import datetime as dt

from geoalchemy2 import Geography
from sqlalchemy import BigInteger, Date, DateTime, Float, ForeignKey, Integer, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class VehiclePosition(Base):
    __tablename__ = "vehicle_positions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    vehicle_id: Mapped[str] = mapped_column(Text, nullable=False)
    trip_id: Mapped[str | None] = mapped_column(Text, index=True)
    route_id: Mapped[str | None] = mapped_column(Text, index=True)
    recorded_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    location: Mapped[str] = mapped_column(
        Geography(geometry_type="POINT", srid=4326), nullable=False
    )
    bearing: Mapped[float | None] = mapped_column(Float)
    speed: Mapped[float | None] = mapped_column(Float)
    status: Mapped[int | None] = mapped_column(SmallInteger)
    congestion_level: Mapped[int | None] = mapped_column(SmallInteger)
    stop_sequence: Mapped[int | None] = mapped_column(Integer)
    current_stop_id: Mapped[str | None] = mapped_column(Text)


class TripUpdate(Base):
    __tablename__ = "trip_updates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trip_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    route_id: Mapped[str | None] = mapped_column(Text, index=True)
    vehicle_id: Mapped[str | None] = mapped_column(Text)
    recorded_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    start_date: Mapped[dt.date | None] = mapped_column(Date)
    schedule_relationship: Mapped[int | None] = mapped_column(SmallInteger)

    stop_time_updates: Mapped[list[StopTimeUpdate]] = relationship(
        back_populates="trip_update", cascade="all, delete-orphan"
    )


class StopTimeUpdate(Base):
    __tablename__ = "stop_time_updates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trip_update_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("trip_updates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stop_id: Mapped[str | None] = mapped_column(Text, index=True)
    stop_sequence: Mapped[int | None] = mapped_column(Integer)
    arrival_delay_seconds: Mapped[int | None] = mapped_column(Integer)
    arrival_time: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    departure_delay_seconds: Mapped[int | None] = mapped_column(Integer)
    departure_time: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    schedule_relationship: Mapped[int | None] = mapped_column(SmallInteger)

    trip_update: Mapped[TripUpdate] = relationship(back_populates="stop_time_updates")
