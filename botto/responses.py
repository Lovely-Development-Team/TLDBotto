import logging
from typing import Optional

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


def yell_at_someone(person: Optional[str], text: Optional[str]) -> str:
    """
    Args:
        person (str): The person to yell at
        text (str): The message requesting yelling
    """
    person = person or "lovely person"
    message = text or "YOU SHOULD BE SLEEPING"
    return f"{person.upper()}, {message.lstrip().upper()}"
