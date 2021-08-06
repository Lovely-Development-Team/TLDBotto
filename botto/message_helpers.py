import asyncio
import logging
from typing import Union, Optional, TYPE_CHECKING

import discord
from discord import Message

if TYPE_CHECKING:
    from tld_botto import TLDBotto

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


async def remove_user_reactions(
        message: Message, user: Union[discord.abc.User, discord.ClientUser]
):
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


async def resolve_message_reference(bot: "TLDBotto", message: Message, force_fresh: bool = False) -> Message:
    if not message.reference:
        raise MessageMissingReferenceError(message)

    if referenced_message := message.reference.resolved and not force_fresh:
        return referenced_message

    reference_channel = await bot.get_or_fetch_channel(
        message.reference.channel_id
    )

    referenced_message = await reference_channel.fetch_message(
        message.reference.message_id
    )
    return referenced_message


class MessageMissingReferenceError(Exception):
    def __init__(self, message: Message, *args: object) -> None:
        self.message = message
        super().__init__(*args)
