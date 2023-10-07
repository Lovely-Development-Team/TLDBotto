import asyncio
import logging
from typing import Optional

import discord

from botto.mixins import ReactionRoles
from botto.storage.beta_testers.model import Tester
from botto.storage.beta_testers.beta_testers_storage import BetaTestersStorage

log = logging.getLogger(__name__)


class TestFlightForm(discord.ui.Modal, title="TestFlight Registration"):
    def __init__(
        self,
        testflight_storage: BetaTestersStorage,
    ) -> None:
        self.testflight_storage = testflight_storage
        super().__init__()

    email = discord.ui.TextInput(
        label="TestFlight Email Address (Apple ID)",
        placeholder="The email address associated with your Apple ID",
        required=True,
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
        requests_generator = self.testflight_storage.list_requests(
            tester_id=interaction.user.id, exclude_approved=True
        )
        log.info(
            f"Testing requests from {updated_tester.discord_id} ({updated_tester.username}): {requests_generator}"
        )
        message_sends = [
            asyncio.create_task(
                client.send_request_notification_message(
                    interaction.user, updated_tester, request
                )
            )
            async for request in requests_generator
        ]

        await interaction.response.send_message(
            f"Thanks for registering with {self.email.value}!"
        )
        try:
            await asyncio.wait(message_sends)
        except discord.DiscordException:
            await interaction.followup.send(
                f"There was an error submitting your testing requests 😢. Please try again"
            )
            raise

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.error(
            f"Failed to register user from interaction {interaction.id}", exc_info=True
        )

        await interaction.response.send_message(
            f"Oops! Something went wrong. Please report this, providing Interaction ID: {interaction.id}",
            ephemeral=True,
        )
