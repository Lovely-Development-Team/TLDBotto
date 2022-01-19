from typing import Union, Literal

import discord
from discord import Guild
from discord.abc import GuildChannel, PrivateChannel


class ExtendedClient(discord.Client):
    async def get_or_fetch_channel(
        self, channel_id: int
    ) -> Union[GuildChannel, PrivateChannel, discord.Thread]:
        if channel := self.get_channel(channel_id):
            return channel
        else:
            return await self.fetch_channel(channel_id)

    async def get_or_fetch_user(self, user_id: int) -> Union[discord.User]:
        if user := self.get_user(user_id):
            return user
        else:
            return await self.fetch_user(user_id)
