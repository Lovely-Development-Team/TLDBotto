import datetime
import logging
from typing import Optional, Union

from discord import Member

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


def _get_yell_person(person: Union[Member, str]) -> str:
    if isinstance(person, str):
        return person.upper()
    else:
        return person.mention


def yell_at_someone(person: Optional[Union[Member, str]], text: Optional[str]) -> str:
    """
    Args:
        person (str): The person to yell at
        text (str): The message requesting yelling
    """
    person = _get_yell_person(person) if person else "LOVELY PERSON"
    message = text or "YOU SHOULD BE SLEEPING"
    return f"{person}, {message.lstrip().upper()}"


def get_local_times(local_times: list[datetime.datetime]) -> str:
    return "\n".join(
        [local_time.strftime("%Z (%z): %a %H:%M:%S") for local_time in local_times]
    )
