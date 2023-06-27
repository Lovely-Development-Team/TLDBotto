import asyncio
import logging
from typing import Optional

import discord

from botto.mixins import ReactionRoles
from botto.storage.testflight.model import Tester
from botto.storage.testflight.testflight_storage import TestFlightStorage

log = logging.getLogger(__name__)


class TestFlightForm(discord.ui.Modal, title="TestFlight Registration"):
    def __init__(
        self,
        testflight_storage: TestFlightStorage,
        default_approvals_channel_id: Optional[str],
    ) -> None:
        self.testflight_storage = testflight_storage
        self.default_approvals_channel_id = default_approvals_channel_id
        super().__init__()

    email = discord.ui.TextInput(
        label="Email Address",
        placeholder="Your email address",
        custom_id="testflight_form:email",
    )
    given_name = discord.ui.TextInput(
        label="Given Name",
        required=True,
        custom_id="testflight_form:given_name",
    )
    family_name = discord.ui.TextInput(
        label="Family Name",
        required=False,
        custom_id="testflight_form:family_name",
    )

    async def on_submit(self, interaction: discord.Interaction):
        client: ReactionRoles = interaction.client
        updated_tester = Tester(
            username=interaction.user.name,
            discord_id=str(interaction.user.id),
            email=self.email.value,
            given_name=self.given_name.value,
            family_name=self.family_name.value,
        )
        updated_tester = await self.testflight_storage.upsert_tester(updated_tester)
        log.info(f"Stored tester: {self.email.value}")
        if self.default_approvals_channel_id:
            default_approvals_channel = interaction.client.get_channel(
                int(self.default_approvals_channel_id)
            )
        else:
            default_approvals_channel = None
        requests_generator = self.testflight_storage.list_requests(
            tester_id=interaction.user.id, exclude_approved=True
        )
        log.info(
            f"Testing requests from {updated_tester.discord_id} ({updated_tester.username}): {requests_generator}"
        )
        message_sends = [
            client.send_request_notification_message(
                default_approvals_channel, interaction.user, updated_tester, request
            )
            async for request in requests_generator
        ]

        await asyncio.wait(message_sends)

        await interaction.response.send_message(
            f"Thanks for registering with {self.email.value}!"
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.error(
            f"Failed to register user from interaction {interaction.id}", exc_info=True
        )

        await interaction.response.send_message(
            f"Oops! Something went wrong. Please report this, providing Interaction ID: {interaction.id}",
            ephemeral=True,
        )
