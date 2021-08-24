import datetime
from typing import Union

from arrow import Arrow


def is_naive(time: Union[datetime.datetime, Arrow]) -> bool:
    return time.tzinfo is None or time.tzinfo.utcoffset(time) is None


def convert_24_hours(hours: int, is_pm: bool) -> int:
    hours_is_12 = hours == 12
    if is_pm and not hours_is_12:
        return hours + 12
    elif not is_pm and hours_is_12:
        return 0
    else:
        return hours
