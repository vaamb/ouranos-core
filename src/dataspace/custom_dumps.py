import datetime

from tzlocal import get_localzone


localTZ = get_localzone()


def dumps_dt(obj) -> str:
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.replace(microsecond=0,
                           tzinfo=datetime.timezone.utc).isoformat()
    if isinstance(obj, datetime.time):
        obj = datetime.datetime.combine(datetime.date.today(), obj)
        obj = obj.replace(microsecond=0, tzinfo=datetime.timezone.utc)
        return obj.astimezone(tz=datetime.timezone.utc).time()
