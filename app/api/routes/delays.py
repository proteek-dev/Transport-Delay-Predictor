from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import DBSession
from app.models.realtime import StopTimeUpdate, TripUpdate
from app.schemas.delays import LiveDelay, LiveDelaysOut

router = APIRouter()


@router.get("/live", response_model=LiveDelaysOut, tags=["delays"])
async def live_delays(
    session: DBSession,
    route_id: str | None = Query(default=None, description="Filter to a single route."),
    stop_id: str | None = Query(default=None, description="Filter to a single stop."),
    snapshot_window_seconds: int = Query(
        default=90,
        ge=10,
        le=600,
        description=(
            "How far back from the latest trip_update.recorded_at to include. "
            "The default 90s covers one realtime poll cadence (60s) plus a buffer."
        ),
    ),
    limit: int = Query(default=200, ge=1, le=1000),
) -> LiveDelaysOut:
    """Latest known delays from the most recent GTFS-RT TripUpdates snapshot.

    The endpoint anchors on `MAX(trip_updates.recorded_at)` and returns every
    StopTimeUpdate from trip updates inside `snapshot_window_seconds` of that
    anchor. That gives the freshest view of running delays without leaking in
    stale updates from earlier polls.
    """
    latest_recorded: dt.datetime | None = await session.scalar(
        select(func.max(TripUpdate.recorded_at))
    )
    if latest_recorded is None:
        return LiveDelaysOut(snapshot_at=None, count=0, delays=[])

    threshold = latest_recorded - dt.timedelta(seconds=snapshot_window_seconds)

    stmt = (
        select(
            TripUpdate.trip_id,
            TripUpdate.route_id,
            TripUpdate.recorded_at,
            StopTimeUpdate.stop_id,
            StopTimeUpdate.stop_sequence,
            StopTimeUpdate.arrival_delay_seconds,
            StopTimeUpdate.departure_delay_seconds,
            StopTimeUpdate.arrival_time,
            StopTimeUpdate.departure_time,
        )
        .join(StopTimeUpdate, StopTimeUpdate.trip_update_id == TripUpdate.id)
        .where(TripUpdate.recorded_at >= threshold)
    )
    if route_id is not None:
        stmt = stmt.where(TripUpdate.route_id == route_id)
    if stop_id is not None:
        stmt = stmt.where(StopTimeUpdate.stop_id == stop_id)

    stmt = stmt.order_by(TripUpdate.recorded_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).all()

    delays = [
        LiveDelay(
            trip_id=row.trip_id,
            route_id=row.route_id,
            stop_id=row.stop_id,
            stop_sequence=row.stop_sequence,
            arrival_delay_seconds=row.arrival_delay_seconds,
            departure_delay_seconds=row.departure_delay_seconds,
            delay_seconds=(
                row.departure_delay_seconds
                if row.departure_delay_seconds is not None
                else row.arrival_delay_seconds
            ),
            arrival_time=row.arrival_time,
            departure_time=row.departure_time,
            recorded_at=row.recorded_at,
        )
        for row in rows
    ]

    return LiveDelaysOut(snapshot_at=latest_recorded, count=len(delays), delays=delays)
