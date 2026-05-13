from __future__ import annotations

import datetime as dt

from geoalchemy2 import Geography
from sqlalchemy import Boolean, Date, Float, ForeignKey, Interval, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Agency(Base):
    __tablename__ = "agencies"

    agency_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(Text, nullable=False)

    routes: Mapped[list[Route]] = relationship(back_populates="agency")


class Route(Base):
    __tablename__ = "routes"

    route_id: Mapped[str] = mapped_column(Text, primary_key=True)
    agency_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("agencies.agency_id", ondelete="CASCADE")
    )
    short_name: Mapped[str | None] = mapped_column(Text, index=True)
    long_name: Mapped[str | None] = mapped_column(Text)
    route_type: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    color: Mapped[str | None] = mapped_column(Text)
    text_color: Mapped[str | None] = mapped_column(Text)

    agency: Mapped[Agency | None] = relationship(back_populates="routes")
    trips: Mapped[list[Trip]] = relationship(back_populates="route")


class Stop(Base):
    __tablename__ = "stops"

    stop_id: Mapped[str] = mapped_column(Text, primary_key=True)
    code: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    location: Mapped[str] = mapped_column(
        Geography(geometry_type="POINT", srid=4326), nullable=False
    )
    location_type: Mapped[int | None] = mapped_column(SmallInteger)
    parent_station: Mapped[str | None] = mapped_column(Text)
    platform_code: Mapped[str | None] = mapped_column(Text)


class Trip(Base):
    __tablename__ = "trips"

    trip_id: Mapped[str] = mapped_column(Text, primary_key=True)
    route_id: Mapped[str] = mapped_column(
        Text, ForeignKey("routes.route_id", ondelete="CASCADE"), nullable=False, index=True
    )
    service_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    headsign: Mapped[str | None] = mapped_column(Text)
    short_name: Mapped[str | None] = mapped_column(Text)
    direction_id: Mapped[int | None] = mapped_column(SmallInteger)
    block_id: Mapped[str | None] = mapped_column(Text)
    shape_id: Mapped[str | None] = mapped_column(Text)

    route: Mapped[Route] = relationship(back_populates="trips")
    stop_times: Mapped[list[StopTime]] = relationship(
        back_populates="trip", cascade="all, delete-orphan"
    )


class StopTime(Base):
    __tablename__ = "stop_times"

    trip_id: Mapped[str] = mapped_column(
        Text, ForeignKey("trips.trip_id", ondelete="CASCADE"), primary_key=True
    )
    stop_sequence: Mapped[int] = mapped_column(primary_key=True)
    stop_id: Mapped[str] = mapped_column(
        Text, ForeignKey("stops.stop_id", ondelete="CASCADE"), nullable=False, index=True
    )
    arrival_time: Mapped[dt.timedelta] = mapped_column(Interval, nullable=False)
    departure_time: Mapped[dt.timedelta] = mapped_column(Interval, nullable=False)
    pickup_type: Mapped[int | None] = mapped_column(SmallInteger)
    drop_off_type: Mapped[int | None] = mapped_column(SmallInteger)
    shape_dist_traveled: Mapped[float | None] = mapped_column(Float)

    trip: Mapped[Trip] = relationship(back_populates="stop_times")


class Calendar(Base):
    __tablename__ = "calendar"

    service_id: Mapped[str] = mapped_column(Text, primary_key=True)
    monday: Mapped[bool] = mapped_column(Boolean, nullable=False)
    tuesday: Mapped[bool] = mapped_column(Boolean, nullable=False)
    wednesday: Mapped[bool] = mapped_column(Boolean, nullable=False)
    thursday: Mapped[bool] = mapped_column(Boolean, nullable=False)
    friday: Mapped[bool] = mapped_column(Boolean, nullable=False)
    saturday: Mapped[bool] = mapped_column(Boolean, nullable=False)
    sunday: Mapped[bool] = mapped_column(Boolean, nullable=False)
    start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[dt.date] = mapped_column(Date, nullable=False)


class CalendarDate(Base):
    __tablename__ = "calendar_dates"

    service_id: Mapped[str] = mapped_column(Text, primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    exception_type: Mapped[int] = mapped_column(SmallInteger, nullable=False)
