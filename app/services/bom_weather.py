"""BOM weather observation ingester.

The Bureau of Meteorology exposes the latest ~72 hours of station observations
as JSON under product IDQ60901 (Queensland). Each station has a 5-digit WMO ID.

Example endpoint:
  http://www.bom.gov.au/fwo/IDQ60901/IDQ60901.94576.json

BOM requires a non-default User-Agent header — bare `python-httpx/...` requests
are rejected with HTTP 403. We supply one from settings.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

import httpx
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
from app.models import WeatherObservation

log = get_logger(__name__)


BOM_PRODUCT = "IDQ60901"  # Queensland half-hourly observations


def _build_station_url(station_id: str) -> str:
    return f"http://www.bom.gov.au/fwo/{BOM_PRODUCT}/{BOM_PRODUCT}.{station_id}.json"


def _parse_aifstime_utc(value: str | None) -> dt.datetime | None:
    """BOM uses `aifstime_utc` of form `YYYYMMDDHHMMSS` in UTC."""
    if not value or len(value) < 14:
        return None
    try:
        return dt.datetime.strptime(value[:14], "%Y%m%d%H%M%S").replace(tzinfo=dt.UTC)
    except ValueError:
        return None


def _parse_float(value: Any) -> float | None:
    """BOM uses `-` for missing readings, strings for some numerics."""
    if value is None or value == "-" or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_observations(payload: dict[str, Any], station_id: str) -> list[dict[str, Any]]:
    """Pure function: given a parsed BOM JSON response, return rows ready for upsert."""
    data = (payload.get("observations") or {}).get("data") or []
    rows: list[dict[str, Any]] = []
    for entry in data:
        observed_at = _parse_aifstime_utc(entry.get("aifstime_utc"))
        if observed_at is None:
            continue
        rows.append(
            {
                "station_id": station_id,
                "observed_at": observed_at,
                "air_temp_c": _parse_float(entry.get("air_temp")),
                "rainfall_mm": _parse_float(entry.get("rain_trace")),
                "humidity_pct": _parse_float(entry.get("rel_hum")),
                "wind_speed_kmh": _parse_float(entry.get("wind_spd_kmh")),
                "source": "bom_IDQ60901",
            }
        )
    return rows


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
    retry=retry_if_exception_type((httpx.HTTPError,)),
)
async def _fetch_station(client: httpx.AsyncClient, station_id: str) -> dict[str, Any]:
    response = await client.get(_build_station_url(station_id))
    response.raise_for_status()
    return response.json()


async def ingest_weather() -> int:
    """Poll every configured SEQ station, upsert into `weather_observations`.

    On-conflict-do-nothing because BOM rows are immutable per (station, observed_at).
    """
    if not settings.bom_station_ids:
        log.info("bom_weather_no_stations_configured")
        return 0

    headers = {"User-Agent": settings.bom_user_agent}
    all_rows: list[dict[str, Any]] = []
    async with httpx.AsyncClient(
        timeout=settings.gtfs_request_timeout_seconds, headers=headers
    ) as client:
        for station_id in settings.bom_station_ids:
            try:
                payload = await _fetch_station(client, station_id)
            except httpx.HTTPError as exc:
                log.warning("bom_weather_fetch_failed", station=station_id, error=str(exc))
                continue
            station_rows = parse_observations(payload, station_id)
            log.info(
                "bom_weather_station_parsed",
                station=station_id,
                rows=len(station_rows),
            )
            all_rows.extend(station_rows)

    if not all_rows:
        return 0

    async with session_scope() as session:
        # Chunk inserts so a single station's worth of rows fits well below libpq limits.
        chunk = 500
        for i in range(0, len(all_rows), chunk):
            stmt = pg_insert(WeatherObservation).values(all_rows[i : i + chunk])
            stmt = stmt.on_conflict_do_nothing(constraint="uq_weather_natural")
            await session.execute(stmt)

    log.info("bom_weather_ingest_done", rows=len(all_rows))
    return len(all_rows)
