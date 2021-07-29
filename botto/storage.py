import asyncio
import logging
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Callable, Awaitable, Optional, Any, Literal

import aiohttp
from aiohttp import ClientSession

from .models import Meal, AirTableError, Intro, Reminder, TLDer, Timezone

log = logging.getLogger(__name__)


async def run_request(
    action_to_run: Callable[[ClientSession], Awaitable[dict]],
    session: Optional[ClientSession] = None,
):
    if not session:
        async with aiohttp.ClientSession() as new_session:
            return await action_to_run(new_session)
    else:
        return await action_to_run(session)


async def airtable_sleep():
    await asyncio.sleep(1.0 / 5)


class MealStorage:
    semaphore = asyncio.Semaphore(5)

    async def get_intros(self) -> Intro:
        raise NotImplementedError

    async def get_meals(self) -> list[Meal]:
        raise NotImplementedError

    async def get_text(self, key: str) -> str:
        raise NotImplementedError

    async def update_meals_cache(self):
        raise NotImplementedError

    async def update_text_cache(self):
        raise NotImplementedError

    async def _get(
        self,
        url: str,
        params: Optional[dict[str, str]] = None,
        session: Optional[ClientSession] = None,
    ) -> dict:
        async def run_fetch(session_to_use: ClientSession):
            async with session_to_use.get(
                url,
                params=params,
                headers=self.auth_header,
            ) as r:
                if r.status != 200:
                    raise AirTableError(r.url, await r.json())
                motto_response: dict = await r.json()
                return motto_response

        async with self.semaphore:
            result = await run_request(run_fetch, session)
            await airtable_sleep()
            return result

    async def _iterate(
        self,
        base_url: str,
        filter_by_formula: Optional[str],
        sort: Optional[list[str]] = None,
        session: Optional[ClientSession] = None,
    ) -> AsyncGenerator[dict]:
        params = {}
        if filter_by_formula:
            params = {"filterByFormula": filter_by_formula}
        if sort:
            for idx, field in enumerate(sort):
                params.update({"sort[{index}][field]".format(index=idx): field})
                params.update({"sort[{index}][direction]".format(index=idx): "asc"})
        offset = None
        while True:
            if offset:
                params.update(offset=offset)
            async with self.semaphore:
                response = await self._get(base_url, params, session)
                await airtable_sleep()
            records = response.get("records", [])
            for record in records:
                yield record
            offset = response.get("offset")
            if not offset:
                break

    async def _delete(
        self,
        base_url: str,
        records_to_delete: [str],
        session: Optional[ClientSession] = None,
    ):
        async def run_delete(session_to_use: ClientSession):
            async with session_to_use.delete(
                (
                    base_url
                    if len(records_to_delete) > 1
                    else base_url + f"/{records_to_delete[0]}"
                ),
                params=(
                    {"records": records_to_delete}
                    if len(records_to_delete) > 1
                    else None
                ),
                headers=self.auth_header,
            ) as r:
                if r.status != 200:
                    raise AirTableError(r.url, await r.json())

        async with self.semaphore:
            result = await run_request(run_delete, session)
            await airtable_sleep()
            return result

    async def _modify(
        self,
        url: str,
        method: Literal["post", "patch"],
        record: dict,
        session: Optional[ClientSession] = None,
    ):
        async def run_insert(session_to_use: ClientSession):
            data = {"fields": record}
            async with session_to_use.request(
                method,
                url,
                json=data,
                headers=self.auth_header,
            ) as r:
                if r.status != 200:
                    raise AirTableError(r.url, await r.json())
                motto_response: dict = await r.json()
                return motto_response

        async with self.semaphore:
            result = await run_request(run_insert, session)
            await airtable_sleep()
            return result

    async def _insert(
        self, url: str, record: dict, session: Optional[ClientSession] = None
    ) -> dict:
        return await self._modify(url, "post", record, session)

    async def _update(
        self, url: str, record: dict, session: Optional[ClientSession] = None
    ) -> dict:
        return await self._modify(url, "patch", record, session)


