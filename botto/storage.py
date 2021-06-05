import asyncio
import random
from collections import AsyncGenerator
from typing import Callable, Awaitable, Optional, Generator, Any

import aiohttp
from aiohttp import ClientSession

from models import Meal, AirTableError, Intro, Reminder


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

    async def retrieve_reminders(self) -> AsyncGenerator[Reminder, Any, None]:
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
        filter_by_formula: str,
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
        self.semaphore = asyncio.Semaphore(5)
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

    def _list_all_reminders(
        self,
        filter_by_formula: Optional[str],
        sort: Optional[list[str]] = None,
        session: Optional[ClientSession] = None,
    ) -> AsyncGenerator[dict]:
        return self._iterate(self.reminders_url, filter_by_formula, sort, session)

    async def get_intros(self) -> Intro:
        texts_iterator = self._list_all_texts(filter_by_formula="{Name}='Intro'")
        return [Intro.from_airtable(x) async for x in texts_iterator][0]

    async def retrieve_meals(self) -> list[Meal]:
        texts_iterator = self._list_all_texts(filter_by_formula="NOT({Name}='Intro')")
        meals = [Meal.from_airtable(x) async for x in texts_iterator]
        self.meals_cache = meals
        return meals

    async def get_meals(self) -> list[Meal]:
        if self.meals_cache is not None:
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
        for meal in await self.retrieve_meals():
            async with self.text_lock:
                for text_ref in meal.texts:
                    await self.get_text(text_ref)

    async def update_text_cache(self):
        async with self.text_lock:
            for key in self.text_cache.keys():
                await self.retrieve_text(key)

    async def retrieve_reminders(self) -> AsyncGenerator[Reminder, Any, None]:
        reminders_iterator = self._list_all_reminders(filter_by_formula=None)
        async for reminder in reminders_iterator:
            yield Reminder.from_airtable(reminder)

    async def retrieve_reminder(self, key: str) -> Reminder:
        result = await self._get(f"{self.reminders_url}/{key}")
        return Reminder.from_airtable(result)