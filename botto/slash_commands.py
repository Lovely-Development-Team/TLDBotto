import logging
from datetime import datetime
from typing import Union, Optional

import dateutil.parser
import discord
from discord_slash import SlashCommand, SlashContext, SlashCommandOptionType
from discord_slash.utils.manage_commands import create_option

import responses
from reminder_manager import ReminderManager, TimeTravelError, ReminderParsingError

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


def person_option(autocomplete: bool):
    return create_option(
        name="person",
        description="The person to yell at.",
        option_type=SlashCommandOptionType.USER
        if autocomplete
        else SlashCommandOptionType.STRING,
        required=True,
    )


message_option = create_option(
    name="message",
    description="The message to send.",
    option_type=SlashCommandOptionType.STRING,
    required=False,
)


def setup_slash(
    client: discord.Client, config: dict, reminder_manager: ReminderManager
):
    slash = SlashCommand(client, sync_commands=True)

    @slash.slash(
        name="ping",
        description="Checks Tildy's response time to Discord",
        # guild_ids=[833842753799848016],
    )
    async def ping(
        ctx: SlashContext,
    ):
        await ctx.send(f"Pong! ({ctx.bot.latency * 1000}ms)")

    async def _yell(ctx: SlashContext, person: Union[str, discord.Member], **kwargs):
        message = kwargs.get("message")
        log.info(f"/yell from {ctx.author.id} at {person}: '{message}'")
        response_text = responses.yell_at_someone(person, message)
        await ctx.send(response_text)

    @slash.slash(
        name="yell",
        description="Have Botto yell at someone",
        options=[
            person_option(False),
            message_option,
        ],
        # guild_ids=[833842753799848016],
    )
    async def yell(ctx: SlashContext, person: str, **kwargs):
        message = kwargs.get("message")
        log.info(f"/yell from {ctx.author.id} at {person}: '{message}'")
        response_text = responses.yell_at_someone(person, message)
        await ctx.send(response_text)

    @slash.slash(
        name="yellat",
        description="Have Botto yell at someone (with selection)",
        options=[
            person_option(True),
            message_option,
        ],
        # guild_ids=[833842753799848016],
    )
    async def yell_at(ctx: SlashContext, person: discord.Member, **kwargs):
        await _yell(ctx, person, **kwargs)

    def _local_times(time_now: datetime = datetime.utcnow()) -> list[datetime]:
        return [time_now.astimezone(zone) for zone in config["timezones"]]

    @slash.slash(
        name="times",
        description="Get the current times for TLDers",
        options=[
            create_option(
                name="current_time",
                description="The time to use as 'now'.",
                option_type=SlashCommandOptionType.STRING,
                required=False,
            )
        ],
        # guild_ids=[833842753799848016],
    )
    async def send_local_times(ctx: SlashContext, **kwargs):
        parsed_time = datetime.utcnow()
        current_time = kwargs.get("current_time")
        if current_time:
            try:
                parsed_time = dateutil.parser.parse(current_time)
            except ValueError as error:
                await ctx.send(f"Failed to parse provided time: {error}")

        log.info(f"\\times from: {ctx.author.id} relative to {parsed_time}")
        local_times_string = responses.get_local_times(
            local_times=_local_times(parsed_time)
        )
        await ctx.send(current_time + " converted:\n" + local_times_string)

    @slash.slash(
        name="reminder",
        description="Set a reminder",
        options=[
            create_option(
                name="at",
                description="The date/time of the reminder.",
                option_type=SlashCommandOptionType.STRING,
                required=True,
            ),
            create_option(
                name="message",
                description="The message associated with the reminder.",
                option_type=SlashCommandOptionType.STRING,
                required=True,
            ),
            create_option(
                name="advance_warning",
                description="Should Tildy send a 15 minute advance warning?",
                option_type=SlashCommandOptionType.BOOLEAN,
                required=False,
            ),
            create_option(
                name="channel",
                description="What channel should Tildy send a message to? (Defaults to the current one)",
                option_type=SlashCommandOptionType.CHANNEL,
                required=False,
            ),
        ],
        # guild_ids=[833842753799848016],
    )
    async def reminder(ctx: SlashContext, at: str, message: str, **kwargs):
        try:
            advance_warning = kwargs.get("advance_warning") is True
            channel: discord.TextChannel = kwargs.get("channel") or ctx.channel
            created_reminder = await reminder_manager.add_reminder_slash(
                ctx.author, at, message, channel, advance_reminder=advance_warning
            )
            await ctx.send(await reminder_manager.build_reminder_message(created_reminder))
        except TimeTravelError as error:
            log.error("Reminder request expected time travel")
            await ctx.send(error.message, hidden=True)
        except ReminderParsingError:
            log.error("Failed to process reminder time", exc_info=True)
            await ctx.send(
                f"I'm sorry, I was unable to process this time 😢.", hidden=True
            )

    @slash.slash(
        name="unixtime",
        description="Covert a timestamp to Unix Time and display it to you (only)",
        options=[
            create_option(
                name="timestamp",
                description="The date/time of the reminder.",
                option_type=SlashCommandOptionType.STRING,
                required=True,
            )
        ],
        # guild_ids=[833842753799848016],
    )
    async def unix_time(ctx: SlashContext, timestamp: str):
        try:
            parsed_date = dateutil.parser.parse(timestamp)
        except (ValueError, OverflowError):
            log.error(f"Failed to parse date: {timestamp}", exc_info=True)
            await ctx.send("Sorry, I was unable to parse that time", hidden=True)
            return
        unix_timestamp = round(parsed_date.timestamp())
        await ctx.send(f"{timestamp} (parsed as `{parsed_date}`) is `{unix_timestamp}` in Unix Time", hidden=True)

    @slash.slash(
        name="time",
        description="Display a time using `<t:>",
        options=[
            create_option(
                name="timestamp",
                description="Sends a response displaying this timestamp in everyone's local time.",
                option_type=SlashCommandOptionType.STRING,
                required=True,
            )
        ],
        # guild_ids=[833842753799848016],
    )
    async def time(ctx: SlashContext, timestamp: str):
        try:
            parsed_date = dateutil.parser.parse(timestamp)
        except (ValueError, OverflowError):
            log.error(f"Failed to parse date: {timestamp}", exc_info=True)
            await ctx.send("Sorry, I was unable to parse that time", hidden=True)
            return
        unix_timestamp = round(parsed_date.timestamp())
        await ctx.send(f"{timestamp} (parsed as `{parsed_date}`) is <t:{unix_timestamp}> (<t:{unix_timestamp}:R>)")

    return slash
