from datetime import datetime, timedelta, timezone
import time

import pytest

from ouranos.core.utils import create_time_window


class TestCreateTimeWindow:
    def test_aware_converted_to_utc(self):
        time_window = create_time_window(
            start_time=datetime(2026, 10, 20, 10, tzinfo=timezone(timedelta(hours=5, minutes=30))),
            end_time=datetime(2026, 10, 20, 12, tzinfo=timezone.utc),
            grace_time=0,
        )
        assert time_window.start == datetime(2026, 10, 20, 4, 30, tzinfo=timezone.utc)
        assert time_window.end == datetime(2026, 10, 20, 12, tzinfo=timezone.utc)

    def test_naive_is_local(self, monkeypatch: pytest.MonkeyPatch):
        # Naive datetimes only come from `datetime.now()`, so they are local
        monkeypatch.setenv("TZ", "Asia/Kolkata")  # UTC+05:30, no DST
        time.tzset()
        try:
            time_window = create_time_window(
                start_time=datetime(2026, 10, 20, 10),
                end_time=datetime(2026, 10, 20, 12, tzinfo=timezone.utc),
                grace_time=0,
            )
        finally:
            monkeypatch.undo()
            time.tzset()
        assert time_window.start == datetime(2026, 10, 20, 4, 30, tzinfo=timezone.utc)

    def test_mixed_naive_and_aware(self):
        # Used to raise a `TypeError` when subtracting naive from aware
        time_window = create_time_window(
            start_time=datetime.now() - timedelta(days=1),
            end_time=datetime.now(timezone.utc),
        )
        assert time_window.start.tzinfo is timezone.utc
        assert time_window.end.tzinfo is timezone.utc

    def test_failure_max_window_length(self):
        with pytest.raises(ValueError):
            create_time_window(
                start_time=datetime(2026, 10, 1, tzinfo=timezone.utc),
                end_time=datetime(2026, 10, 20, tzinfo=timezone.utc),
                max_window_length=7,
            )