class AirtableMealStorage(MealStorage):
    def __init__(
        self,
        airtable_base: str,
        airtable_key: str,
    ):
        self.airtable_key = airtable_key
        self.times_url = "https://api.airtable.com/v0/{base}/Times".format(
            base=airtable_base
        )
        self.texts_url = "https://api.airtable.com/v0/{base}/Texts".format(
            base=airtable_base
        )
        self.reminders_url = "https://api.airtable.com/v0/{base}/Reminders".format(
            base=airtable_base
        )
        self.auth_header = {"Authorization": f"Bearer {self.airtable_key}"}
        self.meals_cache: list[Meal] = []
        self.text_lock = asyncio.Lock()
        self.text_cache = {}

    def _list_all_texts(
        self,
        filter_by_formula: Optional[str],
        sort: Optional[list[str]] = None,
        session: Optional[ClientSession] = None,
    ) -> AsyncGenerator[dict]:
        return self._iterate(self.times_url, filter_by_formula, sort, session)

    async def get_intros(self) -> Intro:
        texts_iterator = self._list_all_texts(filter_by_formula="{Name}='Intro'")
        return [Intro.from_airtable(x) async for x in texts_iterator][0]

    async def retrieve_meals(self) -> list[Meal]:
        texts_iterator = self._list_all_texts(filter_by_formula="NOT({Name}='Intro')")
        meals = [Meal.from_airtable(x) async for x in texts_iterator]
        self.meals_cache = meals
        log.info(f"Retrieved {len(meals)} meals")
        return meals

    async def get_meals(self) -> list[Meal]:
        if self.meals_cache is not None and len(self.meals_cache) > 0:
            return self.meals_cache
        else:
            return await self.retrieve_meals()

    async def retrieve_text(self, key: str) -> str:
        result = await self._get(f"{self.texts_url}/{key}")
        text = result["fields"]["Text"]
        self.text_cache[key] = text
        return text

    async def get_text(self, key: str) -> str:
        if text := self.text_cache.get(key):
            return text
        else:
            return await self.retrieve_text(key)

    async def update_meals_cache(self):
        total_fetches = 0
        async with self.text_lock:
            for meal in await self.retrieve_meals():
                fetches = [self.get_text(text_ref) for text_ref in meal.texts]
                await asyncio.gather(*fetches)
                total_fetches += len(fetches)
        log.debug(f"Ensured {total_fetches} texts are cached")

    async def update_text_cache(self):
        total_fetches = 0
        async with self.text_lock:
            fetches = [self.retrieve_text(key) for key in self.text_cache.keys()]
            await asyncio.gather(*fetches)
            total_fetches += len(fetches)
        log.debug(f"Retrieved {total_fetches} texts")


class ReminderStorage(MealStorage):
    def __init__(
        self,
        airtable_base: str,
        airtable_key: str,
    ):
        self.airtable_key = airtable_key
        self.reminders_url = "https://api.airtable.com/v0/{base}/Reminders".format(
            base=airtable_base
        )
        self.auth_header = {"Authorization": f"Bearer {self.airtable_key}"}

    def _list_all_reminders(
        self,
        filter_by_formula: Optional[str],
        sort: Optional[list[str]] = None,
        session: Optional[ClientSession] = None,
    ) -> AsyncGenerator[dict]:
        return self._iterate(self.reminders_url, filter_by_formula, sort, session)

    async def retrieve_reminders(self) -> AsyncGenerator[Reminder, Any, None]:
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
        advance_reminder: bool = False,
    ) -> Reminder:
        reminder_data = {
            "Date": timestamp.isoformat(),
            "Notes": notes,
            "15 Minutes Before": advance_reminder,
            "Message ID": msg_id,
            "Channel ID": channel_id,
        }
        response = await self._insert(self.reminders_url, reminder_data)
        return Reminder.from_airtable(response)

    async def remove_reminder(self, *reminder_ids: str):
        log.debug(f"Deleting reminders: {reminder_ids}")
        await self._delete(self.reminders_url, list(reminder_ids))
        log.debug(f"Deleted reminders: {reminder_ids}")


class TimezoneStorage(MealStorage):
    def __init__(
        self,
        airtable_base: str,
        airtable_key: str,
    ):
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

    async def retrieve_tlder(self, discord_id: str) -> TLDer:
        tlder_iterator = self._iterate(
            self.tlders_url,
            filter_by_formula=f"{{Discord ID}}='{discord_id}'",
        )
        tlder = [TLDer.from_airtable(x) async for x in tlder_iterator][0]
        async with self.tlders_lock:
            self.tlders_cache[discord_id] = tlder
        return tlder

    async def get_tlder(self, discord_id: str) -> TLDer:
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
