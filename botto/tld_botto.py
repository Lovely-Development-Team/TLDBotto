import logging
import re
from typing import Optional

import subprocess

import discord
from discord import Message, Guild

import reactions
from regexes import SuggestionRegexes, compile_regexes
from message_checks import is_dm

log = logging.getLogger("TLDBotto")
log.setLevel(logging.DEBUG)


CHANNEL_REGEX = re.compile(r"<#(\d+)>")
NUMBERS = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
]
VOTE_EMOJI = ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]


class TLDBotto(discord.Client):
    def __init__(self, config: dict):
        self.config = config

        log.info(
            "Replies are enabled"
            if self.config["should_reply"]
            else "Replies are disabled"
        )

        self.regexes: Optional[SuggestionRegexes] = None

        intents = discord.Intents(messages=True, guilds=True, reactions=True)
        super().__init__(intents=intents)

    async def on_connect(self):
        if not self.regexes and self.user:
            self.regexes = compile_regexes(self.user.id, self.config)

    async def on_ready(self):
        log.info("We have logged in as {0.user}".format(self))
        if not self.regexes:
            self.regexes = compile_regexes(self.user.id, self.config)

        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=self.config["watching_status"],
            )
        )

    async def on_disconnect(self):
        log.warning("Bot disconnected")

    async def add_reaction(
        self, message: Message, reaction_type: str, default: str = None
    ):
        if reaction := self.config["reactions"].get(reaction_type, default):
            await message.add_reaction(reaction)

    async def on_raw_reaction_remove(self, payload):

        if payload.emoji.name not in VOTE_EMOJI:
            return

        channel = await self.fetch_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        log.info(f"Channel: {channel}")
        log.info(f"Message: {message}")
        log.info(f"Reactions: {message.reactions}")

        if channel.name == "voting":
            reacted_users = set()
            for reaction in message.reactions:
                if reaction.emoji not in VOTE_EMOJI:
                    continue
                users = await reaction.users().flatten()
                reacted_users |= set(u for u in users if u != self.user)
            if len(reacted_users) != 9:
                await message.remove_reaction("🏁", self.user)

    async def on_raw_reaction_add(self, payload):
        if payload.emoji.name not in VOTE_EMOJI:
            return

        log.info(f"Reaction received: {payload}")

        channel = await self.fetch_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        log.info(f"Channel: {channel}")
        log.info(f"Message: {message}")
        log.info(f"Reactions: {message.reactions}")

        if channel.name == "voting":
            reacted_users = set()
            for reaction in message.reactions:
                if reaction.emoji not in VOTE_EMOJI:
                    continue
                users = await reaction.users().flatten()
                reacted_users |= set(u for u in users if u != self.user)
            if len(reacted_users) == 9:
                await message.add_reaction("🏁")
            else:
                log.info(f"Waiting for another {9 - len(reacted_users)} people to vote.")

    async def on_message(self, message: Message):

        if is_dm(message):
            await self.process_dm(message)
            return

        channel_name = message.channel.name

        if channel_name == "voting":
            for emoji in VOTE_EMOJI:
                if emoji in message.content:
                    await message.add_reaction(emoji)

        if (
            self.config["channels"]["include"]
            and channel_name not in self.config["channels"]["include"]
        ):
            return
        else:
            if channel_name in self.config["channels"]["exclude"]:
                return

        await self.process_suggestion(message)
        await self.remove_unapproved_messages()

    def clean_trigger_message(self, trigger, message) -> str:
        return trigger.sub("", message).strip().strip("'\"”“")

    def clean_message(self, actual_motto: str, guild: Guild) -> str:

        for channel_id in CHANNEL_REGEX.findall(actual_motto):
            channel = self.get_channel(int(channel_id))
            if not channel:
                continue
            actual_motto = actual_motto.replace(f"<#{channel_id}>", f"#{channel.name}")

        server_emojis = {x.name: str(x) for x in guild.emojis}
        for emoji in server_emojis:
            if server_emojis[emoji] in actual_motto:
                actual_motto = actual_motto.replace(server_emojis[emoji], f":{emoji}:")

        return actual_motto

    async def is_repeat_message(self, message: Message, check_id=True) -> bool:
        matching_mottos = await self.storage.get_matching_mottos(
            self.clean_message(message.content, message.guild), message_id=message.id if check_id else None
        )
        return bool(matching_mottos)

    async def process_suggestion(self, message: Message):

        if self.regexes.off_topic.search(message.content):
            await reactions.off_topic(self, message)
        if self.regexes.apologising.search(
                message.content
        ) and not self.regexes.sorry.search(message.content):
            await reactions.rule_1(self, message)
        if self.regexes.party.search(message.content):
            await reactions.party(self, message)

        if self.regexes.pokes.search(message.content):
            await reactions.poke(self, message)
        if self.regexes.sorry.search(message.content):
            await reactions.love(self, message)
        if self.regexes.love.search(message.content):
            await reactions.love(self, message)
        if self.regexes.hug.search(message.content):
            await reactions.hug(self, message)
        if self.regexes.band.search(message.content):
            await reactions.favorite_band(self, message)
        if message.content.strip().lower() in ("i am 🐌", "i am snail"):
            await reactions.snail(self, message)
        if food := self.regexes.food.food_regex.search(message.content):
            food_char = food.group(1)
            await reactions.food(self, message, food_char)
        elif self.regexes.food.not_food_regex.search(message.content):
            await reactions.unrecognised_food(self, message)
        return

    async def process_dm(self, message: Message):

        if message.author == self.user:
            return

        log.info(
            f"Received direct message (ID: {message.id}) from {message.author}: {message.content}"
        )

        message_content = message.content.lower().strip()

        if message_content in ("!help", "help", "help!", "halp", "halp!", "!halp"):
            trigger = (
                f"@{self.user.display_name}"
                if self.config["trigger_on_mention"]
                else "a trigger word"
            )

            help_message = f"""
Reply to a great motto in the supported channels with {trigger} to tell me about it! You can nominate a section of a message with \"{trigger} <excerpt>\". (Note: you can't nominate yourself.)

You can DM me the following commands:
`!random`: Get a random motto.
`!leaderboard`: Display the top motto authors.
`!link`: Get a link to the leaderboard.
`!emoji <emoji>`: Set your emoji on the leaderboard. A response of {self.config["reactions"]["invalid_emoji"]} means the emoji you requested is not valid.
`!emoji`: Clear your emoji from the leaderboard.
`!nick on`: Use your server-specific nickname on the leaderboard instead of your Discord username. Nickname changes will auto-update the next time you approve a motto.
`!nick off`: Use your Discord username on the leaderboard instead of your server-specific nickname.
`!delete`: Remove all your data from MottoBotto. Confirmation is required.
""".strip()

            help_channel = self.config["support_channel"]
            users = ", ".join(
                f"<@{user.discord_id}>" for user in await self.storage.get_support_users()
            )

            if help_channel or users:
                message_add = "\nIf your question was not answered here, please"
                if help_channel:
                    message_add = f"{message_add} ask for help in #{help_channel}"
                    if users:
                        message_add = f"{message_add}, or"
                if users:
                    message_add = f"{message_add} DM one of the following users: {users}. They are happy to receive your DMs about MottoBotto without prior permission but otherwise usual rules apply"
                help_message = f"{help_message}\n{message_add}."

            await message.author.dm_channel.send(help_message)
            return

        if message_content == "!version":
            git_version = (
                subprocess.check_output(["git", "describe", "--tags"])
                .decode("utf-8")
                .strip()
            )
            response = f"Version: {git_version}"
            if bot_id := self.config["id"]:
                response = f"{response} ({bot_id})"
            await message.author.dm_channel.send(response)
            return

        await reactions.unknown_dm(self, message)
