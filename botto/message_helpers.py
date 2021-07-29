import asyncio
import logging
from typing import Union, Optional

import discord
from discord import Message

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


async def remove_user_reactions(message: Message, user: Union[discord.abc.User, discord.ClientUser]):
    my_reactions = [r for r in message.reactions if r.me is True]
    clearing_reactions = [message.remove_reaction(r.emoji, user) for r in my_reactions]
    await asyncio.wait(clearing_reactions)


async def remove_own_message(requester_name: str, message: Message, delay: Optional[int]):
    log.info(
        "{requester_name} triggered deletion of our message (id: {message_id} in {channel_name}): {content}".format(
            requester_name=requester_name,
            message_id=message.id,
            channel_name=message.channel.name,
            content=message.content,
        )
    )
    if delay:
        await message.delete(delay=delay)
    else:
        await message.delete()
