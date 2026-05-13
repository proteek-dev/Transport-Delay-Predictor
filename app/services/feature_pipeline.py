"""Feature pipeline.

Two stages, both implemented as INSERT … SELECT … ON CONFLICT against Postgres:

1. `refresh_route_delay_stats` — recomputes `route_delay_stats` (avg / p50 / p90
   delay per route over a trailing window) from `delay_observations`.

2. `rebuild_training_features` — joins each `delay_observations` row with:
     - calendar features (hour-of-day, day-of-week, is_weekend, month)
     - the `public_holidays` table (is_public_holiday)
     - a windowed average of `weather_observations` across all SEQ stations
       (air_temp, rainfall, humidity)
     - `route_delay_stats` (route-level historical aggregates)
   …and materializes into `training_features` (one row per observation, target
   column = `delay_seconds`).

Both stages run inside Postgres for throughput; the function bodies just shape
the SQL and pass parameters in.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import text

from app.config import settings
from app.core.database import session_scope
from app.core.logging import get_logger

log = get_logger(__name__)


_ROUTE_STATS_SQL = text(
    """
    INSERT INTO route_delay_stats (
        route_id, window_start, window_end, sample_count,
        avg_delay_seconds, p50_delay_seconds, p90_delay_seconds, refreshed_at
    )
    SELECT
        route_id,
        :window_start,
        :window_end,
        COUNT(*)::int,
        AVG(delay_seconds)::float,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY delay_seconds)::float,
        PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY delay_seconds)::float,
        NOW()
    FROM delay_observations
    WHERE observed_at >= :since
    GROUP BY route_id
    ON CONFLICT (route_id) DO UPDATE SET
        window_start       = EXCLUDED.window_start,
        window_end         = EXCLUDED.window_end,
        sample_count       = EXCLUDED.sample_count,
        avg_delay_seconds  = EXCLUDED.avg_delay_seconds,
        p50_delay_seconds  = EXCLUDED.p50_delay_seconds,
        p90_delay_seconds  = EXCLUDED.p90_delay_seconds,
        refreshed_at       = EXCLUDED.refreshed_at;
    """
)


_FEATURES_SQL = text(
    """
    INSERT INTO training_features (
        observation_id, route_id, trip_id, stop_id, observed_at, service_date,
        hour_of_day, day_of_week, is_weekend, is_public_holiday, month,
        air_temp_c, rainfall_mm, humidity_pct,
        route_avg_delay_30d_s, route_p50_delay_30d_s, route_p90_delay_30d_s,
        delay_seconds, materialized_at
    )
    SELECT
        d.id,
        d.route_id,
        d.trip_id,
        d.stop_id,
        d.observed_at,
        d.service_date,
        d.hour_of_day,
        d.day_of_week,
        (d.day_of_week IN (5, 6))                         AS is_weekend,
        (h.date IS NOT NULL)                              AS is_public_holiday,
        EXTRACT(MONTH FROM d.service_date)::smallint      AS month,
        w.air_temp_c,
        w.rainfall_mm,
        w.humidity_pct,
        rs.avg_delay_seconds,
        rs.p50_delay_seconds,
        rs.p90_delay_seconds,
        d.delay_seconds,
        NOW()
    FROM delay_observations d
    LEFT JOIN public_holidays h
        ON h.date = d.service_date
    LEFT JOIN LATERAL (
        SELECT
            AVG(air_temp_c)::float   AS air_temp_c,
            AVG(rainfall_mm)::float  AS rainfall_mm,
            AVG(humidity_pct)::float AS humidity_pct
        FROM weather_observations wo
        WHERE wo.observed_at BETWEEN d.observed_at - INTERVAL '90 minutes'
                                 AND d.observed_at + INTERVAL '30 minutes'
    ) w ON TRUE
    LEFT JOIN route_delay_stats rs
        ON rs.route_id = d.route_id
    WHERE d.observed_at >= :since
    ON CONFLICT (observation_id) DO UPDATE SET
        is_public_holiday      = EXCLUDED.is_public_holiday,
        air_temp_c             = EXCLUDED.air_temp_c,
        rainfall_mm            = EXCLUDED.rainfall_mm,
        humidity_pct           = EXCLUDED.humidity_pct,
        route_avg_delay_30d_s  = EXCLUDED.route_avg_delay_30d_s,
        route_p50_delay_30d_s  = EXCLUDED.route_p50_delay_30d_s,
        route_p90_delay_30d_s  = EXCLUDED.route_p90_delay_30d_s,
        delay_seconds          = EXCLUDED.delay_seconds,
        materialized_at        = EXCLUDED.materialized_at;
    """
)


async def refresh_route_delay_stats(window_days: int | None = None) -> int:
    """Recompute route-level aggregates over a trailing window."""
    window = window_days or settings.feature_window_days
    now = dt.datetime.now(dt.UTC)
    since = now - dt.timedelta(days=window)
    async with session_scope() as session:
        result = await session.execute(
            _ROUTE_STATS_SQL,
            {
                "since": since,
                "window_start": since.date(),
                "window_end": now.date(),
            },
        )
    rowcount = result.rowcount or 0
    log.info("route_delay_stats_refreshed", rows=rowcount, window_days=window)
    return rowcount


async def rebuild_training_features(window_days: int | None = None) -> int:
    """Materialize `training_features` for observations in the trailing window.

    Idempotent: ON CONFLICT on `observation_id` updates derived columns so the
    table stays current as weather / holiday / route-stats inputs evolve.
    """
    window = window_days or settings.feature_window_days
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=window)
    async with session_scope() as session:
        result = await session.execute(_FEATURES_SQL, {"since": since})
    rowcount = result.rowcount or 0
    log.info("training_features_rebuilt", rows=rowcount, window_days=window)
    return rowcount


async def run_pipeline(window_days: int | None = None) -> dict[str, int]:
    """Refresh stats first, then rebuild features — order matters."""
    stats = await refresh_route_delay_stats(window_days)
    features = await rebuild_training_features(window_days)
    return {"route_stats": stats, "training_features": features}
