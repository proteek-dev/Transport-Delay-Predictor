from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app import __version__
from app.api.routes import features, predictions, stops, trips, vehicles
from app.api.routes.health import router as health_router
from app.config import settings
from app.core.database import dispose_engine
from app.core.logging import configure_logging, get_logger
from app.core.redis import close_redis, get_redis

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    log.info("startup", env=settings.app_env, version=__version__)
    # warm redis connection so we fail fast on bad config
    try:
        await get_redis().ping()
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("redis_ping_failed", error=str(exc))
    yield
    await close_redis()
    await dispose_engine()
    log.info("shutdown")


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title="Transport Delay Predictor",
        version=__version__,
        description=(
            "Public transport delay prediction API backed by TransLink Queensland "
            "GTFS-Realtime feeds."
        ),
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    if settings.app_cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.app_cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/", include_in_schema=False)
    async def _root() -> dict[str, str]:
        return {"service": "transport-delay-predictor", "docs": "/docs"}

    app.include_router(health_router)
    app.include_router(stops.router, prefix="/api/v1/stops", tags=["stops"])
    app.include_router(trips.router, prefix="/api/v1/trips", tags=["trips"])
    app.include_router(vehicles.router, prefix="/api/v1/vehicles", tags=["vehicles"])
    app.include_router(predictions.router, prefix="/api/v1/predictions", tags=["predictions"])
    app.include_router(features.router, prefix="/api/v1/features", tags=["features"])

    return app


app = create_app()
