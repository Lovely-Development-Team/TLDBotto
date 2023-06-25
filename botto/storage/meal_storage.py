import asyncio
import logging
from typing import Optional, AsyncGenerator

from aiohttp import ClientSession

from botto.models import Intro, Meal
from botto.storage.storage import Storage

log = logging.getLogger(__name__)


class MealStorage(Storage):
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


class AirtableMealStorage(MealStorage):
    def __init__(self, airtable_base: str, airtable_key: str):
        super().__init__(airtable_base, airtable_key)
        self.times_url = "https://api.airtable.com/v0/{base}/Times".format(
            base=airtable_base
        )
        self.texts_url = "https://api.airtable.com/v0/{base}/Texts".format(
            base=airtable_base
        )
        self.reminders_url = "https://api.airtable.com/v0/{base}/Reminders".format(
            base=airtable_base
        )
        self.meals_cache: list[Meal] = []
        self.text_lock = asyncio.Lock()
        self.text_cache = {}

    def _list_all_texts(
        self,
        filter_by_formula: Optional[str],
        sort: Optional[list[str]] = None,
        session: Optional[ClientSession] = None,
    ) -> AsyncGenerator[dict, None]:
        return self._iterate(
            self.times_url,
            filter_by_formula=filter_by_formula,
            sort=sort,
            session=session,
        )

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
