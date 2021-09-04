from __future__ import annotations
import asyncio
import logging
import random
from enum import Enum, auto

from discord import Message

from typing import TYPE_CHECKING, Callable

from .regexes import SuggestionRegexes

if TYPE_CHECKING:
    from tld_botto import TLDBotto
from .food import SpecialAction

log = logging.getLogger("MottoBotto").getChild("reactions")
log.setLevel(logging.DEBUG)


class ReactionType(Enum):
    RANDOM = auto()
    ALL = auto()
    ORDERED = auto()

    async def add_reaction(self, message: Message, reactions: list[str]):
        await reaction_type_to_func[self](message, reactions)


async def _random_reaction(message: Message, reactions: list[str]):
    await message.add_reaction(random.choice(reactions))


async def _all_reactions(message: Message, reactions: list[str]):
    await asyncio.wait([message.add_reaction(reaction) for reaction in reactions])


async def _ordered_reactions(message: Message, reactions: list[str]):
    for reaction in reactions:
        await message.add_reaction(reaction)


reaction_type_to_func: dict[ReactionType, Callable[[Message, list[str]], any]] = {
    ReactionType.RANDOM: _random_reaction,
    ReactionType.ALL: _all_reactions,
    ReactionType.ORDERED: _ordered_reactions,
}


class Reactions:
    def __init__(self, config: dict) -> None:
        self.config = config
        super().__init__()

    async def reject(self, message: Message):
        await message.add_reaction(self.config["reactions"]["reject"])

    async def nice_try(self, message: Message):
        await message.add_reaction(self.config["reactions"]["invalid"])
        await message.add_reaction(self.config["reactions"]["nice_try"])

    async def skynet_prevention(self, message: Message):
        log.info(f"{message.author} attempted to activate Skynet!")
        await self.reject(message)
        await message.add_reaction(self.config["reactions"]["skynet"])
        if self.config["should_reply"]:
            await message.reply("Skynet prevention")

    async def poke(self, message: Message):
        log.info(f"Poke from: {message.author}")
        await message.add_reaction(random.choice(self.config["reactions"]["poke"]))

    async def wave(self, message: Message):
        log.info(f"Wave to: {message.author}")
        await message.add_reaction(random.choice(self.config["reactions"]["wave"]))

    async def love(self, message: Message):
        log.info(f"Apology/love from: {message.author}")
        await message.add_reaction(random.choice(self.config["reactions"]["love"]))

    async def hug(self, message: Message):
        log.info(f"Hug from: {message.author}")
        await message.add_reaction(random.choice(self.config["reactions"]["hug"]))

    async def party(self, message: Message, trigger_word: str):
        log.info(f"Party from: {message.author}")
        if trigger_word.isupper() or "!!" in trigger_word:
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
        if "?" in trigger_word:
            log.info("is there a party?")
            await message.add_reaction("❓")

    async def food(self, regexes: SuggestionRegexes, message: Message, food_item: str):
        try:
            reactions = regexes.food.lookup[food_item]
            for reaction in reactions:
                if reaction == SpecialAction.echo:
                    await message.add_reaction(food_item)
                elif reaction == SpecialAction.party:
                    await self.party(message, food_item)
                elif reaction == SpecialAction.love:
                    await self.love(message)
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

    async def unknown_dm(self, message: Message):
        log.info(f"I don't know how to handle {message.content} from {message.author}")
        await message.add_reaction(self.config["reactions"]["unknown"])

    async def pattern(self, name: str, message: Message):
        try:
            pattern_item = self.config.get("pattern_reactions", {})[name]
        except KeyError:
            log.warning(f"Failed to find configured pattern '{name}'")
            return
        try:
            reactions = pattern_item["reactions"]
            try:
                reaction_type = ReactionType[
                    pattern_item.get("reaction_type", "RANDOM")
                ]
                if name == "fisrt" and random.randint(1, 100) < 10:
                    await message.add_reaction("🖕")
                else:
                    await reaction_type.add_reaction(message, reactions)
            except KeyError:
                log.warning(f"Unknown reaction type '{pattern_item['reaction_type']}'")
                return
        except KeyError:
            log.warning(f"Failed to find configured pattern '{name}'")
            return

    async def enabled(self, message: Message):
        await message.add_reaction(self.config["reactions"]["enabled"])

    async def dizzy(self, message: Message):
        log.info(f"Dizzy to: {message.author}")
        await message.add_reaction(self.config["reactions"]["dizzy"])

    async def drama_llama(self, message: Message):
        log.info(f"Drama llama detected: {message.author}!")
        await message.add_reaction("🦙")
