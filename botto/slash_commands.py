import logging
from datetime import datetime
from typing import Union, Optional

import dateutil.parser
import discord
from discord_slash import SlashCommand, SlashContext, SlashCommandOptionType
from discord_slash.utils.manage_commands import create_option

import responses

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


def setup_slash(client: discord.Client, config: dict):
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

    return slash
