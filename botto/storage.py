import asyncio
import random
from collections import AsyncGenerator
from typing import Callable, Awaitable, Optional

import aiohttp
from aiohttp import ClientSession

from models import Meal, AirTableError, Intro


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
    async def get_intros(self) -> list[Intro]:
        raise NotImplementedError

    async def get_meals(self) -> list[Meal]:
        raise NotImplementedError

    async def retrieve_text(self, key: str) -> str:
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
        self.auth_header = {"Authorization": f"Bearer {self.airtable_key}"}
        self.semaphore = asyncio.Semaphore(5)
        self.cache = {}

    def _list_all_texts(
        self,
        filter_by_formula: str,
        sort: Optional[list[str]] = None,
        session: Optional[ClientSession] = None,
    ) -> AsyncGenerator[dict]:
        return self._iterate(self.times_url, filter_by_formula, sort, session)

    async def get_intros(self) -> Intro:
        texts_iterator = self._list_all_texts(filter_by_formula="{Name}='Intro'")
        return [Intro.from_airtable(x) async for x in texts_iterator][0]

    async def get_meals(self) -> list[Meal]:
        texts_iterator = self._list_all_texts(filter_by_formula="NOT({Name}='Intro')")
        return [Meal.from_airtable(x) async for x in texts_iterator]

    async def retrieve_text(self, key: str) -> str:
        result = await self._get(f"{self.texts_url}/{key}")
        text = result["fields"]["Text"]
        self.cache[key] = text
        return text

    async def get_text(self, key: str) -> str:
        if (text := self.cache.get(key)) and random.random() > 0.1:
            return text
        else:
            return await self.retrieve_text(key)
