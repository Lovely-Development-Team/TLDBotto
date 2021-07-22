import logging
import discord
from discord_slash import SlashCommand, SlashContext, SlashCommandOptionType
from discord_slash.utils.manage_commands import create_option

import responses

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


def setup_slash(client: discord.Client):
    slash = SlashCommand(client, sync_commands=True)

    @slash.slash(
        name="ping",
        description="Checks Tildy's response time to Discord",
        guild_ids=[833842753799848016],
    )
    async def _ping(
            ctx: SlashContext,
    ):
        await ctx.send(f"Pong! ({ctx.bot.latency * 1000}ms)")

    @slash.slash(
        name="yell",
        description="Have Botto yell at someone",
        options=[
            create_option(
                name="person",
                description="The person to yell at.",
                option_type=SlashCommandOptionType.USER,
                required=True,
            ),
            create_option(
                name="message",
                description="The message to send.",
                option_type=SlashCommandOptionType.STRING,
                required=False,
            ),
        ],
    )
    async def yell(ctx: SlashContext, person: str, **kwargs):
        message = kwargs.get("message")
        log.info(f"/yell from {ctx.author.id} at {person}: '{message}'")
        response_text = responses.yell_at_someone(person, message)
        await ctx.send(response_text)

    return slash
