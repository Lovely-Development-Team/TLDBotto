import datetime
from typing import Union

from arrow import Arrow


def is_naive(time: Union[datetime.datetime, Arrow]) -> bool:
    return time.tzinfo is None or time.tzinfo.utcoffset(time) is None