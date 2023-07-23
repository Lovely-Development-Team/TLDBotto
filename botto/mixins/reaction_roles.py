import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from asyncache import cachedmethod
from cachetools import TTLCache

from botto.clients import AppStoreConnectClient
from botto.extended_client import ExtendedClient
from botto.models import AirTableError
from botto.storage import BetaTestersStorage, ConfigStorage
from botto.storage.beta_testers import model
from botto.storage.beta_testers.model import (
    Tester,
    TestingRequest,
    ApiKeyNotSetError,
    BetaGroupNotSetError,
)

log = logging.getLogger(__name__)


class ReactionRoles(ExtendedClient):
    def __init__(
        self,
        scheduler: AsyncIOScheduler,
        reactions_roles_storage: BetaTestersStorage,
        testflight_config_storage: ConfigStorage,
        app_store_connect_client: AppStoreConnectClient,
        **kwargs,
    ):
        self.testflight_storage = reactions_roles_storage
        self.config_storage = testflight_config_storage
        self.app_store_connect_client = app_store_connect_client
        self.approvals_channels_cache = TTLCache(10, 600)
        scheduler.add_job(
            self.refresh_caches,
            name="Refresh reaction-role watched messages and approval channels",
            trigger="cron",
            minute="*/30",
            coalesce=True,
            next_run_time=datetime.now() + timedelta(seconds=5),
            misfire_grace_time=10,
        )
        super().__init__(**kwargs)

    async def refresh_caches(self):
        await asyncio.gather(
            self.testflight_storage.list_watched_message_ids(),
            self.testflight_storage.list_approvals_channel_ids(),
        )

    @cachedmethod(lambda self: self.approvals_channels_cache)
    async def get_default_approvals_channel_id(self, guild_id: str) -> Optional[str]:
        if result := await self.config_storage.get_config(
            guild_id, "default_approvals_channel"
        ):
            return result.value
        return None

    async def get_approval_emojis(self, guild_id: str) -> set[str]:
        if result := await self.config_storage.get_config(guild_id, "approval_emojis"):
            return set(result.parsed_value)
        return set()

    async def handle_role_reaction(self, payload: discord.RawReactionActionEvent):
        watched_message_ids = (
            self.testflight_storage.watched_message_ids
            if len(self.testflight_storage.watched_message_ids) > 0
            else await self.testflight_storage.list_watched_message_ids()
        )
        if str(payload.message_id) not in watched_message_ids:
            return

        guild_id = payload.guild_id
        if guild_id is None:
            log.debug("Reaction on non-guild message. Ignoring")
            return
        guild = self.get_guild(guild_id)
        if guild is None:
            log.error(f"Guild with ID '{guild_id}' not found!")
            return
        reaction_role = await self.testflight_storage.get_reaction_role(
            str(guild_id), str(payload.message_id), payload.emoji.name
        )
        if reaction_role is None:
            log.info("No reaction-role mapping found")
            return
        tester = await self.testflight_storage.find_tester(str(payload.member.id))
        log.debug(f"Existing tester: {tester and tester.username or 'No'}")
        if tester is None:
            tester = Tester(
                username=payload.member.name,
                discord_id=str(payload.member.id),
            )
        else:
            tester.username = payload.member.name
            tester.discord_id = str(payload.member.id)
        tester = await self.testflight_storage.upsert_tester(tester)
        log.debug(f"Updated tester: {tester}")
        testing_request = await self.testflight_storage.add_request(
            TestingRequest(
                tester=tester.id,
                tester_discord_id=tester.discord_id,
                app=reaction_role.app_ids[0],
                server_id=str(payload.guild_id),
            )
        )
        if tester is None or not tester.email:
            dm_channel = payload.member.dm_channel or await payload.member.create_dm()
            await dm_channel.send(
                "Hi!\n You've requested access to one of our TestFlights, but we don't have your email on file.\n"
                "Please enter `/testflight register` to register your details"
            )
            return
        else:
            approvals_channel_id = await self.get_default_approvals_channel_id(
                str(payload.guild_id)
            )
            if approvals_channel_id is None:
                log.warning(f"No approvals channel found for server {payload.guild_id}")
                return
            approvals_channel = self.get_channel(int(approvals_channel_id))
            await self.send_request_notification_message(
                approvals_channel,
                payload.member or await self.get_or_fetch_user(payload.user_id),
                tester,
                testing_request,
            )

    async def send_request_notification_message(
        self,
        default_channel: discord.TextChannel,
        user: discord.User,
        tester: Tester,
        request: TestingRequest,
    ) -> (TestingRequest, discord.Message):
        if request_approval_channel_id := request.approval_channel_id:
            approval_channel = self.get_channel(int(request_approval_channel_id))
        elif (
            guild_approvals_channel_id := await self.get_default_approvals_channel_id(
                request.server_id
            )
        ) and (
            guild_approvals_channel := self.get_channel(int(guild_approvals_channel_id))
        ):
            approval_channel = guild_approvals_channel
        else:
            approval_channel = default_channel
        message = await approval_channel.send(
            f"{user.mention} wants access to **{request.app_name}**\n"
            f"Name: {tester.full_name}\n"
            f"Email: {tester.email}\n"
            f"{self.testflight_storage.url_for_request(request)}",
            suppress_embeds=True,
        )
        log.debug(f"Sent message: {message}")
        request.notification_message_id = message.id
        await self.testflight_storage.update_request(request)

    async def send_approval_notification(self, request: TestingRequest, tester: Tester):
        user = await self.get_or_fetch_user(int(request.tester_discord_id))
        await user.send(
            f"Hi again!\n "
            f"Your request to test **{request.app_name}** has been approved.\n"
            f"A TestFlight invite should have been sent to {tester.email}"
        )

    async def handle_role_approval(self, payload: discord.RawReactionActionEvent):
        guild_id = payload.guild_id
        if guild_id is None:
            return

        if (
            channel_id := str(payload.channel_id)
        ) and channel_id not in self.testflight_storage.approvals_channel_ids:
            default_approvals_channel_id = await self.get_default_approvals_channel_id(
                str(guild_id)
            )
            if channel_id != default_approvals_channel_id:
                return

        log.debug(f"Role approval for: {payload}")
        channel = self.get_channel(payload.channel_id)
        message = channel.get_partial_message(payload.message_id)

        guild = self.get_guild(guild_id)
        if guild is None:
            log.warning(f"Found no guild for role approval: {payload}")
            return

        approval_emojis = await self.get_approval_emojis(str(payload.guild_id))
        if payload.emoji.name not in approval_emojis:
            return

        testing_request = await self.testflight_storage.fetch_request(
            payload.message_id
        )
        if testing_request is None:
            async with channel.typing():
                await channel.send(
                    f"{payload.member.mention} Received approval reaction '{payload.emoji.name}'"
                    f" but no testing requests found for this message!",
                    reference=message.to_reference(),
                    mention_author=False,
                    delete_after=30,
                )
                return
        is_previously_approved_testing_request = testing_request.approved

        tester = await self.testflight_storage.fetch_tester(testing_request.tester)
        if tester is None:
            await channel.send(
                f"{payload.member.mention} Received approval reaction '{payload.emoji.name}'"
                f" but could not find tester!",
                reference=message.to_reference(),
                mention_author=False,
            )
            return

        app = await self.testflight_storage.fetch_app(testing_request.app)
        if app is None:
            log.error(
                f"Failed fetch app {testing_request.app} ({testing_request.app_name})",
                exc_info=True,
            )
            await channel.send(
                f"{payload.member.mention} Failed to fetch app {testing_request.app} ({testing_request.app_name})",
                reference=message.to_reference(),
                mention_author=False,
            )

        testing_request.approved = True

        await self.add_tester_to_group(payload, tester, app)

        roles = [
            guild.get_role(int(role_id))
            for role_id in testing_request.app_reaction_roles_ids
        ]
        tester_user = guild.get_member(int(tester.discord_id))
        if not all(r in tester_user.roles for r in roles):
            log.debug(f"Adding roles {roles} to {payload.member}")
            try:
                await tester_user.add_roles(
                    *roles, reason=f"Testflight request for {app.name} approved"
                )
            except discord.DiscordException as e:
                log.error("Failed to add roles to member", exc_info=True)
                await channel.send(
                    f"{payload.member.mention} Received approval reaction '{payload.emoji.name}'"
                    f" but failed to add roles to member due to error: {e}",
                    reference=message.to_reference(),
                    mention_author=False,
                )
                raise

        if not is_previously_approved_testing_request:
            try:
                await self.send_approval_notification(testing_request, tester)
            except discord.DiscordException as e:
                log.error("Failed to add roles to member", exc_info=True)
                await channel.send(
                    f"{payload.member.mention} Received approval reaction '{payload.emoji.name}'and added roles to member"
                    f" but failed to notify member due to error: {e}",
                    reference=message.to_reference(),
                    mention_author=False,
                )
                raise

        try:
            await self.testflight_storage.update_request(testing_request)
        except AirTableError as e:
            log.error("Failed to mark request as approved", exc_info=True)
            await channel.send(
                f"{payload.member.mention} Failed to mark request as approved in airtable: {e}",
                reference=message.to_reference(),
                mention_author=False,
            )

        try:
            message = channel.get_partial_message(payload.message_id)
            await message.add_reaction("✅")
        except discord.DiscordException as e:
            log.error("Failed to mark message with ✅", exc_info=True)
            await channel.send(
                f"{payload.member.mention} Received approval reaction '{payload.emoji.name}' and added roles to member"
                f" but failed to mark message with ✅ due to error: {e}",
                reference=message.to_reference(),
                mention_author=False,
            )
            raise

    async def add_tester_to_group(
        self, payload: discord.RawReactionActionEvent, tester: Tester, app: model.App
    ):
        try:
            testers_with_email = await self.app_store_connect_client.find_beta_tester(
                tester.email, app
            )
            groups_for_testers = sum(
                [tester.beta_group_ids for tester in testers_with_email], []
            )
            if app.beta_group_id in groups_for_testers:
                log.info(f"{tester.email} already in group {app.beta_group_id}")
                return
            await self.app_store_connect_client.create_beta_tester(
                app, tester.email, tester.given_name, tester.family_name
            )
            log.info(f"Added {tester} to Beta Testers")
        except ApiKeyNotSetError:
            log.error(
                f"App Store Api Key not set for {app}",
                exc_info=True,
            )
            channel = self.get_channel(payload.channel_id)
            message = channel.get_partial_message(payload.message_id)
            await channel.send(
                f"{payload.member.mention} No Api Key is set for {app.name}, unable to add tester automatically)",
                reference=message.to_reference(),
                mention_author=False,
            )
        except BetaGroupNotSetError:
            log.error(
                f"Beta group not set for {app}",
                exc_info=True,
            )
            channel = self.get_channel(payload.channel_id)
            message = channel.get_partial_message(payload.message_id)
            await channel.send(
                f"{payload.member.mention} No Beta Group is set for {app.name}, unable to add tester automatically)",
                reference=message.to_reference(),
                mention_author=False,
            )
