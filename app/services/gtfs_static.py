"""GTFS static feed ingestion.

Downloads the TransLink SEQ static GTFS zip, parses the relevant tables with
pandas, and upserts them into Postgres. Run via `make ingest-static` or the
Celery beat schedule.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import io
import zipfile
from pathlib import Path

import httpx
import pandas as pd
from sqlalchemy import delete, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import session_scope
from app.core.logging import configure_logging, get_logger
from app.models import (
    Agency,
    Calendar,
    CalendarDate,
    Route,
    Stop,
    StopTime,
    Trip,
)

log = get_logger(__name__)


REQUIRED_FILES = {
    "agency.txt",
    "routes.txt",
    "stops.txt",
    "trips.txt",
    "stop_times.txt",
    "calendar.txt",
}
OPTIONAL_FILES = {"calendar_dates.txt"}


async def download_static_feed(dest: Path | None = None) -> bytes:
    log.info("gtfs_static_download_start", url=str(settings.gtfs_static_url))
    async with httpx.AsyncClient(timeout=settings.gtfs_request_timeout_seconds) as client:
        response = await client.get(str(settings.gtfs_static_url))
        response.raise_for_status()
        payload = response.content
    if dest is not None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload)
    log.info("gtfs_static_download_done", bytes=len(payload))
    return payload


def _parse_zip(payload: bytes) -> dict[str, pd.DataFrame]:
    archive = zipfile.ZipFile(io.BytesIO(payload))
    available = set(archive.namelist())
    missing = REQUIRED_FILES - available
    if missing:
        raise ValueError(f"GTFS archive missing required files: {sorted(missing)}")

    frames: dict[str, pd.DataFrame] = {}
    for name in REQUIRED_FILES | (OPTIONAL_FILES & available):
        with archive.open(name) as fp:
            # keep_default_na=False without na_values keeps empty cells as "" — letting our
            # `row.get(col) or None` pattern work without false positives from NaN floats.
            frames[name] = pd.read_csv(fp, dtype=str, keep_default_na=False)
    return frames


def _hms_to_interval(value: str) -> dt.timedelta:
    """GTFS times can exceed 24h (e.g. 25:30:00 for after-midnight services)."""
    hh, mm, ss = value.split(":")
    return dt.timedelta(hours=int(hh), minutes=int(mm), seconds=int(ss))


async def _upsert(
    session: AsyncSession,
    model,
    rows: list[dict],
    index_elements: list[str],
    batch_size: int = 1000,
) -> None:
    if not rows:
        return
    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        stmt = pg_insert(model).values(chunk)
        update_cols = {
            col.name: stmt.excluded[col.name]
            for col in model.__table__.columns
            if col.name not in index_elements
        }
        if update_cols:
            stmt = stmt.on_conflict_do_update(
                index_elements=index_elements,
                set_=update_cols,
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=index_elements)
        await session.execute(stmt)


def _to_bool(value: str) -> bool:
    return value.strip() == "1"


async def _ingest_frames(session: AsyncSession, frames: dict[str, pd.DataFrame]) -> None:
    log.info("gtfs_static_upsert_agencies", count=len(frames["agency.txt"]))
    agencies = [
        {
            "agency_id": row.get("agency_id") or "default",
            "name": row.get("agency_name") or "Unknown Agency",
            "url": row.get("agency_url") or None,
            "timezone": row.get("agency_timezone") or "Australia/Brisbane",
        }
        for row in frames["agency.txt"].to_dict(orient="records")
    ]
    await _upsert(session, Agency, agencies, ["agency_id"])

    log.info("gtfs_static_upsert_routes", count=len(frames["routes.txt"]))
    routes = [
        {
            "route_id": row["route_id"],
            "agency_id": row.get("agency_id") or "default",
            "short_name": row.get("route_short_name") or None,
            "long_name": row.get("route_long_name") or None,
            "route_type": int(row.get("route_type") or 3),
            "color": row.get("route_color") or None,
            "text_color": row.get("route_text_color") or None,
        }
        for row in frames["routes.txt"].to_dict(orient="records")
    ]
    await _upsert(session, Route, routes, ["route_id"])

    log.info("gtfs_static_upsert_stops", count=len(frames["stops.txt"]))
    stops = []
    for row in frames["stops.txt"].to_dict(orient="records"):
        lat = float(row["stop_lat"]) if row.get("stop_lat") else None
        lon = float(row["stop_lon"]) if row.get("stop_lon") else None
        if lat is None or lon is None:
            continue
        stops.append(
            {
                "stop_id": row["stop_id"],
                "code": row.get("stop_code") or None,
                "name": row["stop_name"],
                "description": row.get("stop_desc") or None,
                "lat": lat,
                "lon": lon,
                "location": f"SRID=4326;POINT({lon} {lat})",
                "location_type": int(row["location_type"]) if row.get("location_type") else None,
                "parent_station": row.get("parent_station") or None,
                "platform_code": row.get("platform_code") or None,
            }
        )
    await _upsert(session, Stop, stops, ["stop_id"])

    log.info("gtfs_static_upsert_trips", count=len(frames["trips.txt"]))
    trips = [
        {
            "trip_id": row["trip_id"],
            "route_id": row["route_id"],
            "service_id": row["service_id"],
            "headsign": row.get("trip_headsign") or None,
            "short_name": row.get("trip_short_name") or None,
            "direction_id": int(row["direction_id"]) if row.get("direction_id") else None,
            "block_id": row.get("block_id") or None,
            "shape_id": row.get("shape_id") or None,
        }
        for row in frames["trips.txt"].to_dict(orient="records")
    ]
    await _upsert(session, Trip, trips, ["trip_id"])

    log.info("gtfs_static_upsert_calendar", count=len(frames["calendar.txt"]))
    calendars = [
        {
            "service_id": row["service_id"],
            "monday": _to_bool(row["monday"]),
            "tuesday": _to_bool(row["tuesday"]),
            "wednesday": _to_bool(row["wednesday"]),
            "thursday": _to_bool(row["thursday"]),
            "friday": _to_bool(row["friday"]),
            "saturday": _to_bool(row["saturday"]),
            "sunday": _to_bool(row["sunday"]),
            "start_date": dt.datetime.strptime(row["start_date"], "%Y%m%d").date(),
            "end_date": dt.datetime.strptime(row["end_date"], "%Y%m%d").date(),
        }
        for row in frames["calendar.txt"].to_dict(orient="records")
    ]
    await _upsert(session, Calendar, calendars, ["service_id"])

    if "calendar_dates.txt" in frames:
        log.info("gtfs_static_upsert_calendar_dates", count=len(frames["calendar_dates.txt"]))
        dates = [
            {
                "service_id": row["service_id"],
                "date": dt.datetime.strptime(row["date"], "%Y%m%d").date(),
                "exception_type": int(row["exception_type"]),
            }
            for row in frames["calendar_dates.txt"].to_dict(orient="records")
        ]
        await _upsert(session, CalendarDate, dates, ["service_id", "date"])

    # stop_times is the big one; refresh wholesale per trip set
    log.info("gtfs_static_replace_stop_times", count=len(frames["stop_times.txt"]))
    await session.execute(delete(StopTime))
    stop_times = []
    for row in frames["stop_times.txt"].to_dict(orient="records"):
        if not row.get("arrival_time") or not row.get("departure_time"):
            continue
        stop_times.append(
            {
                "trip_id": row["trip_id"],
                "stop_sequence": int(row["stop_sequence"]),
                "stop_id": row["stop_id"],
                "arrival_time": _hms_to_interval(row["arrival_time"]),
                "departure_time": _hms_to_interval(row["departure_time"]),
                "pickup_type": int(row["pickup_type"]) if row.get("pickup_type") else None,
                "drop_off_type": (
                    int(row["drop_off_type"]) if row.get("drop_off_type") else None
                ),
                "shape_dist_traveled": (
                    float(row["shape_dist_traveled"])
                    if row.get("shape_dist_traveled")
                    else None
                ),
            }
        )
    # Bulk insert in chunks (no conflict possible after the wipe).
    chunk = 5000
    for i in range(0, len(stop_times), chunk):
        await session.execute(StopTime.__table__.insert(), stop_times[i : i + chunk])

    await session.execute(text("ANALYZE"))


async def ingest_static_feed() -> None:
    """End-to-end: download, parse, upsert."""
    payload = await download_static_feed()
    frames = _parse_zip(payload)
    async with session_scope() as session:
        await _ingest_frames(session, frames)
    log.info("gtfs_static_ingest_done")


def main() -> None:
    configure_logging()
    asyncio.run(ingest_static_feed())


if __name__ == "__main__":
    main()
