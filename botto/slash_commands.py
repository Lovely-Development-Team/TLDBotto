import logging
from typing import Union

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


def setup_slash(client: discord.Client):
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

    return slash
