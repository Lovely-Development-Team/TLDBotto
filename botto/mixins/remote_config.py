import asyncio
import json
from datetime import datetime, timedelta
from typing import Literal, Optional, Union

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from botto.storage import ConfigStorage


class RemoteConfig:
    def __init__(
        self,
        config: dict,
        config_storage: ConfigStorage,
        scheduler: AsyncIOScheduler,
        **kwargs,
    ):
        self.config = config
        self.config_storage = config_storage
        scheduler.add_job(
            self.config_storage.refresh_cache,
            name="Refresh config cache",
            trigger="cron",
            minute="*/40",
            coalesce=True,
            next_run_time=datetime.now() + timedelta(seconds=5),
        )
        super().__init__(scheduler=scheduler, **kwargs)

    async def is_feature_disabled(
        self,
        feature_name: Literal[
            "remaining_voters", "vote_emoji_reminder", "apology_reaction"
        ],
        server_id: Optional[Union[str, int]] = None,
    ) -> bool:
        if feature_name in self.config["disabled_features"]:
            return True
        if server_id := server_id:
            disabled_features_for_server = await self.config_storage.get_config(
                str(server_id), "disabled_features"
            )
            return feature_name in disabled_features_for_server.parsed_value

    async def should_respond_dms(self, member: discord.User) -> bool:
        config_entries = await asyncio.gather(
            *[
                self.config_storage.get_config(guild.id, "respond_member_dms")
                for guild in member.mutual_guilds
            ]
        )
        return any(
            guild_config.parsed_value for guild_config in config_entries if guild_config
        )
