from __future__ import annotations

import datetime as dt

from app.services.holidays import parse_holidays


def test_keeps_national_holidays_and_qld_specific() -> None:
    payload = [
        {"date": "2026-01-01", "localName": "New Year's Day", "name": "New Year's Day",
         "counties": None},
        {"date": "2026-10-05", "localName": "Labour Day (QLD)", "name": "Labour Day",
         "counties": ["AU-QLD"]},
        {"date": "2026-03-09", "localName": "Labour Day (VIC)", "name": "Labour Day",
         "counties": ["AU-VIC"]},
    ]
    rows = parse_holidays(payload)
    dates = [r["date"] for r in rows]
    assert dt.date(2026, 1, 1) in dates
    assert dt.date(2026, 10, 5) in dates
    assert dt.date(2026, 3, 9) not in dates


def test_falls_back_to_english_name_when_local_missing() -> None:
    payload = [{"date": "2026-04-25", "name": "Anzac Day", "counties": None}]
    rows = parse_holidays(payload)
    assert rows[0]["name"] == "Anzac Day"


def test_bad_rows_are_skipped_not_raised() -> None:
    payload = [
        {"date": None, "name": "x", "counties": None},
        {"date": "not-a-date", "name": "y", "counties": None},
        {"date": "2026-12-25", "name": "Christmas", "counties": None},
    ]
    rows = parse_holidays(payload)
    assert [r["date"] for r in rows] == [dt.date(2026, 12, 25)]
