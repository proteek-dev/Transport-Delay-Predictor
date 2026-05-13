"""Lazy joblib loader for the trained XGBoost delay model.

Loads the artifact at `settings.model_artifact_path` on first use and reloads
when the file's mtime changes — so the API picks up the latest retrain without
needing a restart, but pays the joblib cost only when something actually changed.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sklearn.pipeline import Pipeline

from app.config import settings
from app.core.logging import get_logger
from app.services.ml_predictor import load_model

log = get_logger(__name__)

_LOCK = threading.Lock()


@dataclass(slots=True)
class _CacheEntry:
    pipeline: Pipeline
    metrics: dict[str, Any]
    mtime_ns: int


_cache: _CacheEntry | None = None


def get_model() -> tuple[Pipeline, dict[str, Any]] | None:
    """Return (pipeline, metrics) if the artifact is present, else None.

    Thread-safe and mtime-aware: the next call after a retrain transparently
    reloads from disk. Returns None if the artifact has never been written.
    """
    global _cache

    path = Path(settings.model_artifact_path)
    try:
        mtime_ns = path.stat().st_mtime_ns
    except FileNotFoundError:
        return None

    cached = _cache
    if cached is not None and cached.mtime_ns == mtime_ns:
        return cached.pipeline, cached.metrics

    with _LOCK:
        # Re-check under the lock so concurrent first-loads don't both pay the joblib cost.
        cached = _cache
        if cached is not None and cached.mtime_ns == mtime_ns:
            return cached.pipeline, cached.metrics

        try:
            pipeline, metrics = load_model(path)
        except Exception as exc:  # pragma: no cover - filesystem race or corrupt artifact
            log.warning("ml_model_load_failed", path=str(path), error=str(exc))
            return None

        _cache = _CacheEntry(pipeline=pipeline, metrics=metrics, mtime_ns=mtime_ns)
        log.info(
            "ml_model_loaded",
            path=str(path),
            version=metrics.get("model_version"),
            rmse_test=metrics.get("rmse_test"),
        )
        return pipeline, metrics


def reset_cache() -> None:
    """Test hook: drop the in-memory cache so a subsequent get_model reloads."""
    global _cache
    with _LOCK:
        _cache = None
