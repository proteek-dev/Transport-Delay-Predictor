from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class LiveDelay(BaseModel):
    trip_id: str
    route_id: str | None
    stop_id: str | None
    stop_sequence: int | None
    arrival_delay_seconds: int | None
    departure_delay_seconds: int | None
    delay_seconds: int | None = Field(
        description="Convenience: departure_delay_seconds if set, else arrival_delay_seconds.",
    )
    arrival_time: dt.datetime | None
    departure_time: dt.datetime | None
    recorded_at: dt.datetime


class LiveDelaysOut(BaseModel):
    snapshot_at: dt.datetime | None = Field(
        description="The most recent trip_update.recorded_at; null if no realtime data yet."
    )
    count: int = Field(ge=0)
    delays: list[LiveDelay]
