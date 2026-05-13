from __future__ import annotations

import datetime as dt

from pydantic import Field

from app.schemas.common import ORMModel


class StopOut(ORMModel):
    stop_id: str
    code: str | None = None
    name: str
    description: str | None = None
    lat: float
    lon: float
    location_type: int | None = None
    parent_station: str | None = None
    platform_code: str | None = None


class StopNearbyOut(StopOut):
    distance_m: float = Field(description="Distance from query point in metres.")


class Departure(ORMModel):
    trip_id: str
    route_id: str
    route_short_name: str | None = None
    headsign: str | None = None
    scheduled_departure: dt.datetime
    predicted_delay_seconds: int | None = None
    predicted_departure: dt.datetime | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source: str = Field(
        description="`realtime` if a TripUpdate is available, `predicted` otherwise."
    )
