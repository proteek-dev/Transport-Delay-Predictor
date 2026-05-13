from __future__ import annotations

import datetime as dt

from app.services.bom_weather import parse_observations

_SAMPLE_PAYLOAD = {
    "observations": {
        "header": [{"name": "Brisbane"}],
        "data": [
            {
                "aifstime_utc": "20260513020000",
                "air_temp": 22.4,
                "rain_trace": "0.2",
                "rel_hum": 78,
                "wind_spd_kmh": 11,
            },
            {
                # Missing values must coerce to None, not raise.
                "aifstime_utc": "20260513013000",
                "air_temp": 22.1,
                "rain_trace": "-",
                "rel_hum": None,
                "wind_spd_kmh": "",
            },
            {
                # Bad timestamp is dropped, not propagated.
                "aifstime_utc": "not-a-date",
                "air_temp": 99,
            },
        ],
    }
}


def test_parses_air_temp_rainfall_humidity_and_timestamps() -> None:
    rows = parse_observations(_SAMPLE_PAYLOAD, station_id="94576")
    assert len(rows) == 2
    first, second = rows
    assert first["station_id"] == "94576"
    assert first["observed_at"] == dt.datetime(2026, 5, 13, 2, 0, tzinfo=dt.UTC)
    assert first["air_temp_c"] == 22.4
    assert first["rainfall_mm"] == 0.2
    assert first["humidity_pct"] == 78.0
    assert first["wind_speed_kmh"] == 11.0
    assert first["source"] == "bom_IDQ60901"


def test_missing_readings_become_none_not_errors() -> None:
    rows = parse_observations(_SAMPLE_PAYLOAD, station_id="94576")
    second = rows[1]
    assert second["rainfall_mm"] is None
    assert second["humidity_pct"] is None
    assert second["wind_speed_kmh"] is None


def test_empty_payload_returns_empty_list() -> None:
    assert parse_observations({}, station_id="94576") == []
    assert parse_observations({"observations": {}}, station_id="94576") == []
