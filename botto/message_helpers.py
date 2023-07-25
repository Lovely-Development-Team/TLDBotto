import asyncio
import logging
from decimal import Decimal
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
    """
    Removes all reactions by the user from the message.
    :param message: The message from which to remove reactions
    :param user: The user for which reactions should be removed
    """
    log.info(f"Removing reactions by {user} from {message}")
    my_reactions = [
        r for r in message.reactions if any([u.id == user.id async for u in r.users()])
    ]
    clearing_reactions = [
        asyncio.create_task(message.remove_reaction(r.emoji, user))
        for r in my_reactions
    ]
    try:
        await asyncio.wait(clearing_reactions)
    except ValueError:
        log.info(f"No reactions to remove by {user} on {message}")


async def remove_own_message(
    requester_name: str, message: Message, delay: Optional[int] = None
):
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


async def resolve_message_reference(
    bot: "TLDBotto", message: Message, force_fresh: bool = False
) -> Message:
    if not message.reference:
        raise MessageMissingReferenceError(message)

    if not force_fresh:
        if referenced_message := message.reference.resolved:
            return referenced_message

    log.debug("Fetching referenced message")
    reference_channel = await bot.get_or_fetch_channel(message.reference.channel_id)

    referenced_message = await reference_channel.fetch_message(
        message.reference.message_id
    )
    return referenced_message


def convert_amount(text: str) -> Decimal:
    """
    Converts a string containing an amount into an int.

    This does not actually do currency conversions right now because that sounds like a lot of work.

    :param text: The textual amount to convert to an integer
    :return: An int representing the amount, with sterling currency symbol stripped

    :raise BadAmountError: The amount is not parsable to an integer
    :raise BadCurrencyError: Text starts with an unrecognised symbol
    """
    if not text:
        raise BadAmountError(text)
    stripped_text = text.strip()
    if (
        not stripped_text[0].isdigit()
        and stripped_text[1:].isdigit()
        and not stripped_text.startswith("£")
    ):
        raise BadCurrencyError(text)
    number_text = text.strip().replace("£", "")
    try:
        amount = Decimal(number_text)
        return amount
    except ValueError:
        raise BadAmountError(text)


class MessageMissingReferenceError(Exception):
    def __init__(self, message: Message, *args: object) -> None:
        self.message = message
        super().__init__(*args)


class BadAmountError(Exception):
    def __init__(self, text: str, *args: object) -> None:
        self.text = text
        super().__init__(*args)


class BadCurrencyError(BadAmountError):
    def __init__(self, text: str, *args: object) -> None:
        self.symbol = text[0] if text else ""
        super().__init__(text, *args)


def hex_to_rgb(hex: str):
    hex = hex.lstrip("#")
    return tuple(int(hex[i : i + 2], 16) for i in (0, 2, 4))


def truncate_string(text: str, limit: int) -> str:
    return (text[: limit - 1] + "…") if len(text) > limit else text
