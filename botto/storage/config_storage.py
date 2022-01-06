import asyncio
import logging
from typing import Optional

from botto.models import ConfigEntry
from botto.storage.storage import Storage

log = logging.getLogger(__name__)


class ConfigStorage(Storage):
    def __init__(self, airtable_base: str, airtable_key: str):
        super().__init__(airtable_base, airtable_key)
        self.airtable_key = airtable_key
        self.config_url = "https://api.airtable.com/v0/{base}/Config".format(
            base=airtable_base
        )
        self.config_lock = asyncio.Lock()
        self.config_cache: dict[str, dict[str, ConfigEntry]] = {}
        self.auth_header = {"Authorization": f"Bearer {self.airtable_key}"}

    async def list_config(self) -> list[ConfigEntry]:
        config_iterator = self._iterate(self.config_url, filter_by_formula=None)
        config_entries = [ConfigEntry.from_airtable(x) async for x in config_iterator]
        async with self.config_lock:
            for config in config_entries:
                server_config = self.config_cache.get(config.server_id, {})
                server_config[config.config_key] = config
                self.config_cache[config.server_id] = server_config
        return config_entries

    async def retrieve_config(self, server_id: str, key: str) -> Optional[ConfigEntry]:
        log.debug(f"Fetching {key} for {server_id}")
        result_iterator = self._iterate(
            self.config_url,
            filter_by_formula=f"AND({{Server ID}}='{server_id}',{{Key}}='{key}')",
        )
        config_iterator = (ConfigEntry.from_airtable(x) async for x in result_iterator)
        try:
            config = await config_iterator.__anext__()
            async with self.config_lock:
                server_config = self.config_cache.get(str(server_id), {})
                server_config[config.config_key] = config
                self.config_cache[config.server_id] = server_config
            return config
        except (StopIteration, StopAsyncIteration):
            log.info(f"No Config found with Server ID {server_id}")
            return None

    async def get_config(self, server_id: str, key: str) -> Optional[ConfigEntry]:
        await self.config_lock.acquire()
        if server_config := self.config_cache.get(str(server_id)):
            if config := server_config[key]:
                self.config_lock.release()
                return config
        else:
            self.config_lock.release()
            return await self.retrieve_config(server_id, key)
