import logging

import discord
from discord import Message

from botto.clients import ClickUpClient
from botto.errors import ClickupError
from botto.message_helpers import truncate_string, hex_to_rgb

log = logging.getLogger(__name__)


class ClickupMixin:
    def __init__(
        self, clickup_client: ClickUpClient, clickup_enabled_guilds: set[str], **kwargs
    ):
        self.clickup_client = clickup_client
        self.enabled_guilds = clickup_enabled_guilds
        super().__init__(**kwargs)

    async def clickup_task(self, message: Message, **kwargs):
        if not message.guild:
            log.info(f"clickup_task triggered in DM")
            return
        if str(message.guild.id) not in self.enabled_guilds:
            log.info(f"clickup_task triggered in non-enabled guild: {message.guild}")
            return
        task_id = kwargs.get("task_id")
        if not task_id:
            log.warning(
                f"{message.content} by {message.author} match task pattern but no `task_id` found"
            )
        only_contains_task_id = message.content.strip().lstrip("#") == task_id
        try:
            task = await self.clickup_client.get_task(task_id)
        except ClickupError as err:
            if err.code == "OAUTH_027":
                log.info(f"Error finding task in ClickUp: {err}")
                return
            raise
        if not task:
            log.info(f"Clickup task '{task_id}' not found")
            return
        task_embed = (
            discord.Embed(
                title=truncate_string(task.name, 256),
                description=(
                    truncate_string(task.description, 4096)
                    if task.description
                    else None
                ),
                colour=discord.Colour.from_rgb(*hex_to_rgb(task.status.colour)),
                timestamp=task.date_created,
                url=task.url,
            )
            .set_author(name=task.creator_name)
            .add_field(
                name="Status",
                value=truncate_string(task.status.name.capitalize(), 1024),
            )
            .add_field(
                name="Tags",
                value=", ".join([tag["name"] for tag in task.tags if tag.get("name")]),
            )
        )

        if priority := task.priority:
            task_embed = task_embed.add_field(
                name="Priority", value=truncate_string(priority, 1024)
            )
        if date_closed := task.date_closed:
            task_embed = task_embed.add_field(
                name="Date Updated",
                value=f"<t:{round(task.date_updated.timestamp())}:f>",
                inline=False,
            ).add_field(
                name="Date Closed", value=f"<t:{round(date_closed.timestamp())}:f>"
            )
        else:
            task_embed = task_embed.add_field(
                name="Date Updated",
                value=f"<t:{round(task.date_updated.timestamp())}:f>",
            )

        if len(task_embed) > 6000:
            chars_to_trim = len(task_embed) - 6000
            task_embed.description = task.description[:-chars_to_trim] + "…"
        if only_contains_task_id:
            await message.channel.send(embed=task_embed)
            try:
                await message.delete()
            except discord.HTTPException as error:
                if error.code != 50003:
                    raise
        else:
            await message.reply(embed=task_embed, mention_author=False)
