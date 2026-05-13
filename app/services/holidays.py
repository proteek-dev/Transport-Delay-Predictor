"""Queensland public-holiday sync.

Uses the free Nager.Date API (https://date.nager.at). Their `/AU` endpoint
returns Australian holidays with a `counties` field listing AU-XX subdivisions
the holiday applies to. We keep rows that are either national (counties is
empty/null) or include `AU-QLD`.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.core.database import session_scope
from app.core.logging import get_logger
from app.models import PublicHoliday

log = get_logger(__name__)


def _qld_applicable(entry: dict[str, Any]) -> bool:
    counties = entry.get("counties")
    if not counties:
        return True  # national holiday
    return "AU-QLD" in counties


def parse_holidays(payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pure parser: pick QLD-applicable rows out of the Nager.Date response."""
    rows: list[dict[str, Any]] = []
    for entry in payload:
        if not _qld_applicable(entry):
            continue
        date_str = entry.get("date")
        if not date_str:
            continue
        try:
            date = dt.date.fromisoformat(date_str)
        except ValueError:
            continue
        rows.append(
            {
                "date": date,
                "name": entry.get("localName") or entry.get("name") or "Public holiday",
                "subdivision": "AU-QLD" if entry.get("counties") else "AU",
                "source": "nager.at",
            }
        )
    return rows


async def sync_qld_holidays(years: list[int] | None = None) -> int:
    """Pull current + next year by default."""
    if years is None:
        this_year = dt.date.today().year
        years = [this_year, this_year + 1]

    base = str(settings.nager_holidays_url).rstrip("/")
    all_rows: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=settings.gtfs_request_timeout_seconds) as client:
        for year in years:
            response = await client.get(f"{base}/PublicHolidays/{year}/AU")
            response.raise_for_status()
            rows = parse_holidays(response.json())
            log.info("holidays_year_parsed", year=year, count=len(rows))
            all_rows.extend(rows)

    if not all_rows:
        return 0

    async with session_scope() as session:
        stmt = pg_insert(PublicHoliday).values(all_rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["date"],
            set_={
                "name": stmt.excluded.name,
                "subdivision": stmt.excluded.subdivision,
                "source": stmt.excluded.source,
            },
        )
        await session.execute(stmt)

    log.info("holidays_sync_done", rows=len(all_rows))
    return len(all_rows)
