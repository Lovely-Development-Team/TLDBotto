import logging
from typing import AsyncGenerator
from datetime import datetime
from typing import Optional

from aiohttp import ClientSession

from botto.storage.models.reminder import MongoReminder
from botto.storage.mongo_storage import MongoStorage
from pymongo.asynchronous.collection import AsyncCollection

log = logging.getLogger(__name__)


class ReminderStorage(MongoStorage):
    def __init__(self, username: str, password: str, host: str):
        super().__init__(username, password, host)
        self.database = self.client.get_database("general")
        self.collection: AsyncCollection[MongoReminder] = self.database.get_collection(
            "reminders"
        )

    async def _list_all_reminders(
        self,
    ) -> AsyncGenerator[MongoReminder, None]:
        async for reminder in self.collection.find({}):
            yield reminder

    async def retrieve_reminders(self) -> AsyncGenerator[MongoReminder, None]:
        reminders_iterator = self._list_all_reminders()
        async for reminder in reminders_iterator:
            yield reminder

    async def retrieve_reminder(self, key: str) -> MongoReminder:
        return await self.collection.find_one({"_id": key})

    async def add_reminder(
        self,
        timestamp: datetime,
        notes: str,
        msg_id: Optional[str],
        channel_id: Optional[str],
        requester_id: Optional[str],
        advance_reminder: bool = False,
    ) -> MongoReminder:
        new_reminder = MongoReminder(
            date=timestamp,
            notes=notes,
            remind_15_minutes_before=advance_reminder,
            msg_id=msg_id,
            channel_id=channel_id,
            requester_id=requester_id,
        )

        result = await self.collection.insert_one(new_reminder)
        new_reminder["_id"] = result.inserted_id
        return new_reminder

    async def remove_reminder(self, *reminder_ids: str):
        log.debug(f"Deleting reminders: {reminder_ids}")
        await self.collection.delete_many({"_id": {"$in": list(reminder_ids)}})
        log.debug(f"Deleted reminders: {reminder_ids}")
