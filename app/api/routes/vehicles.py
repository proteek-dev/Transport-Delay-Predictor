from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import DBSession
from app.models import VehiclePosition
from app.schemas.vehicle import VehiclePositionOut

router = APIRouter()


@router.get("", response_model=list[VehiclePositionOut])
async def list_latest_vehicle_positions(
    session: DBSession,
    route_id: str | None = Query(default=None),
    bbox: str | None = Query(
        default=None, description="min_lon,min_lat,max_lon,max_lat — clips by bounding box."
    ),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[VehiclePosition]:
    """Latest known position per vehicle, optionally filtered."""
    latest_per_vehicle = (
        select(
            VehiclePosition.vehicle_id,
            func.max(VehiclePosition.recorded_at).label("latest"),
        )
        .group_by(VehiclePosition.vehicle_id)
        .subquery()
    )

    stmt = (
        select(VehiclePosition)
        .join(
            latest_per_vehicle,
            (VehiclePosition.vehicle_id == latest_per_vehicle.c.vehicle_id)
            & (VehiclePosition.recorded_at == latest_per_vehicle.c.latest),
        )
        .limit(limit)
    )

    if route_id:
        stmt = stmt.where(VehiclePosition.route_id == route_id)

    if bbox:
        try:
            min_lon, min_lat, max_lon, max_lat = (float(x) for x in bbox.split(","))
        except ValueError:
            return []
        envelope = func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
        stmt = stmt.where(func.ST_Intersects(VehiclePosition.location, envelope))

    return list((await session.execute(stmt)).scalars())
