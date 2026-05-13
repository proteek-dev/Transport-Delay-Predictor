"""Lazy joblib loader for the trained XGBoost delay model.

Two backends, picked by `settings.model_s3_bucket`:
  - empty (default, local dev): mtime-based cache on `settings.model_artifact_path`.
  - non-empty (AWS deploy): S3 ETag-based cache; downloads to the local path
    when the bucket's object changes. The local file still acts as the
    on-disk cache between process restarts, so cold starts are quick.

In both cases the in-memory cache means hot requests don't touch disk or S3.
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
    version: str  # mtime_ns as string, or S3 ETag


_cache: _CacheEntry | None = None


def get_model() -> tuple[Pipeline, dict[str, Any]] | None:
    """Return (pipeline, metrics) if the artifact is available, else None.

    Thread-safe. Cache key is the local file mtime (local backend) or the S3
    object's ETag (S3 backend) — either way, calls after a retrain pick up
    the new artifact transparently.
    """
    if settings.model_s3_bucket:
        return _get_from_s3()
    return _get_from_local()


def _get_from_local() -> tuple[Pipeline, dict[str, Any]] | None:
    global _cache
    path = Path(settings.model_artifact_path)
    try:
        version = str(path.stat().st_mtime_ns)
    except FileNotFoundError:
        return None
    return _load_under_lock(path, version)


def _get_from_s3() -> tuple[Pipeline, dict[str, Any]] | None:
    global _cache
    bucket = settings.model_s3_bucket
    key = settings.model_s3_key
    path = Path(settings.model_artifact_path)

    import boto3  # noqa: PLC0415 - keep boto3 optional at module import time
    from botocore.exceptions import ClientError  # noqa: PLC0415

    s3 = boto3.client("s3")
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey"}:
            return None
        log.warning("ml_model_s3_head_failed", bucket=bucket, key=key, error=str(exc))
        return None

    etag = head["ETag"].strip('"')

    cached = _cache
    if cached is not None and cached.version == etag:
        return cached.pipeline, cached.metrics

    with _LOCK:
        cached = _cache
        if cached is not None and cached.version == etag:
            return cached.pipeline, cached.metrics

        path.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(bucket, key, str(path))
        log.info("ml_model_downloaded_s3", bucket=bucket, key=key, etag=etag)
        return _load_into_cache(path, etag)


def _load_under_lock(path: Path, version: str) -> tuple[Pipeline, dict[str, Any]] | None:
    cached = _cache
    if cached is not None and cached.version == version:
        return cached.pipeline, cached.metrics

    with _LOCK:
        cached = _cache
        if cached is not None and cached.version == version:
            return cached.pipeline, cached.metrics
        return _load_into_cache(path, version)


def _load_into_cache(path: Path, version: str) -> tuple[Pipeline, dict[str, Any]] | None:
    global _cache
    try:
        pipeline, metrics = load_model(path)
    except Exception as exc:  # pragma: no cover - filesystem race or corrupt artifact
        log.warning("ml_model_load_failed", path=str(path), error=str(exc))
        return None

    _cache = _CacheEntry(pipeline=pipeline, metrics=metrics, version=version)
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
