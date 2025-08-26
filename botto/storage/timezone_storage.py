import asyncio
import logging
from typing import Optional

from botto.models import TLDer, Timezone
from botto.storage.models.user import DiscordUser
from botto.storage.mongo_storage import MongoStorage
from pymongo.asynchronous.collection import AsyncCollection

log = logging.getLogger(__name__)


class TimezoneStorage(MongoStorage):
    def __init__(self, username: str, password: str, host: str):
        super().__init__(username, password, host)
        self.database = self.client.get_database("general")
        self.collection: AsyncCollection[DiscordUser] = self.database.get_collection(
            "users"
        )
        self.tlders_lock = asyncio.Lock()
        self.tlders_cache: dict[str, DiscordUser] = {}
        self.timezones_lock = asyncio.Lock()
        self.timezones_cache: dict[str, Timezone] = {}

    async def list_tlders(self) -> list[DiscordUser]:
        tlders = []
        async with self.tlders_lock:
            async for tlder in self.collection.find({}):
                tlders.append(tlder)
                self.tlders_cache[str(tlder["discord_id"])] = tlder
        return tlders

    async def retrieve_tlder(self, discord_id: str) -> Optional[DiscordUser]:
        log.debug(f"Fetching TLDer with ID {discord_id}")
        tlder = await self.collection.find_one({"discord_id": discord_id})
        if not tlder:
            log.info(f"No TLDer found with ID {discord_id}")
            return None
        async with self.tlders_lock:
            self.tlders_cache[str(discord_id)] = tlder
            return tlder

    async def get_tlder(self, discord_id: str) -> Optional[DiscordUser]:
        await self.tlders_lock.acquire()
        if tlder := self.tlders_cache.get(str(discord_id)):
            self.tlders_lock.release()
            return tlder
        else:
            self.tlders_lock.release()
            return await self.retrieve_tlder(discord_id)

    async def add_tlder(self, name: str, discord_id: str, timezone: str) -> DiscordUser:
        new_user = DiscordUser(discord_id=discord_id, name=name, timezone=timezone)
        result = await self.collection.insert_one(new_user)
        new_user._id = result.inserted_id
        async with self.tlders_lock:
            self.tlders_cache[str(discord_id)] = new_user
        return new_user

    async def update_tlder(
        self,
        tlder: DiscordUser,
        name: Optional[str] = None,
        timezone: Optional[str] = None,
    ) -> DiscordUser:
        update_record = {}
        if name is not None:
            update_record["name"] = name
            tlder["name"] = name
        if timezone is not None:
            update_record["timezone"] = timezone
            tlder["timezone"] = timezone

        if not update_record:
            log.warning(f"update_tlder called for {tlder} with no changes. Skipping.")
            return tlder

        await self.collection.update_one({"_id": tlder["_id"]}, {"$set": update_record})
        async with self.tlders_lock:
            self.tlders_cache[str(tlder["discord_id"])] = tlder
        return tlder
