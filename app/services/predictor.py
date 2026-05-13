from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.config import settings
from app.core.logging import get_logger
from app.models.observations import DelayObservation
from app.schemas.prediction import PredictionOut
from app.services import cache

log = get_logger(__name__)

_BUCKET_KEY = "predict:bucket:v1:{route}:{stop}:{hour}:{dow}"


@dataclass(slots=True)
class _BucketStats:
    sample_size: int
    mean: float
    p50: float | None
    p90: float | None


async def _bucket_stats(
    session: AsyncSession,
    *,
    route_id: str,
    stop_id: str,
    hour: int,
    day_of_week: int,
    since: dt.datetime,
) -> _BucketStats:
    stmt = select(
        func.count(DelayObservation.id),
        func.avg(DelayObservation.delay_seconds),
        func.percentile_cont(0.5).within_group(DelayObservation.delay_seconds.asc()),
        func.percentile_cont(0.9).within_group(DelayObservation.delay_seconds.asc()),
    ).where(
        DelayObservation.route_id == route_id,
        DelayObservation.stop_id == stop_id,
        DelayObservation.hour_of_day == hour,
        DelayObservation.day_of_week == day_of_week,
        DelayObservation.observed_at >= since,
    )
    row = (await session.execute(stmt)).one()
    count, mean, p50, p90 = row
    return _BucketStats(
        sample_size=int(count or 0),
        mean=float(mean or 0.0),
        p50=float(p50) if p50 is not None else None,
        p90=float(p90) if p90 is not None else None,
    )


async def _route_fallback(
    session: AsyncSession, *, route_id: str, since: dt.datetime
) -> _BucketStats:
    stmt = select(
        func.count(DelayObservation.id),
        func.avg(DelayObservation.delay_seconds),
    ).where(
        DelayObservation.route_id == route_id,
        DelayObservation.observed_at >= since,
    )
    count, mean = (await session.execute(stmt)).one()
    return _BucketStats(
        sample_size=int(count or 0),
        mean=float(mean or 0.0),
        p50=None,
        p90=None,
    )


def _confidence(sample_size: int) -> float:
    """Map sample size to a 0..1 confidence using a saturating curve."""
    if sample_size <= 0:
        return 0.0
    # 30 samples ~= 0.78, 100 samples ~= 0.95
    return float(min(1.0, 1.0 - math.exp(-sample_size / 30.0)))


async def predict_delay(
    session: AsyncSession,
    *,
    route_id: str,
    stop_id: str,
    target_time: dt.datetime,
) -> PredictionOut:
    """Predict the expected delay (seconds) for a route/stop at a given local time.

    Strategy:
      1. Average over (route, stop, hour-of-day, day-of-week) bucket in the trailing window.
      2. If too few observations, fall back to route-wide mean.
      3. If still empty, return 0 with confidence 0.
    """
    hour = target_time.hour
    dow = target_time.weekday()
    cache_key = _BUCKET_KEY.format(route=route_id, stop=stop_id, hour=hour, dow=dow)
    cached = await cache.get_json(cache_key)
    if cached is not None:
        return PredictionOut.model_validate(cached)

    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=settings.predictor_history_days)
    bucket = await _bucket_stats(
        session,
        route_id=route_id,
        stop_id=stop_id,
        hour=hour,
        day_of_week=dow,
        since=since,
    )

    if bucket.sample_size >= settings.predictor_min_observations:
        prediction = PredictionOut(
            route_id=route_id,
            stop_id=stop_id,
            target_time=target_time,
            predicted_delay_seconds=int(round(bucket.mean)),
            sample_size=bucket.sample_size,
            confidence=_confidence(bucket.sample_size),
            method="bucket_mean",
            p50_delay_seconds=int(round(bucket.p50)) if bucket.p50 is not None else None,
            p90_delay_seconds=int(round(bucket.p90)) if bucket.p90 is not None else None,
        )
    else:
        fallback = await _route_fallback(session, route_id=route_id, since=since)
        prediction = PredictionOut(
            route_id=route_id,
            stop_id=stop_id,
            target_time=target_time,
            predicted_delay_seconds=int(round(fallback.mean)),
            sample_size=fallback.sample_size,
            confidence=_confidence(fallback.sample_size) * 0.5,
            method="route_fallback" if fallback.sample_size else "no_data",
        )

    await cache.set_json(
        cache_key,
        prediction.model_dump(mode="json"),
        ttl_seconds=settings.predictor_cache_ttl_seconds,
    )
    return prediction
