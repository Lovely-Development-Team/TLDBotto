from typing import Union, Optional, Any

import discord
from discord import app_commands
from discord.abc import GuildChannel, PrivateChannel


class ExtendedClient(discord.Client):
    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.tree = app_commands.CommandTree(self)

    async def get_or_fetch_channel(
        self, channel_id: int | str
    ) -> Optional[Union[GuildChannel, PrivateChannel, discord.Thread]]:
        if channel := self.get_channel(int(channel_id)):
            return channel
        else:
            return await self.fetch_channel(int(channel_id))

    async def get_or_fetch_user(self, user_id: int) -> Union[discord.User]:
        if user := self.get_user(user_id):
            return user
        else:
            return await self.fetch_user(user_id)
