from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DBSession
from app.models import Stop, StopTime, Trip
from app.schemas.trip import StopTimeOut, TripDetailOut, TripOut

router = APIRouter()


@router.get("/{trip_id}", response_model=TripDetailOut)
async def get_trip(trip_id: str, session: DBSession) -> TripDetailOut:
    trip = (
        await session.execute(
            select(Trip)
            .options(selectinload(Trip.stop_times))
            .where(Trip.trip_id == trip_id)
        )
    ).scalar_one_or_none()
    if trip is None:
        raise HTTPException(status_code=404, detail="trip not found")

    stop_ids = [st.stop_id for st in trip.stop_times]
    stops_by_id = {
        s.stop_id: s
        for s in (await session.execute(select(Stop).where(Stop.stop_id.in_(stop_ids))))
        .scalars()
    }

    stop_times = [
        StopTimeOut(
            stop_sequence=st.stop_sequence,
            stop_id=st.stop_id,
            stop_name=stops_by_id.get(st.stop_id).name if stops_by_id.get(st.stop_id) else None,
            arrival_time=st.arrival_time,
            departure_time=st.departure_time,
        )
        for st in sorted(trip.stop_times, key=lambda x: x.stop_sequence)
    ]
    return TripDetailOut(
        **TripOut.model_validate(trip).model_dump(),
        stop_times=stop_times,
    )
