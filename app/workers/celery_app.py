from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import settings
from app.core.logging import configure_logging

configure_logging()

celery_app = Celery(
    "transport_delay_predictor",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_queue="default",
    task_time_limit=300,
    task_soft_time_limit=240,
    worker_max_tasks_per_child=200,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    enable_utc=True,
)

celery_app.conf.beat_schedule = {
    "poll-trip-updates": {
        "task": "app.workers.tasks.poll_trip_updates",
        "schedule": float(settings.gtfs_rt_poll_interval),
    },
    "poll-vehicle-positions": {
        "task": "app.workers.tasks.poll_vehicle_positions",
        "schedule": float(settings.gtfs_rt_poll_interval),
    },
    "prune-realtime-data": {
        "task": "app.workers.tasks.prune_realtime",
        "schedule": crontab(minute="*/15"),
    },
    "refresh-static-feed": {
        "task": "app.workers.tasks.refresh_static_feed",
        "schedule": crontab(hour=f"*/{settings.gtfs_static_refresh_hours}", minute=5),
    },
}


__all__ = ["celery_app"]
