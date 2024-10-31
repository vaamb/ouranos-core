from datetime import datetime, timedelta, timezone

import gaia_validators as gv


timestamp_now = datetime.now(timezone.utc)


calendar_event = {
    "level": gv.WarningLevel.low,
    "title": "An event",
    "description": "That is not really important",
    "start_time": timestamp_now + timedelta(days=2),
    "end_time": timestamp_now + timedelta(days=5),
}


wiki_topic_name = "Topic"
wiki_article_name = "Article"
wiki_article_content = "Content"
wiki_picture_name = "Picture"
wiki_picture_content = b"Picture"
