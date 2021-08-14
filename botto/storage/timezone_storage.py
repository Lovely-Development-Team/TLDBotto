import asyncio
import logging
from typing import Optional

from botto.models import TLDer, Timezone
from botto.storage.storage import Storage

log = logging.getLogger(__name__)


class TimezoneStorage(Storage):
    def __init__(self, airtable_base: str, airtable_key: str):
        super().__init__(airtable_base, airtable_key)
        self.airtable_key = airtable_key
        self.reminders_url = "https://api.airtable.com/v0/{base}/Reminders".format(
            base=airtable_base
        )
        self.tlders_url = "https://api.airtable.com/v0/{base}/TLDers".format(
            base=airtable_base
        )
        self.timezones_url = "https://api.airtable.com/v0/{base}/Timezones".format(
            base=airtable_base
        )
        self.tlders_lock = asyncio.Lock()
        self.tlders_cache: dict[str, TLDer] = {}
        self.timezones_lock = asyncio.Lock()
        self.timezones_cache: dict[str, Timezone] = {}
        self.auth_header = {"Authorization": f"Bearer {self.airtable_key}"}

    async def list_tlders(self) -> list[TLDer]:
        tlder_iterator = self._iterate(self.tlders_url, filter_by_formula=None)
        tlders = [TLDer.from_airtable(x) async for x in tlder_iterator]
        async with self.tlders_lock:
            for tlder in tlders:
                self.tlders_cache[tlder.discord_id] = tlder
        return tlders

    async def retrieve_tlder(self, discord_id: str) -> Optional[TLDer]:
        log.debug(f"Fetching TLDer with ID {discord_id}")
        result_iterator = self._iterate(
            self.tlders_url,
            filter_by_formula=f"{{Discord ID}}='{discord_id}'",
        )
        tlder_iterator = (TLDer.from_airtable(x) async for x in result_iterator)
        try:
            tlder = await tlder_iterator.__anext__()
            async with self.tlders_lock:
                self.tlders_cache[discord_id] = tlder
            return tlder
        except StopIteration:
            log.info(f"No TLDer found with ID {discord_id}")
            return None

    async def get_tlder(self, discord_id: str) -> Optional[TLDer]:
        await self.tlders_lock.acquire()
        if tlder := self.tlders_cache.get(discord_id):
            self.tlders_lock.release()
            return tlder
        else:
            self.tlders_lock.release()
            return await self.retrieve_tlder(discord_id)

    async def _retrieve_timezone(self, key: str) -> Timezone:
        result = await self._get(f"{self.timezones_url}/{key}")
        timezone = Timezone.from_airtable(result)
        async with self.timezones_lock:
            self.timezones_cache[key] = timezone
        return timezone

    async def get_timezone(self, key: str) -> Timezone:
        await self.timezones_lock.acquire()
        if timezone_string := self.timezones_cache.get(key):
            self.timezones_lock.release()
            return timezone_string
        else:
            self.timezones_lock.release()
            return await self._retrieve_timezone(key)

    async def update_tlder_timezone_cache(self):
        tlders = await self.list_tlders()
        for tlder in tlders:
            if timezone_id := tlder.timezone_id:
                await self._retrieve_timezone(timezone_id)

    async def find_timezone(
        self,
        name: str,
    ) -> Timezone:
        timezone_iterator = self._iterate(
            self.tlders_url,
            filter_by_formula=f"{{Name}}='{name}'",
        )
        timezone = [Timezone.from_airtable(x) async for x in timezone_iterator][0]
        async with self.tlders_lock:
            self.timezones_cache[timezone.id] = timezone
        return timezone

    async def add_timezone(self, name: str) -> Timezone:
        reminder_data = {"Name": name}
        response = await self._insert(self.timezones_url, reminder_data)
        return Timezone.from_airtable(response)