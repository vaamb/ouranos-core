from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
import pytest

from ouranos.web_server.dependencies import get_time_window, http_datetime


class TestHttpDatetime:
    def test_none(self):
        assert http_datetime(None) is None

    def test_naive_is_utc(self):
        dt = http_datetime("2026-10-20T10:00:00")
        assert dt == datetime(2026, 10, 20, 10, tzinfo=timezone.utc)

    def test_offset_kept(self):
        dt = http_datetime("2026-10-20T10:00:00+05:30")
        assert dt.utcoffset() == timedelta(hours=5, minutes=30)

    def test_failure_payload(self):
        with pytest.raises(HTTPException) as exc_info:
            http_datetime("not a datetime")
        assert exc_info.value.status_code == 422


class TestGetTimeWindow:
    def test_mixed_naive_and_aware(self):
        # Used to raise a `TypeError`, i.e. a 500, when subtracting naive from aware
        time_window = get_time_window(rounding=10, grace_time=0)(
            start_time="2026-10-20T10:00:00",
            end_time="2026-10-20T12:00:00+00:00",
            window_length=None,
        )
        assert time_window.start == datetime(2026, 10, 20, 10, tzinfo=timezone.utc)
        assert time_window.end == datetime(2026, 10, 20, 12, tzinfo=timezone.utc)

    def test_failure_payload(self):
        with pytest.raises(HTTPException) as exc_info:
            get_time_window(rounding=10, grace_time=0)(
                start_time="not a datetime", end_time=None, window_length=None)
        assert exc_info.value.status_code == 422
