from __future__ import annotations

import asyncio
from typing import Any

from celery import shared_task

from app.core.logging import get_logger
from app.services.gtfs_realtime import (
    ingest_trip_updates,
    ingest_vehicle_positions,
    prune_old_realtime,
)
from app.services.gtfs_static import ingest_static_feed

log = get_logger(__name__)


def _run(coro: Any) -> Any:
    """Bridge async services into Celery's sync task context.

    Each task creates its own loop — Celery prefork workers fork cleanly and
    don't share event-loop state, which keeps asyncpg pools tidy.
    """
    return asyncio.run(coro)


@shared_task(name="app.workers.tasks.poll_trip_updates", bind=True, max_retries=3)
def poll_trip_updates(self) -> int:
    try:
        return _run(ingest_trip_updates())
    except Exception as exc:
        log.exception("poll_trip_updates_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=5)


@shared_task(name="app.workers.tasks.poll_vehicle_positions", bind=True, max_retries=3)
def poll_vehicle_positions(self) -> int:
    try:
        return _run(ingest_vehicle_positions())
    except Exception as exc:
        log.exception("poll_vehicle_positions_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=5)


@shared_task(name="app.workers.tasks.prune_realtime")
def prune_realtime(retention_hours: int = 6) -> int:
    return _run(prune_old_realtime(retention_hours))


@shared_task(name="app.workers.tasks.refresh_static_feed", bind=True, max_retries=2)
def refresh_static_feed(self) -> None:
    try:
        _run(ingest_static_feed())
    except Exception as exc:
        log.exception("refresh_static_feed_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=300)
