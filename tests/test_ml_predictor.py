from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.services.ml_predictor import (
    CATEGORICAL_FEATURES,
    FEATURE_COLUMNS,
    NUMERIC_FEATURES,
    TARGET,
    build_pipeline,
    derive_weather_condition,
    load_model,
    predict_single,
    save_model,
    train_and_evaluate,
)


def _synthetic_dataset(n: int = 600, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    routes = [f"R{i}" for i in range(8)]
    stops = [f"S{i}" for i in range(20)]
    rainfall = rng.choice([np.nan, 0.0, 0.5, 3.0], size=n, p=[0.1, 0.6, 0.2, 0.1])

    df = pd.DataFrame(
        {
            "route_id": rng.choice(routes, size=n),
            "stop_id": rng.choice(stops, size=n),
            "hour_of_day": rng.integers(0, 24, size=n),
            "day_of_week": rng.integers(0, 7, size=n),
            "rainfall_mm": rainfall,
        }
    )
    df["weather_condition"] = derive_weather_condition(df["rainfall_mm"])

    # Build a label that depends on the features so the regressor has signal to learn.
    base = 30.0
    rush = np.where((df["hour_of_day"] >= 7) & (df["hour_of_day"] <= 9), 90.0, 0.0)
    rain = np.where(df["weather_condition"] == "heavy_rain", 60.0, 0.0)
    rain += np.where(df["weather_condition"] == "light_rain", 20.0, 0.0)
    noise = rng.normal(0, 15, size=n)
    df[TARGET] = (base + rush + rain + noise).clip(min=-30).astype(int)
    return df


def test_derive_weather_condition_buckets() -> None:
    rainfall = pd.Series([None, 0.0, 0.2, 0.3, 1.5, 5.0])
    conditions = derive_weather_condition(rainfall)
    assert conditions.tolist() == [
        "unknown",
        "clear",
        "clear",
        "light_rain",
        "light_rain",
        "heavy_rain",
    ]


def test_feature_columns_match_spec() -> None:
    # Sanity: the task definition is (route_id, stop_id, hour, day_of_week, weather_condition).
    assert set(CATEGORICAL_FEATURES) == {"route_id", "stop_id", "weather_condition"}
    assert set(NUMERIC_FEATURES) == {"hour_of_day", "day_of_week"}
    assert FEATURE_COLUMNS == CATEGORICAL_FEATURES + NUMERIC_FEATURES


def test_pipeline_trains_evaluates_and_round_trips(tmp_path: Path) -> None:
    df = _synthetic_dataset()
    pipeline, metrics = train_and_evaluate(df)

    assert metrics.sample_count == len(df)
    assert metrics.train_count + metrics.test_count == len(df)
    assert metrics.rmse_train >= 0
    assert metrics.rmse_test >= 0
    # Trees should at least beat naive variance of the noise (sd≈15) by a clear margin on
    # synthetic data with strong signal.
    assert metrics.rmse_test < 50.0

    artifact = tmp_path / "delay_predictor.joblib"
    save_model(pipeline, metrics, artifact)
    assert artifact.exists()

    loaded_pipeline, loaded_metrics = load_model(artifact)
    assert loaded_metrics["sample_count"] == metrics.sample_count

    # Inference works with both seen and unseen categoricals (unknown_value=-1).
    seen = predict_single(
        loaded_pipeline,
        route_id="R0",
        stop_id="S0",
        hour=8,
        day_of_week=1,
        weather_condition="heavy_rain",
    )
    unseen = predict_single(
        loaded_pipeline,
        route_id="ROUTE_NEVER_SEEN",
        stop_id="STOP_NEVER_SEEN",
        hour=8,
        day_of_week=1,
        weather_condition="heavy_rain",
    )
    assert isinstance(seen, float)
    assert isinstance(unseen, float)


def test_build_pipeline_handles_unknown_categoricals() -> None:
    df = _synthetic_dataset(n=200)
    pipeline = build_pipeline()
    pipeline.fit(df[FEATURE_COLUMNS], df[TARGET])

    novel = pd.DataFrame(
        [
            {
                "route_id": "NEW_ROUTE",
                "stop_id": "NEW_STOP",
                "weather_condition": "blizzard",  # not in training set
                "hour_of_day": 10,
                "day_of_week": 3,
            }
        ]
    )
    # OrdinalEncoder with handle_unknown='use_encoded_value' must not raise.
    prediction = pipeline.predict(novel[FEATURE_COLUMNS])
    assert prediction.shape == (1,)


@pytest.mark.parametrize("samples", [50, 100, 199])
def test_train_skipped_below_threshold_marker(samples: int) -> None:
    # The threshold-skip logic lives in train_delay_model; here we just verify
    # train_and_evaluate itself doesn't impose a minimum and works on small inputs.
    df = _synthetic_dataset(n=samples)
    pipeline, metrics = train_and_evaluate(df)
    assert metrics.sample_count == samples
    assert pipeline.named_steps["regressor"].n_estimators > 0
