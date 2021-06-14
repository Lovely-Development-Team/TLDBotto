from __future__ import annotations
import asyncio
import logging
import random

from discord import Message

from typing import TYPE_CHECKING

from regexes import SuggestionRegexes

if TYPE_CHECKING:
    from tld_botto import TLDBotto
from food import SpecialAction

log = logging.getLogger("MottoBotto").getChild("reactions")
log.setLevel(logging.DEBUG)


class Reactions:
    def __init__(self, config: dict) -> None:
        self.config = config
        super().__init__()

    async def reject(self, message: Message):
        await message.add_reaction(self.config["reject"])

    async def skynet_prevention(self, message: Message):
        log.info(f"{message.author} attempted to activate Skynet!")
        await self.reject(message)
        await message.add_reaction(self.config["reactions"]["skynet"])
        if self.config["should_reply"]:
            await message.reply("Skynet prevention")

    async def snail(self, message: Message):
        log.info(f"Snail from: {message.author}")
        await message.add_reaction("🐌")

    async def poke(self, message: Message):
        log.info(f"Poke from: {message.author}")
        await message.add_reaction(random.choice(self.config["reactions"]["poke"]))

    async def love(self, message: Message):
        log.info(f"Apology/love from: {message.author}")
        await message.add_reaction(random.choice(self.config["reactions"]["love"]))

    async def hug(self, message: Message):
        log.info(f"Hug from: {message.author}")
        await message.add_reaction(random.choice(self.config["reactions"]["hug"]))

    async def party(self, message: Message, trigger_word: str):
        log.info(f"Party from: {message.author}")
        if trigger_word.isupper():
            log.info("Party harder!")
            tasks = [
                message.add_reaction(reaction)
                for reaction in self.config["reactions"]["party"]
            ]
        else:
            tasks = [
                message.add_reaction(random.choice(self.config["reactions"]["party"]))
                for _ in range(5)
            ]
        await asyncio.wait(tasks)

    async def food(self, regexes: SuggestionRegexes, message: Message, food_item: str):
        try:
            reactions = regexes.food.lookup[food_item]
            for reaction in reactions:
                if reaction == SpecialAction.echo:
                    await message.add_reaction(food_item)
                elif reaction == SpecialAction.party:
                    await self.party(message, food_item)
                else:
                    await message.add_reaction(reaction)
        except KeyError:
            log.error(
                f"Failed to find food item using key {food_item}. "
                f"Message content: '{message.content.encode('unicode_escape')}'",
                exc_info=True,
            )

    async def unrecognised_food(self, message: Message):
        await message.add_reaction("😵")

    async def rule_1(self, message: Message):
        for emoji in self.config["reactions"]["rule_1"]:
            await message.add_reaction(emoji)
        log.info(f"Someone broke rule #1")

    async def favorite_band(self, message: Message):
        for letter in self.config["reactions"]["favorite_band"]:
            await message.add_reaction(letter)
        log.info(f"Someone asked for favorite band")

    async def off_topic(self, message: Message):
        await message.add_reaction(random.choice(self.config["reactions"]["off_topic"]))

    async def unknown_dm(self, message: Message):
        log.info(f"I don't know how to handle {message.content} from {message.author}")
        await message.add_reaction(self.config["reactions"]["unknown"])

    async def shrug(self, message: Message):
        await message.add_reaction("🤷")
