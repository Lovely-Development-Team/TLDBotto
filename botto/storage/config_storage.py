import asyncio
import logging
from typing import Optional, Union, Any

from botto.models import ConfigEntry
from botto.storage.models.server_config import (
    ServerConfig,
    ConfigValues,
    GeneralServerConfig,
)
from botto.storage.mongo_storage import MongoStorage
from pymongo.asynchronous.collection import AsyncCollection

log = logging.getLogger(__name__)

ConfigCache = dict[str, ServerConfig]
NegativeConfigKeyCache = dict[str, set[str]]


class ConfigStorage(MongoStorage):
    def __init__(self, username: str, password: str, host: str):
        super().__init__(username, password, host)
        self.database = self.client.get_database("general")
        self.collection: AsyncCollection[GeneralServerConfig] = (
            self.database.get_collection("config")
        )
        self.config_lock = asyncio.Lock()
        self.config_cache: ConfigCache = {}
        self.config_key_negative_cache_lock = asyncio.Lock()
        self.config_key_negative_cache: NegativeConfigKeyCache = {}

    async def clear_server_cache(self, server_id: str):
        log.debug(f"Clearing cache for server {server_id}")
        async with self.config_lock:
            self.config_cache.pop(server_id, None)

    async def list_config(self) -> list[ServerConfig]:
        config_iterator = self.collection.find({})
        config_entries: list[ServerConfig] = []
        async with self.config_lock:
            async for config in config_iterator:
                self.config_cache[config["server_id"]] = config
                config_entries.append(config)
        return config_entries

    async def list_config_by_server(self) -> ConfigCache:
        await self.list_config()
        async with self.config_lock:
            return self.config_cache

    async def retrieve_config(
        self, server_id: str | int, key: Optional[Union[str, int]]
    ) -> Optional[ServerConfig | ConfigValues]:
        server_config = await self.collection.find_one({"server_id": str(server_id)})
        if not server_config:
            async with self.config_key_negative_cache_lock:
                self.config_key_negative_cache.setdefault(str(server_id), set()).add(
                    key
                )
            return None
        try:
            async with self.config_lock:
                self.config_cache[str(server_id)] = server_config
                return server_config if not key else server_config["config"][key]
        except (StopIteration, StopAsyncIteration, KeyError):
            log.info(f"No config found for Key {key} with Server ID {server_id}")
            async with self.config_key_negative_cache_lock:
                self.config_key_negative_cache.setdefault(str(server_id), set()).add(
                    key
                )
            return None

    async def get_config(self, server_id: str | int, key: str) -> Optional[Any]:
        if (
            not self.config_key_negative_cache_lock.locked()
            and key in self.config_key_negative_cache.get(str(server_id), {})
        ):
            return None
        await self.config_lock.acquire()
        if (server_config := self.config_cache.get(str(server_id))) and (
            config := server_config.get(key)
        ):
            self.config_lock.release()
            return config
        else:
            self.config_lock.release()
            return await self.retrieve_config(server_id, key)

    async def refresh_cache(self):
        log.info("Refreshing config cache")
        await self.config_lock.acquire()
        current_cache = self.config_cache
        self.config_lock.release()
        for key, entries in current_cache.items():
            log.debug(f"Refreshing config for server {key}")
            for entry in entries.values():
                await self.retrieve_config(server_id=key, key=entry.config_key)

        log.info("Refreshing negative config key cache")
        for server_id, keys in self.config_key_negative_cache.items():
            keys_to_remove = []
            for key in keys:
                async with self.config_key_negative_cache_lock:
                    if await self.retrieve_config(server_id, key):
                        keys_to_remove.append(key)
                        log.debug(
                            f"Previously non-existent key {key} now exists for {server_id}"
                        )
            for key in keys_to_remove:
                self.config_key_negative_cache[server_id].remove(key)
        log.info("Config cache refreshed")
