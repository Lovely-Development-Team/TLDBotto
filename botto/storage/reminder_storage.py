import logging
from typing import AsyncGenerator
from datetime import datetime
from typing import Optional

from aiohttp import ClientSession

from botto.models import Reminder
from botto.storage.storage import Storage

log = logging.getLogger(__name__)


class ReminderStorage(Storage):
    def __init__(self, airtable_base: str, airtable_key: str):
        super().__init__(airtable_base, airtable_key)
        self.reminders_url = "https://api.airtable.com/v0/{base}/Reminders".format(
            base=airtable_base
        )

    def _list_all_reminders(
        self,
        filter_by_formula: Optional[str],
        sort: Optional[list[str]] = None,
        session: Optional[ClientSession] = None,
    ) -> AsyncGenerator[dict, None]:
        return self._iterate(
            self.reminders_url,
            filter_by_formula=filter_by_formula,
            sort=sort,
            session=session,
        )

    async def retrieve_reminders(self) -> AsyncGenerator[Reminder, None]:
        reminders_iterator = self._list_all_reminders(filter_by_formula=None)
        async for reminder in reminders_iterator:
            yield Reminder.from_airtable(reminder)

    async def retrieve_reminder(self, key: str) -> Reminder:
        result = await self._get(f"{self.reminders_url}/{key}")
        return Reminder.from_airtable(result)

    async def add_reminder(
        self,
        timestamp: datetime,
        notes: str,
        msg_id: Optional[str],
        channel_id: Optional[str],
        requester_id: Optional[str],
        advance_reminder: bool = False,
    ) -> Reminder:
        reminder_data = {
            "Date": timestamp.isoformat(),
            "Notes": notes,
            "15 Minutes Before": advance_reminder,
            "Message ID": msg_id,
            "Channel ID": channel_id,
            "Requester ID": requester_id,
        }
        response = await self._insert(self.reminders_url, reminder_data)
        return Reminder.from_airtable(response)

    async def remove_reminder(self, *reminder_ids: str):
        log.debug(f"Deleting reminders: {reminder_ids}")
        await self._delete(self.reminders_url, list(reminder_ids))
        log.debug(f"Deleted reminders: {reminder_ids}")
