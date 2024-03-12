from datetime import datetime, timedelta, timezone

from ouranos.core.database.models.common import ImportanceLevel


timestamp_now = datetime.now(timezone.utc)


calendar_event = {
    "level": ImportanceLevel.low,
    "title": "An event",
    "description": "That is not really important",
    "start_time": timestamp_now + timedelta(days=2),
    "end_time": timestamp_now + timedelta(days=5),
}
