import logging
import re

import discord

from botto.views.dm_reply_form import DMReplyForm

log = logging.getLogger(__name__)


class DMReplyButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"button:dm_reply:(?P<id>[0-9]+):(?P<msg>[0-9]+)",
):
    def __init__(self, user_id: int, message_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label="Reply",
                style=discord.ButtonStyle.blurple,
                custom_id=f"button:dm_reply:{user_id}:{message_id}",
                emoji="✉️",
            )
        )
        self.user_id: int = user_id
        self.msg_id: int = message_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
        /,
    ):
        user_id = int(match["id"])
        msg_id = int(match["msg"])
        return cls(user_id, msg_id)

    async def callback(self, interaction: discord.Interaction) -> None:
        log.info(f"DM reply button for msg {self.msg_id} clicked by {interaction.user}")
        user_dm_channel = interaction.client.get_user(self.user_id).dm_channel
        if user_dm_channel is None:
            user_dm_channel = await interaction.client.get_user(
                self.user_id
            ).create_dm()
        await interaction.response.send_modal(
            DMReplyForm(self.user_id, self.msg_id, interaction.message),
        )
