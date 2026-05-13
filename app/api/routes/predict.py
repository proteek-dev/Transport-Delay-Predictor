from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Query

from app.api.deps import DBSession
from app.schemas.prediction import PredictWithIntervalOut
from app.services.predictor import predict_with_interval

router = APIRouter()


@router.get("/predict", response_model=PredictWithIntervalOut, tags=["predict"])
async def predict(
    session: DBSession,
    route_id: str = Query(..., description="GTFS route_id."),
    stop_id: str = Query(..., description="GTFS stop_id."),
    when: dt.datetime | None = Query(
        default=None,
        alias="datetime",
        description="ISO-8601 datetime to predict for. Defaults to `now` (UTC).",
    ),
) -> PredictWithIntervalOut:
    """Predicted delay (seconds) with an empirical confidence interval.

    Point estimate comes from the trained XGBoost model when its artifact is
    available, falling back to the bucket mean otherwise. The interval is the
    empirical [p10, p90] of historical delays in the same hour-of-day /
    day-of-week bucket — null when there are too few samples to form one.
    """
    return await predict_with_interval(
        session,
        route_id=route_id,
        stop_id=stop_id,
        when=when or dt.datetime.now(dt.UTC),
    )
