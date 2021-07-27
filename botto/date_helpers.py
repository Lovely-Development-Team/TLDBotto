import datetime


def is_naive(time: datetime.datetime) -> bool:
    return time.tzinfo is None or time.tzinfo.utcoffset(time) is None