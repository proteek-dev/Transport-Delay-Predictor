from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_, select

from app.api.deps import DBSession
from app.models import Route, Stop, StopTime, Trip
from app.models.realtime import StopTimeUpdate, TripUpdate
from app.schemas.stop import Departure, StopNearbyOut, StopOut
from app.services.predictor import predict_delay

router = APIRouter()


@router.get("", response_model=list[StopOut])
async def list_stops(
    session: DBSession,
    q: str | None = Query(default=None, description="Fuzzy match on stop name or code."),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[Stop]:
    stmt = select(Stop)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Stop.name.ilike(like), Stop.code.ilike(like)))
    stmt = stmt.order_by(Stop.name).limit(limit).offset(offset)
    return list((await session.execute(stmt)).scalars())


@router.get("/nearby", response_model=list[StopNearbyOut])
async def nearby_stops(
    session: DBSession,
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_m: int = Query(default=500, ge=1, le=10_000),
    limit: int = Query(default=25, ge=1, le=100),
) -> list[StopNearbyOut]:
    point = func.ST_GeogFromText(f"SRID=4326;POINT({lon} {lat})")
    distance = func.ST_Distance(Stop.location, point).label("distance_m")
    stmt = (
        select(Stop, distance)
        .where(func.ST_DWithin(Stop.location, point, radius_m))
        .order_by(distance)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [
        StopNearbyOut(
            **StopOut.model_validate(stop).model_dump(),
            distance_m=float(dist),
        )
        for stop, dist in rows
    ]


@router.get("/{stop_id}", response_model=StopOut)
async def get_stop(stop_id: str, session: DBSession) -> Stop:
    stop = await session.get(Stop, stop_id)
    if stop is None:
        raise HTTPException(status_code=404, detail="stop not found")
    return stop


@router.get("/{stop_id}/departures", response_model=list[Departure])
async def upcoming_departures(
    stop_id: str,
    session: DBSession,
    window_minutes: int = Query(default=60, ge=1, le=240),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[Departure]:
    """Upcoming departures from a stop, enriched with realtime delay or a prediction."""
    stop = await session.get(Stop, stop_id)
    if stop is None:
        raise HTTPException(status_code=404, detail="stop not found")

    now = dt.datetime.now(dt.UTC)
    today = now.date()
    seconds_into_day = (
        now.hour * 3600 + now.minute * 60 + now.second
    )  # local-ish; GTFS times are in agency tz, this is good-enough
    window_end_seconds = seconds_into_day + window_minutes * 60

    # Pull scheduled departures from stop_times for active trips
    stmt = (
        select(StopTime, Trip, Route)
        .join(Trip, Trip.trip_id == StopTime.trip_id)
        .join(Route, Route.route_id == Trip.route_id)
        .where(
            StopTime.stop_id == stop_id,
            func.extract("epoch", StopTime.departure_time).between(
                seconds_into_day, window_end_seconds
            ),
        )
        .order_by(StopTime.departure_time)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()

    departures: list[Departure] = []
    for stop_time, trip, route in rows:
        scheduled = dt.datetime.combine(today, dt.time()) + stop_time.departure_time
        scheduled = scheduled.replace(tzinfo=dt.UTC)

        rt = await _latest_realtime_delay(session, trip.trip_id, stop_id)
        if rt is not None:
            departures.append(
                Departure(
                    trip_id=trip.trip_id,
                    route_id=route.route_id,
                    route_short_name=route.short_name,
                    headsign=trip.headsign,
                    scheduled_departure=scheduled,
                    predicted_delay_seconds=rt,
                    predicted_departure=scheduled + dt.timedelta(seconds=rt),
                    confidence=1.0,
                    source="realtime",
                )
            )
            continue

        prediction = await predict_delay(
            session,
            route_id=route.route_id,
            stop_id=stop_id,
            target_time=scheduled,
        )
        departures.append(
            Departure(
                trip_id=trip.trip_id,
                route_id=route.route_id,
                route_short_name=route.short_name,
                headsign=trip.headsign,
                scheduled_departure=scheduled,
                predicted_delay_seconds=prediction.predicted_delay_seconds,
                predicted_departure=scheduled
                + dt.timedelta(seconds=prediction.predicted_delay_seconds),
                confidence=prediction.confidence,
                source="predicted",
            )
        )

    return departures


async def _latest_realtime_delay(
    session, trip_id: str, stop_id: str
) -> int | None:
    stmt = (
        select(StopTimeUpdate.departure_delay_seconds, StopTimeUpdate.arrival_delay_seconds)
        .join(TripUpdate, TripUpdate.id == StopTimeUpdate.trip_update_id)
        .where(TripUpdate.trip_id == trip_id, StopTimeUpdate.stop_id == stop_id)
        .order_by(TripUpdate.recorded_at.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    dep, arr = row
    return dep if dep is not None else arr
