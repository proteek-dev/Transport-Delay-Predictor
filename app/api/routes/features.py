from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import DBSession
from app.models import TrainingFeature
from app.schemas.features import FeaturePipelineRunResult, TrainingFeatureOut
from app.services.feature_pipeline import run_pipeline

router = APIRouter()


@router.get("", response_model=list[TrainingFeatureOut])
async def list_features(
    session: DBSession,
    route_id: str | None = Query(default=None),
    since: dt.datetime | None = Query(
        default=None, description="ISO-8601; defaults to the last 24h."
    ),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[TrainingFeature]:
    """Browse rows of `training_features` — useful for inspection or sampling."""
    cutoff = since or (dt.datetime.now(dt.UTC) - dt.timedelta(hours=24))
    stmt = (
        select(TrainingFeature)
        .where(TrainingFeature.observed_at >= cutoff)
        .order_by(TrainingFeature.observed_at.desc())
        .limit(limit)
    )
    if route_id:
        stmt = stmt.where(TrainingFeature.route_id == route_id)
    return list((await session.execute(stmt)).scalars())


@router.post("/refresh", response_model=FeaturePipelineRunResult)
async def refresh_features(
    window_days: int | None = Query(
        default=None, ge=1, le=365, description="Override the trailing window."
    ),
) -> FeaturePipelineRunResult:
    """Run the route-stats refresh + training-features rebuild on demand.

    Beat already invokes this on a schedule; this endpoint is for manual reruns
    after backfilling weather or holidays.
    """
    result = await run_pipeline(window_days)
    return FeaturePipelineRunResult(**result)
