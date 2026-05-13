from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app import __version__
from app.api.deps import DBSession
from app.core.redis import get_redis
from app.schemas.common import HealthStatus

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthStatus)
async def health(session: DBSession) -> HealthStatus:
    checks: dict[str, str] = {}
    overall = "ok"

    try:
        await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:  # pragma: no cover
        checks["postgres"] = f"error: {exc}"
        overall = "degraded"

    try:
        pong = await get_redis().ping()
        checks["redis"] = "ok" if pong else "error: no pong"
    except Exception as exc:  # pragma: no cover
        checks["redis"] = f"error: {exc}"
        overall = "degraded"

    return HealthStatus(status=overall, version=__version__, checks=checks)


@router.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"service": "transport-delay-predictor", "version": __version__, "docs": "/docs"}
