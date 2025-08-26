import logging
from math import floor

import discord

log = logging.getLogger(__name__)


class DMReplyForm(discord.ui.Modal, title="DM Reply"):
    def __init__(
        self, user_id: int, msg_id: int, spawn_msg: discord.PartialMessage
    ) -> None:
        super().__init__()
        self.user_id = user_id
        self.msg_id = msg_id
        self.spawn_msg = spawn_msg

    msg = discord.ui.Label(
        text="Reply to send",
        component=discord.ui.TextInput(
            required=True,
            custom_id="dm_reply_form:msg",
        ),
    )

    async def on_submit(self, interaction: discord.Interaction):
        dm_user = interaction.client.get_user(int(self.user_id))
        user_dm_channel = dm_user.dm_channel
        referenced_message = user_dm_channel.get_partial_message(int(self.msg_id))

        dm_reply = await user_dm_channel.send(
            self.msg.component.value, reference=referenced_message
        )

        try:
            # Replace the Reply button with a message
            fetched_msg = await interaction.channel.fetch_message(self.spawn_msg.id)
            view = discord.ui.LayoutView(timeout=None)
            view.add_item(
                discord.ui.Container(
                    discord.ui.TextDisplay("**Title**: New DM"),
                    discord.ui.TextDisplay(fetched_msg.embeds[0].description),
                    discord.ui.TextDisplay(
                        f"<t:{floor(fetched_msg.embeds[0].timestamp.timestamp())}:t>"
                    ),
                ),
            )
            view.add_item(
                discord.ui.Container(
                    discord.ui.TextDisplay("Reply sent!"),
                    discord.ui.TextDisplay(f"**Sender**: {interaction.user.mention}"),
                    discord.ui.TextDisplay(
                        f"**Replied At**: <t:{floor(dm_reply.created_at.timestamp())}:t>"
                    ),
                    accent_colour=discord.Colour.green(),
                )
            )
            await self.spawn_msg.edit(embed=None, view=view)
        except discord.HTTPException as error:
            log.error(f"Failed to edit message after DM reply: {error}", exc_info=True)
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="Reply Sent",
                    description=f"Your reply has been sent to {dm_user.mention}",
                    timestamp=dm_reply.created_at,
                )
            )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.error(
            f"Failed to reply to user DM from interaction {interaction.id}",
            exc_info=True,
        )

        await interaction.response.send_message(
            f"Oops! Something went wrong. Please report this, providing Interaction ID: {interaction.id}",
            ephemeral=True,
        )
