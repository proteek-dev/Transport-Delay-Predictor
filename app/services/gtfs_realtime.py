"""GTFS-Realtime ingestion.

Fetches TransLink SEQ TripUpdates and VehiclePositions protobuf feeds and
persists them. Designed to be invoked by Celery beat on a tight schedule
(default 30s — TransLink updates every ~15-30s).
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Iterable

import httpx
from google.transit import gtfs_realtime_pb2
from sqlalchemy.dialects.postgresql import insert as pg_insert
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.core.database import session_scope
from app.core.logging import get_logger
from app.models import DelayObservation, StopTimeUpdate, TripUpdate, VehiclePosition

log = get_logger(__name__)


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
    retry=retry_if_exception_type((httpx.HTTPError,)),
)
async def _fetch_pb(url: str) -> gtfs_realtime_pb2.FeedMessage:
    async with httpx.AsyncClient(timeout=settings.gtfs_request_timeout_seconds) as client:
        response = await client.get(url)
        response.raise_for_status()
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)
    return feed


def _epoch_to_dt(epoch: int | None) -> dt.datetime | None:
    if not epoch:
        return None
    return dt.datetime.fromtimestamp(epoch, tz=dt.UTC)


async def ingest_vehicle_positions() -> int:
    feed = await _fetch_pb(str(settings.gtfs_rt_vehicle_positions_url))
    rows: list[dict] = []
    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue
        vp = entity.vehicle
        if not vp.HasField("position"):
            continue
        recorded_at = _epoch_to_dt(vp.timestamp) or dt.datetime.now(dt.UTC)
        lat = vp.position.latitude
        lon = vp.position.longitude
        rows.append(
            {
                "vehicle_id": vp.vehicle.id or entity.id,
                "trip_id": vp.trip.trip_id or None,
                "route_id": vp.trip.route_id or None,
                "recorded_at": recorded_at,
                "lat": lat,
                "lon": lon,
                "location": f"SRID=4326;POINT({lon} {lat})",
                "bearing": vp.position.bearing if vp.position.HasField("bearing") else None,
                "speed": vp.position.speed if vp.position.HasField("speed") else None,
                "status": vp.current_status if vp.HasField("current_status") else None,
                "congestion_level": (
                    vp.congestion_level if vp.HasField("congestion_level") else None
                ),
                "stop_sequence": (
                    vp.current_stop_sequence if vp.HasField("current_stop_sequence") else None
                ),
                "current_stop_id": vp.stop_id or None,
            }
        )

    if not rows:
        log.info("gtfs_rt_vehicle_positions_empty")
        return 0

    async with session_scope() as session:
        await session.execute(VehiclePosition.__table__.insert(), rows)

    log.info("gtfs_rt_vehicle_positions_ingested", count=len(rows))
    return len(rows)


async def ingest_trip_updates() -> int:
    feed = await _fetch_pb(str(settings.gtfs_rt_trip_updates_url))
    n_trips = 0
    n_obs = 0
    async with session_scope() as session:
        for entity in feed.entity:
            if not entity.HasField("trip_update"):
                continue
            tu = entity.trip_update
            recorded_at = _epoch_to_dt(tu.timestamp) or dt.datetime.now(dt.UTC)
            start_date = (
                dt.datetime.strptime(tu.trip.start_date, "%Y%m%d").date()
                if tu.trip.start_date
                else None
            )
            trip_update = TripUpdate(
                trip_id=tu.trip.trip_id,
                route_id=tu.trip.route_id or None,
                vehicle_id=tu.vehicle.id or None,
                recorded_at=recorded_at,
                start_date=start_date,
                schedule_relationship=(
                    tu.trip.schedule_relationship
                    if tu.trip.HasField("schedule_relationship")
                    else None
                ),
            )
            session.add(trip_update)
            await session.flush()

            observation_rows: list[dict] = []
            for stu in tu.stop_time_update:
                arrival_delay = stu.arrival.delay if stu.HasField("arrival") else None
                arrival_time = (
                    _epoch_to_dt(stu.arrival.time)
                    if stu.HasField("arrival") and stu.arrival.HasField("time")
                    else None
                )
                departure_delay = stu.departure.delay if stu.HasField("departure") else None
                departure_time = (
                    _epoch_to_dt(stu.departure.time)
                    if stu.HasField("departure") and stu.departure.HasField("time")
                    else None
                )
                session.add(
                    StopTimeUpdate(
                        trip_update_id=trip_update.id,
                        stop_id=stu.stop_id or None,
                        stop_sequence=(
                            stu.stop_sequence if stu.HasField("stop_sequence") else None
                        ),
                        arrival_delay_seconds=arrival_delay,
                        arrival_time=arrival_time,
                        departure_delay_seconds=departure_delay,
                        departure_time=departure_time,
                        schedule_relationship=(
                            stu.schedule_relationship
                            if stu.HasField("schedule_relationship")
                            else None
                        ),
                    )
                )

                delay = arrival_delay if arrival_delay is not None else departure_delay
                if delay is None or not stu.stop_id or not tu.trip.route_id or not start_date:
                    continue
                observation_rows.append(
                    {
                        "route_id": tu.trip.route_id,
                        "trip_id": tu.trip.trip_id,
                        "stop_id": stu.stop_id,
                        "observed_at": recorded_at,
                        "service_date": start_date,
                        "hour_of_day": recorded_at.hour,
                        "day_of_week": recorded_at.weekday(),
                        "delay_seconds": int(delay),
                    }
                )

            if observation_rows:
                # Natural-key upsert keeps the latest observation per (trip, stop, day).
                stmt = pg_insert(DelayObservation).values(observation_rows)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_delay_obs_natural",
                    set_={
                        "delay_seconds": stmt.excluded.delay_seconds,
                        "observed_at": stmt.excluded.observed_at,
                        "hour_of_day": stmt.excluded.hour_of_day,
                        "day_of_week": stmt.excluded.day_of_week,
                    },
                )
                await session.execute(stmt)
                n_obs += len(observation_rows)
            n_trips += 1

    log.info("gtfs_rt_trip_updates_ingested", trips=n_trips, observations=n_obs)
    return n_trips


async def prune_old_realtime(retention_hours: int = 6) -> int:
    """Drop trip_updates / vehicle_positions older than `retention_hours`.

    delay_observations are kept long-term because they feed the predictor.
    """
    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(hours=retention_hours)
    async with session_scope() as session:
        from sqlalchemy import delete

        r1 = await session.execute(delete(TripUpdate).where(TripUpdate.recorded_at < cutoff))
        r2 = await session.execute(
            delete(VehiclePosition).where(VehiclePosition.recorded_at < cutoff)
        )
    removed = (r1.rowcount or 0) + (r2.rowcount or 0)
    log.info("gtfs_rt_prune_done", removed=removed, cutoff=cutoff.isoformat())
    return removed


__all__: Iterable[str] = (
    "ingest_vehicle_positions",
    "ingest_trip_updates",
    "prune_old_realtime",
)
