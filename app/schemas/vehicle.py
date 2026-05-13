from __future__ import annotations

import datetime as dt

from app.schemas.common import ORMModel


class VehiclePositionOut(ORMModel):
    vehicle_id: str
    trip_id: str | None = None
    route_id: str | None = None
    recorded_at: dt.datetime
    lat: float
    lon: float
    bearing: float | None = None
    speed: float | None = None
    status: int | None = None
    stop_sequence: int | None = None
    current_stop_id: str | None = None
