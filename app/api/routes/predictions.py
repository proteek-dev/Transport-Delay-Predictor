from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Query

from app.api.deps import DBSession
from app.schemas.prediction import PredictionOut, PredictionRequest
from app.services.predictor import predict_delay

router = APIRouter()


@router.get("", response_model=PredictionOut)
async def predict(
    session: DBSession,
    route_id: str = Query(...),
    stop_id: str = Query(...),
    target_time: dt.datetime | None = Query(
        default=None, description="ISO-8601; defaults to `now`."
    ),
) -> PredictionOut:
    return await predict_delay(
        session,
        route_id=route_id,
        stop_id=stop_id,
        target_time=target_time or dt.datetime.now(dt.UTC),
    )


@router.post("", response_model=PredictionOut)
async def predict_post(payload: PredictionRequest, session: DBSession) -> PredictionOut:
    return await predict_delay(
        session,
        route_id=payload.route_id,
        stop_id=payload.stop_id,
        target_time=payload.target_time,
    )
