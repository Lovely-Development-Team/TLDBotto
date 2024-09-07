from functools import partial
from typing import Optional

from asyncache import cachedmethod
from cachetools import TTLCache
from cachetools.keys import hashkey

from botto.storage.config_storage import ConfigStorage


class TestFlightConfigStorage(ConfigStorage):
    def __init__(self, airtable_base: str, airtable_key: str):
        self.cache = TTLCache(20, 600)
        super().__init__(airtable_base, airtable_key)

    @cachedmethod(
        lambda self: self.cache,
        key=partial(hashkey, "approvals_channels"),
    )
    async def get_default_approvals_channel_id(
        self, guild_id: str | int
    ) -> Optional[str]:
        if result := await self.get_config(guild_id, "default_approvals_channel"):
            return result.value
        return None

    @cachedmethod(
        lambda self: self.cache,
        key=partial(hashkey, "rule_agreement_role"),
    )
    async def get_rule_agreement_role_id(self, guild_id: str) -> Optional[str]:
        if result := await self.get_config(guild_id, "rule_agreement_role"):
            return result.value
        return None

    @cachedmethod(
        lambda self: self.cache,
        key=partial(hashkey, "tester_exit_notification_channel"),
    )
    async def get_tester_exit_notification_channel(
        self, guild_id: str
    ) -> Optional[str]:
        if result := await self.get_config(
            guild_id, "tester_exit_notification_channel"
        ):
            return result.value
        return None
