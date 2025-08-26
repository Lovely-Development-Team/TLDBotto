from typing import TypedDict, NotRequired
from bson import ObjectId


class DiscordUser(TypedDict):
    _id: NotRequired[ObjectId]
    discord_id: str
    name: str
    timezone: str
