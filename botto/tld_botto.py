from __future__ import annotations

import asyncio
import logging
import os
import random
import re
from datetime import datetime, timedelta
from typing import Optional, Callable

import subprocess

import discord
import pytz
from discord import Message, Guild
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import responses
from date_helpers import is_naive
from models import Meal
from reactions import Reactions
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reminder_manager import ReminderManager
from storage import MealStorage, TimezoneStorage
from regexes import SuggestionRegexes, compile_regexes
from message_checks import is_dm

log = logging.getLogger(__name__)
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
VOTE_EMOJI = [
    "0️⃣",
    "1️⃣",
    "2️⃣",
    "3️⃣",
    "4️⃣",
    "5️⃣",
    "6️⃣",
    "7️⃣",
    "8️⃣",
    "9️⃣",
    "✅",
    "👍",
    "👎",
]


class TLDBotto(discord.Client):
    def __init__(
        self,
        config: dict,
        reactions: Reactions,
        scheduler: AsyncIOScheduler,
        storage: MealStorage,
        timezones: TimezoneStorage,
        reminders: ReminderManager,
    ):
        self.config = config
        self.reactions = reactions
        self.scheduler = scheduler
        self.storage = storage
        self.timezones = timezones
        self.reminders = reminders
        log.info(
            "Replies are enabled"
            if self.config["should_reply"]
            else "Replies are disabled"
        )

        reminder_hours = ",".join(config["meals"]["auto_reminder_hours"])
        scheduler.add_job(
            self.send_meal_reminder,
            name="Meal Reminder",
            trigger="cron",
            hour=reminder_hours,
            coalesce=True,
        )
        scheduler.add_job(
            self.random_presence,
            name="Randomise presence",
            trigger="cron",
            hour="*/12",
            coalesce=True,
        )
        initial_refresh_run = datetime.now() + timedelta(seconds=5)
        scheduler.add_job(
            self.storage.update_meals_cache,
            name="Refresh meals cache",
            trigger="cron",
            minute="*/30",
            coalesce=True,
            next_run_time=initial_refresh_run,
        )
        scheduler.add_job(
            self.storage.update_text_cache,
            name="Refresh text cache",
            trigger="cron",
            hour="*/3",
            coalesce=True,
        )

        scheduler.add_job(
            self.timezones.update_tlder_timezone_cache,
            name="Refresh TLDer timezone cache",
            trigger="cron",
            hour="*/6",
            coalesce=True,
        )

        self.regexes: Optional[SuggestionRegexes] = None

        intents = discord.Intents(messages=True, guilds=True, reactions=True)
        super().__init__(intents=intents)

    async def on_connect(self):
        if not self.regexes and self.user:
            self.regexes = compile_regexes(self.user.id, self.config)

    async def random_presence(self):
        chosen_status = random.choice(self.config["watching_statūs"])
        log.info(f"Chosen status: {chosen_status}")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=chosen_status,
            )
        )

    async def on_ready(self):
        log.info("We have logged in as {0.user}".format(self))

        if not self.regexes:
            self.regexes = compile_regexes(self.user.id, self.config)

        await self.random_presence()

        self.reminders.start(self.get_or_fetch_channel)

        reminder_log_text = ", ".join(
            [
                f"{channel.guild.name} in #{channel.name}"
                async for channel in self.get_meal_channels()
            ]
        )
        log.info(f"Meal reminders for: {reminder_log_text}")

    async def on_disconnect(self):
        log.warning("Bot disconnected")

    async def get_or_fetch_channel(self, channel_id: int) -> discord.TextChannel:
        if channel := self.get_channel(channel_id):
            return channel
        else:
            return await self.fetch_channel(channel_id)

    async def get_meal_channels(self):
        for guild in self.config["meals"]["guilds"]:
            yield await self.get_or_fetch_channel(guild["channel"])

    async def add_reaction(
        self, message: Message, reaction_type: str, default: str = None
    ):
        if reaction := self.config["reactions"].get(reaction_type, default):
            await message.add_reaction(reaction)

    def is_voting_channel(self, channel: discord.abc.Messageable) -> bool:
        if isinstance(channel, discord.TextChannel):
            return channel.name in self.config["channels"]["voting"]
        else:
            return False

    async def on_raw_reaction_remove(self, payload):

        if payload.emoji.name not in VOTE_EMOJI:
            return

        channel = await self.fetch_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        log.info(f"Channel: {channel}")
        log.info(f"Message: {message}")
        log.info(f"Reactions: {message.reactions}")

        if self.is_voting_channel(channel):
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

        if self.is_voting_channel(channel):
            reacted_users = set()
            for reaction in message.reactions:
                if reaction.emoji not in VOTE_EMOJI:
                    continue
                users = await reaction.users().flatten()
                reacted_users |= set(u for u in users if u != self.user)
            if len(reacted_users) == 9:
                await message.add_reaction("🏁")
            else:
                log.info(
                    f"Waiting for another {9 - len(reacted_users)} people to vote."
                )

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

        if message.author.id == self.user.id:
            log.info("Ignoring message from self")
            return

        await self.process_suggestion(message)

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

    def check_triggers(self, message: Message) -> tuple[Callable, re.Match]:
        def search_triggers(content: str, trigger_dict: dict):
            for name, triggers in trigger_dict.items():
                for trigger in triggers:
                    if matched := trigger.match(content):
                        return name, matched

        at_command = None
        for t in self.regexes.at_command:
            if match := t.match(message.content):
                if command_group := match.group("command"):
                    at_command = command_group.strip()
        if at_command:
            trigger_details = search_triggers(at_command, self.regexes.at_triggers)
        else:
            trigger_details = search_triggers(message.content, self.regexes.triggers)

        if trigger_details:
            resolved_name = trigger_details[0]
            resolved_matched = trigger_details[1]
            if trigger_func := self.trigger_funcs.get(resolved_name):
                return trigger_func, resolved_matched

    @property
    def trigger_funcs(self):
        return {
            "meal_time": self.send_meal_reminder,
            "timezones": self.send_local_times,
            "job_schedule": self.send_schedule,
            "yell": self.yell_at_someone,
            "add_reminder": self.reminders.add_reminder_message,
            "reminder_explain": self.reminders.send_reminder_syntax,
            "remove_reactions": self.remove_reactions,
        }

    @staticmethod
    async def handle_trigger(
        message: Message, trigger_details: tuple[Callable, re.Match]
    ):
        if trigger_func := trigger_details[0]:
            if groups := trigger_details[1].groupdict():
                await trigger_func(message, **groups)
            else:
                await trigger_func(message)
            return

    @property
    def simple_reactions(self) -> list[tuple[Callable, Callable]]:
        return [
            (
                lambda content: self.regexes.apologising.search(content)
                and not self.regexes.sorry.search(content),
                self.reactions.rule_1,
            ),
            (lambda content: self.regexes.sorry.search(content), self.reactions.love),
            (lambda content: self.regexes.love.search(content), self.reactions.love),
            (lambda content: self.regexes.hug.search(content), self.reactions.hug),
        ]

    async def react(self, message):
        has_matched = False
        for reaction in self.simple_reactions:
            if reaction[0](message.content):
                await reaction[1](message)
                has_matched = True
        if party_match := self.regexes.party.search(message.content):
            matched_string = party_match.group("partyword")
            await self.reactions.party(message, matched_string)
            has_matched = True
        if food := self.regexes.food.food_regex.search(message.content):
            food_char = food.group(1)
            await self.reactions.food(self.regexes, message, food_char)
            has_matched = True
        elif self.regexes.food.not_food_regex.search(message.content):
            await self.reactions.unrecognised_food(message)
            has_matched = True
        if pattern_name := self.regexes.patterns.matches(message.content):
            log.info(f"{pattern_name.capitalize()} from {message.author}")
            await self.reactions.pattern(pattern_name, message)
            has_matched = True
        return has_matched

    async def match_times(self, message: Message):
        def is_time(maybe_time: re.Match):
            if maybe_time.group("hours"):
                if maybe_time.group("minutes"):
                    return True
                elif am_pm := maybe_time.group("am_pm"):
                    if am_pm.upper() in ("AM", "PM"):
                        return True
            return False

        time_matches = [
            match.group(0)
            for match in self.regexes.convert_time.finditer(message.content)
            if is_time(match)
        ]

        num_matches = len(time_matches)
        if num_matches > 0:
            log.info(f"Message contained {num_matches} times")
            try:
                response_string = await self.process_time_matches(
                    message.author, time_matches
                )
                print(response_string)
                await message.reply(
                    response_string,
                    allowed_mentions=discord.AllowedMentions(replied_user=False),
                )
            except ValueError:
                log.error(f"Failed to process times: {time_matches}", exc_info=True)

    async def process_time_matches(
        self, author: discord.User, matches: list[str]
    ) -> str:
        import dateutil.parser

        parsed_times = (
            (time_string, dateutil.parser.parse(time_string)) for time_string in matches
        )
        tlder = await self.timezones.get_tlder(author.id)
        timezone = await self.timezones.get_timezone(tlder.timezone_id)
        parsed_local_times = []
        for time in parsed_times:
            now = datetime.now() if is_naive(time[1]) else datetime.utcnow()
            converted_time = time[1]
            if (now - converted_time) > timedelta(
                hours=self.config["time_is_next_day_threshold_hours"]
            ):
                new_day = now + timedelta(days=1)
                converted_time = converted_time.replace(day=new_day.day)
            if is_naive(converted_time):
                parsed_local_times.append(
                    (time[0], converted_time.astimezone(pytz.timezone(timezone)))
                )
            else:
                parsed_local_times.append((time[0], converted_time))
        conversion_string_intro = [
            f"{time[0]} is <t:{round(time[1].timestamp())}> (<t:{round(time[1].timestamp())}:R>)"
            for time in parsed_local_times
        ]
        return "\n".join(conversion_string_intro)

    async def process_suggestion(self, message: Message):
        if trigger_result := self.check_triggers(message):
            await self.handle_trigger(message, trigger_result)

        await self.match_times(message)

        await self.react(message)
        return

    async def process_dm(self, message: Message):
        await self.match_times(message)

        if message.author == self.user:
            return

        log.info(
            f"Received direct message (ID: {message.id}) from {message.author}: {message.content}"
        )

        if trigger_result := self.check_triggers(message):
            await self.handle_trigger(message, trigger_result)
            return

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
`!schedule`: Show the current schedule of reminders
`!bottoyellat<name>. <message>`: Get Tildy to yell at someone.
{self.reminders.reminder_syntax}: Get Tidly to remind you. Include '🕰' in `message` to also receive a reminder 15 minutes prior.
`!emoji <emoji>`: Set your emoji on the leaderboard. A response of {self.config["reactions"]["invalid_emoji"]} means the emoji you requested is not valid.
`!emoji`: Clear your emoji from the leaderboard.
`!nick on`: Use your server-specific nickname on the leaderboard instead of your Discord username. Nickname changes will auto-update the next time you approve a motto.
`!nick off`: Use your Discord username on the leaderboard instead of your server-specific nickname.
""".strip()

            help_channel = self.config["support_channel"]
            # users = ", ".join(
            #     f"<@{user.discord_id}>"
            #     for user in await self.storage.get_support_users()
            # )
            users = ""

            if help_channel or users:
                message_add = "\nIf your question was not answered here, please"
                if help_channel:
                    message_add = f"{message_add} ask for help in #{help_channel}"
                    if users:
                        message_add = f"{message_add}, or"
                if users:
                    message_add = (
                        f"{message_add} DM one of the following users: {users}. They are happy to receive "
                        f"your DMs about MottoBotto without prior permission but otherwise usual rules apply"
                    )
                help_message = f"{help_message}\n{message_add}."

            await message.author.dm_channel.send(help_message)
            return

        if message_content == "!version":
            await message.channel.trigger_typing()
            git_version = os.getenv("TLDBOTTO_VERSION")
            try:
                git_version = (
                    subprocess.check_output(["git", "describe", "--tags"])
                    .decode("utf-8")
                    .strip()
                )
            except subprocess.CalledProcessError as error:
                log.warning(
                    "Git command failed with code: {code}".format(code=error.returncode)
                )
            except FileNotFoundError:
                log.warning("Git command not found")
            response = f"Version: {git_version}"
            if bot_id := self.config["id"]:
                response = f"{response} ({bot_id})"
            await message.author.dm_channel.send(response)
            return

        if not await self.react(message):
            await self.reactions.unknown_dm(message)

    @property
    def local_times(self) -> list[datetime]:
        time_now = datetime.utcnow()
        return [zone.fromutc(time_now) for zone in self.config["timezones"]]

    async def get_meal_reminder_text(self):
        configured_meals = await self.storage.get_meals()
        localised_times = self.local_times
        return await self.calculate_meal_reminders(localised_times, configured_meals)

    async def calculate_meal_reminders(
        self, timezones: list[datetime], configured_meals: list[Meal]
    ):
        intro_fetch = self.storage.get_intros()
        meals = {}
        for local_timezone in timezones:
            for meal in configured_meals:
                start_time = datetime.combine(
                    local_timezone, meal.start, local_timezone.tzinfo
                )
                end_time = datetime.combine(
                    local_timezone, meal.end, local_timezone.tzinfo
                )
                adjusted_local_timezone = local_timezone
                # We're comparing datetimes but really only care about the time.
                # If the start and end of the meal crosses midnight, we can end up with impossible comparisons where
                # time periods end before they start.
                # Ween this happens, presume that the start date was meant to be the previous day.
                if start_time > end_time:
                    start_time = start_time - timedelta(days=1)

                if start_time < adjusted_local_timezone < end_time:
                    log.debug(
                        "Adding meal {meal_name} for {tzname}: {start} < {local_time} < {end}".format(
                            meal_name=meal.name,
                            tzname=adjusted_local_timezone.tzname(),
                            start=start_time,
                            local_time=adjusted_local_timezone,
                            end=end_time,
                        )
                    )
                    meal_text_ref = random.choice(meal.texts)
                    meal_text = await self.storage.get_text(meal_text_ref)
                    zones_for_meal = meals.get(meal.name, ([], meal.emoji, meal_text))
                    zones_for_meal[0].append(local_timezone.tzname())
                    meals.update({meal.name: zones_for_meal})

        intro_ref = random.choice((await intro_fetch).texts)
        intro_text = await self.storage.get_text(intro_ref)
        reminder_list = [
            " & ".join(meal_details[0])
            + f" ({meal_details[1]})"
            + f", {meal_details[2]}"
            for meal_details in meals.values()
        ]
        reminder_text = "\n".join(reminder_list)
        return f"{intro_text}\n{reminder_text}"

    async def send_meal_reminder(self, reply_to: Optional[Message] = None):
        log.info("Sending meal reminder")
        if reply_to:
            log.info(f"Mealtimes from: {reply_to.author}")
            async with reply_to.channel.typing():
                await reply_to.reply(await self.get_meal_reminder_text())
        else:
            async for channel in self.get_meal_channels():
                async with channel.typing():
                    await channel.send(await self.get_meal_reminder_text())

    async def send_local_times(self, reply_to: Message):
        log.info(f"Times from: {reply_to.author}")
        async with reply_to.channel.typing():
            local_times_string = responses.get_local_times(local_times=self.local_times)
            await reply_to.reply(local_times_string)

    async def send_schedule(self, reply_to: Message):
        log.info(f"Schedule from: {reply_to.author}")
        async with reply_to.channel.typing():
            await self.reminders.refresh_reminders()
            current_time = f"\nBotto time is {datetime.now().strftime('%H:%M:%S %Z')}"
            regular_jobs = (
                job
                for job in self.scheduler.get_jobs()
                if not job.name.startswith("Reminder: ")
            )
            reminder_jobs = (
                job
                for job in self.scheduler.get_jobs()
                if job.name.startswith("Reminder:")
            )
            job_descs = [
                f"- `{job.name}` next running at {job.next_run_time.strftime('%a %H:%M:%S %Z')}"
                for job in regular_jobs
            ]
            reminder_job_descs = [
                f"- `{job.name.lstrip('Reminder:')}` running at {job.next_run_time.strftime('%a %H:%M:%S %Z')}."
                f" Ref `{job.id}`"
                for job in reminder_jobs
            ]
            regular_jobs_text = "Regular jobs:\n" + "\n".join(job_descs)
            reminder_jobs_text = "\nReminder jobs:\n" + "\n".join(reminder_job_descs)
            response_text = (
                regular_jobs_text + reminder_jobs_text
                if len(reminder_job_descs) > 0
                else regular_jobs_text
            )
            await reply_to.reply(response_text + current_time)

    @staticmethod
    async def yell_at_someone(message: Message, **kwargs):
        """
        Args:
            message: The message requesting yelling

        Keyword args:
            person (str): The person to yell at
        """
        log.info(f"Yelling from: {message.author}")
        channel: discord.TextChannel = message.channel
        async with channel.typing():
            response_text = responses.yell_at_someone(
                kwargs.get("person"), kwargs.get("text")
            )
            await channel.send(response_text)

    async def remove_own_reactions(self, message: Message):
        my_reactions = [r for r in message.reactions if r.me is True]
        clearing_reactions = [
            message.remove_reaction(r.emoji, self.user) for r in my_reactions
        ]
        await asyncio.wait(clearing_reactions)

    async def remove_own_message(self, message: Message):
        await message.delete()

    async def remove_reactions(self, message: Message):
        if not message.reference:
            await self.reactions.unknown_dm(message)
            return

        reference_channel = await self.get_or_fetch_channel(
            message.reference.channel_id
        )
        referenced_message = await reference_channel.fetch_message(
            message.reference.message_id
        )
        if referenced_message.author.id == message.author.id:
            log.info(
                f"{message.author.id} attempted to removed reactions from their own message!"
            )
            await self.reactions.nice_try(message)
            return

        # This is a valid request, so indicate it was recognised
        await message.add_reaction("👍")
        if referenced_message.author.id == self.user.id:
            # Message was us, so we'll remove
            log.info(
                "{requester_id} triggered deletion of our message (id: {message_id}): {message_content}".format(
                    requester_id=message.author.id,
                    message_id=referenced_message.id,
                    message_content=referenced_message.content,
                )
            )
            await self.remove_own_message(referenced_message)
        else:
            # Someone else's message, so we'll remove reactions
            log.info(
                f"{message.author.id} triggered reaction removal on {referenced_message.id} by {referenced_message.author.id}"
            )
            await self.remove_own_reactions(referenced_message)
        await message.delete(delay=5)
