import datetime

from tzlocal import get_localzone


localTZ = get_localzone()


def dumps_dt(obj) -> str:
    if isinstance(obj, (datetime.datetime, datetime.date)):
        obj = obj.astimezone(tz=datetime.timezone.utc)
        return obj.replace(microsecond=0).isoformat()
    if isinstance(obj, datetime.time):
        obj = datetime.datetime.combine(datetime.date.today(), obj)
        obj = obj.astimezone(tz=localTZ)
        obj = obj.astimezone(tz=datetime.timezone.utc).time()
        return obj.replace(microsecond=0).isoformat()
