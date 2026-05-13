"""XGBoost regressor that predicts `delay_seconds` from the training_features table.

Pipeline:
  1. Pull the trailing `model_training_window_days` of rows from `training_features`.
  2. Derive a categorical `weather_condition` from `rainfall_mm`.
  3. Split train/test (default 80/20).
  4. sklearn Pipeline: ColumnTransformer(OrdinalEncoder for categoricals) -> XGBRegressor.
  5. Report train + test RMSE.
  6. Persist the fitted pipeline + metadata via joblib at `MODEL_ARTIFACT_PATH`.

Triggered manually via `make train-model` or automatically every 24 hours by
`app.workers.tasks.retrain_delay_model` (see beat schedule).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder
from sqlalchemy import select
from xgboost import XGBRegressor

from app.config import settings
from app.core.database import session_scope
from app.core.logging import get_logger
from app.models.features import TrainingFeature

log = get_logger(__name__)

CATEGORICAL_FEATURES = ["route_id", "stop_id", "weather_condition"]
NUMERIC_FEATURES = ["hour_of_day", "day_of_week"]
FEATURE_COLUMNS = CATEGORICAL_FEATURES + NUMERIC_FEATURES
TARGET = "delay_seconds"


@dataclass(slots=True, frozen=True)
class TrainingMetrics:
    sample_count: int
    train_count: int
    test_count: int
    rmse_train: float
    rmse_test: float
    features: list[str]
    target: str
    trained_at: str
    model_version: str


def derive_weather_condition(rainfall_mm: pd.Series) -> pd.Series:
    """Bucket rainfall (mm) into a small categorical.

    Buckets are pragmatic, not meteorological — `unknown` keeps rows with
    missing BOM readings instead of dropping them, since most delay rows
    will have weather coverage but a sizeable minority won't.
    """
    conditions = pd.Series("clear", index=rainfall_mm.index, dtype="object")
    conditions[rainfall_mm.isna()] = "unknown"
    conditions[rainfall_mm.fillna(0) > 0.2] = "light_rain"
    conditions[rainfall_mm.fillna(0) > 2.0] = "heavy_rain"
    return conditions


async def load_training_dataframe(window_days: int) -> pd.DataFrame:
    """Stream `training_features` rows from the trailing window into a DataFrame."""
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=window_days)
    async with session_scope() as session:
        stmt = select(
            TrainingFeature.route_id,
            TrainingFeature.stop_id,
            TrainingFeature.hour_of_day,
            TrainingFeature.day_of_week,
            TrainingFeature.rainfall_mm,
            TrainingFeature.delay_seconds,
        ).where(TrainingFeature.observed_at >= since)
        rows = (await session.execute(stmt)).all()

    df = pd.DataFrame(
        rows,
        columns=[
            "route_id",
            "stop_id",
            "hour_of_day",
            "day_of_week",
            "rainfall_mm",
            "delay_seconds",
        ],
    )
    if df.empty:
        return df
    df["weather_condition"] = derive_weather_condition(df["rainfall_mm"])
    return df


def build_pipeline() -> Pipeline:
    """sklearn Pipeline: OrdinalEncoder for categoricals + XGBRegressor.

    `handle_unknown='use_encoded_value'` keeps inference robust to unseen
    route_ids/stop_ids — they get the sentinel and the boosted trees fall
    back to splits on the remaining features.
    """
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "categorical",
                OrdinalEncoder(
                    handle_unknown="use_encoded_value",
                    unknown_value=-1,
                ),
                CATEGORICAL_FEATURES,
            ),
        ],
        remainder="passthrough",
        verbose_feature_names_out=False,
    )

    regressor = XGBRegressor(
        n_estimators=settings.model_n_estimators,
        max_depth=settings.model_max_depth,
        learning_rate=settings.model_learning_rate,
        objective="reg:squarederror",
        random_state=42,
        n_jobs=-1,
        tree_method="hist",
    )

    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("regressor", regressor),
        ]
    )


def train_and_evaluate(df: pd.DataFrame) -> tuple[Pipeline, TrainingMetrics]:
    X = df[FEATURE_COLUMNS]
    y = df[TARGET].astype(float)

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=settings.model_test_size,
        random_state=42,
    )

    pipeline = build_pipeline()
    pipeline.fit(X_train, y_train)

    rmse_train = float(np.sqrt(mean_squared_error(y_train, pipeline.predict(X_train))))
    rmse_test = float(np.sqrt(mean_squared_error(y_test, pipeline.predict(X_test))))

    now = dt.datetime.now(dt.UTC)
    metrics = TrainingMetrics(
        sample_count=len(df),
        train_count=len(X_train),
        test_count=len(X_test),
        rmse_train=rmse_train,
        rmse_test=rmse_test,
        features=FEATURE_COLUMNS,
        target=TARGET,
        trained_at=now.isoformat(),
        model_version=now.strftime("%Y%m%dT%H%M%SZ"),
    )
    return pipeline, metrics


def save_model(pipeline: Pipeline, metrics: TrainingMetrics, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": pipeline, "metrics": asdict(metrics)}, path)
    if settings.model_s3_bucket:
        _upload_to_s3(path, settings.model_s3_bucket, settings.model_s3_key)


def _upload_to_s3(path: Path, bucket: str, key: str) -> None:
    """Upload the joblib to S3. Lazy boto3 import so local dev isn't forced to install it."""
    import boto3  # noqa: PLC0415 - keep boto3 optional at import time

    s3 = boto3.client("s3")
    s3.upload_file(str(path), bucket, key)
    log.info("ml_model_uploaded_s3", bucket=bucket, key=key)


def load_model(path: Path) -> tuple[Pipeline, dict[str, Any]]:
    bundle = joblib.load(path)
    return bundle["pipeline"], bundle["metrics"]


def predict_single(
    pipeline: Pipeline,
    *,
    route_id: str,
    stop_id: str,
    hour: int,
    day_of_week: int,
    weather_condition: str,
) -> float:
    X = pd.DataFrame(
        [
            {
                "route_id": route_id,
                "stop_id": stop_id,
                "hour_of_day": hour,
                "day_of_week": day_of_week,
                "weather_condition": weather_condition,
            }
        ]
    )
    return float(pipeline.predict(X[FEATURE_COLUMNS])[0])


async def train_delay_model() -> dict[str, Any]:
    """End-to-end: load features, train+evaluate, persist. Returns a metrics dict."""
    log.info("ml_training_start", window_days=settings.model_training_window_days)
    df = await load_training_dataframe(settings.model_training_window_days)

    if len(df) < settings.model_min_training_samples:
        log.warning(
            "ml_training_skipped_insufficient_samples",
            count=len(df),
            required=settings.model_min_training_samples,
        )
        return {"status": "skipped", "sample_count": len(df)}

    pipeline, metrics = train_and_evaluate(df)
    save_model(pipeline, metrics, Path(settings.model_artifact_path))
    log.info("ml_training_done", **asdict(metrics))
    return {"status": "trained", **asdict(metrics)}


def main() -> None:
    """CLI entrypoint: `python -m app.services.ml_predictor`."""
    import asyncio

    from app.core.logging import configure_logging

    configure_logging()
    result = asyncio.run(train_delay_model())
    log.info("ml_training_cli_result", **result)


if __name__ == "__main__":
    main()
