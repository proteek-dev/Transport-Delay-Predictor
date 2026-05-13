"""Unit tests for the GTFS static zip parser — exercised without a database."""
from __future__ import annotations

import io
import zipfile

import pytest

from app.services.gtfs_static import _hms_to_interval, _parse_zip


def _zip_with(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_hms_to_interval_handles_post_midnight_times() -> None:
    td = _hms_to_interval("25:30:15")
    assert td.total_seconds() == 25 * 3600 + 30 * 60 + 15


def test_parse_zip_rejects_archive_missing_required_files() -> None:
    payload = _zip_with({"agency.txt": "agency_id,agency_name,agency_timezone\n"})
    with pytest.raises(ValueError, match="missing required files"):
        _parse_zip(payload)


def test_parse_zip_loads_required_tables() -> None:
    files = {
        "agency.txt": "agency_id,agency_name,agency_timezone\nA,Acme,Australia/Brisbane\n",
        "routes.txt": "route_id,agency_id,route_short_name,route_type\nR1,A,66,3\n",
        "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\nS1,Central,-27.46,153.02\n",
        "trips.txt": "route_id,service_id,trip_id\nR1,SVC,T1\n",
        "stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "T1,08:00:00,08:00:30,S1,1\n",
        "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,"
        "start_date,end_date\nSVC,1,1,1,1,1,0,0,20260101,20261231\n",
    }
    frames = _parse_zip(_zip_with(files))
    assert set(frames) >= {
        "agency.txt",
        "routes.txt",
        "stops.txt",
        "trips.txt",
        "stop_times.txt",
        "calendar.txt",
    }
    assert frames["stops.txt"].iloc[0]["stop_id"] == "S1"
