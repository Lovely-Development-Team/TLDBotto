from __future__ import annotations
import asyncio
import logging
import random

from discord import Message

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tld_botto import TLDBotto
from food import SpecialAction

log = logging.getLogger("MottoBotto").getChild("reactions")
log.setLevel(logging.DEBUG)


async def reject(reactions_config: dict, message: Message):
    await message.add_reaction(reactions_config["reject"])


async def skynet_prevention(botto: TLDBotto, message: Message):
    log.info(f"{message.author} attempted to activate Skynet!")
    await reject(botto.config["reactions"], message)
    await message.add_reaction(botto.config["reactions"]["skynet"])
    if botto.config["should_reply"]:
        await message.reply("Skynet prevention")


async def snail(botto: TLDBotto, message: Message):
    log.info(f"Snail from: {message.author}")
    await message.add_reaction("🐌")


async def poke(botto: TLDBotto, message: Message):
    log.info(f"Poke from: {message.author}")
    await message.add_reaction(random.choice(botto.config["reactions"]["poke"]))


async def love(botto: TLDBotto, message: Message):
    log.info(f"Apology/love from: {message.author}")
    await message.add_reaction(random.choice(botto.config["reactions"]["love"]))


async def hug(botto: TLDBotto, message: Message):
    log.info(f"Hug from: {message.author}")
    await message.add_reaction(random.choice(botto.config["reactions"]["hug"]))


async def party(botto: TLDBotto, message: Message, trigger_word: str):
    log.info(f"Party from: {message.author}")
    if trigger_word.isupper():
        log.info("Party harder!")
        tasks = [message.add_reaction(reaction) for reaction in botto.config["reactions"]["party"]]
    else:
        tasks = [message.add_reaction(random.choice(botto.config["reactions"]["party"])) for _ in range(5)]
    await asyncio.wait(tasks)


async def food(botto: TLDBotto, message: Message, food_item: str):
    try:
        reactions = botto.regexes.food.lookup[food_item]
        for reaction in reactions:
            if reaction == SpecialAction.echo:
                await message.add_reaction(food_item)
            elif reaction == SpecialAction.party:
                await party(botto, message)
            else:
                await message.add_reaction(reaction)
    except KeyError:
        log.error(
            f"Failed to find food item using key {food_item}. "
            f"Message content: '{message.content.encode('unicode_escape')}'",
            exc_info=True,
        )


async def unrecognised_food(botto: TLDBotto, message: Message):
    await message.add_reaction("😵")


async def not_reply(botto: TLDBotto, message: Message):
    log.info(
        f"Suggestion from {message.author} was not a reply (Message ID {message.id})"
    )
    await message.add_reaction(botto.config["reactions"]["unknown"])
    if botto.config["should_reply"]:
        await message.reply("I see no motto!")


async def fishing(botto: TLDBotto, message: Message):
    log.info(f"Motto fishing from: {message.author}")
    await reject(botto.config["reactions"], message)
    await message.add_reaction(botto.config["reactions"]["fishing"])


async def invalid(botto: TLDBotto, message: Message):
    log.info(f"Motto from {message.author} is invalid according to rules.")
    await reject(botto.config["reactions"], message)
    await message.add_reaction(botto.config["reactions"]["invalid"])


async def duplicate(botto: TLDBotto, message: Message):
    log.debug("Ignoring motto, it's a duplicate.")
    await message.add_reaction(botto.config["reactions"]["repeat"])
    await message.remove_reaction(botto.config["reactions"]["pending"], botto.user)


async def deleted(botto: TLDBotto, message: Message):
    log.debug("Ignoring motto, it's been deleted.")
    await message.add_reaction(botto.config["reactions"]["deleted"])
    await reject(botto.config["reactions"], message)
    await message.remove_reaction(botto.config["reactions"]["pending"], botto.user)


async def stored(botto: TLDBotto, message: Message, motto_message: Message):
    await message.remove_reaction(botto.config["reactions"]["pending"], botto.user)
    await message.add_reaction(botto.config["reactions"]["success"])
    if special_reactions := botto.config["special_reactions"].get(
        str(motto_message.author.id)
    ):
        await message.add_reaction(random.choice(special_reactions))
    log.debug("Reaction added")
    if botto.config["should_reply"]:
        await message.reply(f'"{motto_message.content}" will be considered!')
    log.debug("Reply sent")


async def pending(botto: TLDBotto, message: Message, motto_message: Message):
    await message.add_reaction(botto.config["reactions"]["pending"])
    log.debug("Reaction added")


async def invalid_emoji(botto: TLDBotto, message: Message):
    log.info(f"Invalid emoji requested from {message.author}")
    await message.add_reaction(botto.config["reactions"]["invalid_emoji"])


async def valid_emoji(botto: TLDBotto, message: Message):
    log.info(f"Valid emoji requested from {message.author}")
    await message.add_reaction(botto.config["reactions"]["valid_emoji"])


async def rule_1(botto: TLDBotto, message: Message):
    for emoji in botto.config["reactions"]["rule_1"]:
        await message.add_reaction(emoji)
    log.info(f"Someone broke rule #1")


async def favorite_band(botto: TLDBotto, message: Message):
    for letter in botto.config["reactions"]["favorite_band"]:
        await message.add_reaction(letter)
    log.info(f"Someone asked for favorite band")


async def off_topic(botto: TLDBotto, message: Message):
    await message.add_reaction(random.choice(botto.config["reactions"]["off_topic"]))


async def unknown_dm(botto: TLDBotto, message: Message):
    log.info(f"I don't know how to handle {message.content} from {message.author}")
    await message.add_reaction(botto.config["reactions"]["unknown"])
