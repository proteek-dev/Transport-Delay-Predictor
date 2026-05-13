from __future__ import annotations

import datetime as dt

from app.schemas.common import ORMModel


class TripOut(ORMModel):
    trip_id: str
    route_id: str
    service_id: str
    headsign: str | None = None
    short_name: str | None = None
    direction_id: int | None = None


class StopTimeOut(ORMModel):
    stop_sequence: int
    stop_id: str
    stop_name: str | None = None
    arrival_time: dt.timedelta
    departure_time: dt.timedelta


class TripDetailOut(TripOut):
    stop_times: list[StopTimeOut]
