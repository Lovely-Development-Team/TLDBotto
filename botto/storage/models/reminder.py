from datetime import datetime
from typing import TypedDict, Optional
from bson import ObjectId


class MongoReminder(TypedDict, total=False):
    _id: ObjectId
    date: datetime
    notes: Optional[str]
    remind_15_minutes_before: bool
    msg_id: str
    channel_id: str
    requester_id: Optional[str]
