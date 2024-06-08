import asyncio
import itertools
import logging
from collections import namedtuple
from datetime import datetime, timedelta
from functools import partial
from typing import Optional
from weakref import WeakValueDictionary

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from asyncache import cachedmethod
from cachetools import TTLCache
from cachetools.keys import hashkey

from botto.clients import AppStoreConnectClient
from botto.extended_client import ExtendedClient
from botto.models import AirTableError
from botto.storage import BetaTestersStorage, ConfigStorage
from botto.storage.beta_testers import model
from botto.storage.beta_testers.beta_testers_storage import RequestApprovalFilter
from botto.storage.beta_testers.model import (
    Tester,
    TestingRequest,
    ApiKeyNotSetError,
    BetaGroupNotSetError,
    InvalidAttributeError,
    AppStoreConnectError,
)

log = logging.getLogger(__name__)

AgreementMessage = namedtuple("AgreementMessage", ["channel_id", "message_id"])


async def mark_request_messages_handled(
    messages: list[discord.Message], reaction: str = "✔️"
):
    return asyncio.gather(
        *[
            m.add_reaction(reaction)
            for m in messages
            if "✅" not in m.reactions
            and "✔️" not in m.reactions
            and reaction not in m.reactions
        ]
    )


async def get_or_fetch_message(
    channel: discord.TextChannel, message_id: int
) -> discord.Message:
    partial_message = channel.get_partial_message(message_id)
    if cached_message := partial_message.to_reference().cached_message:
        message = cached_message
    else:
        message = await partial_message.fetch()
    return message


processing_emoji = "⏳"


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
        self.reaction_roles_config_storage = testflight_config_storage
        self.app_store_connect_client = app_store_connect_client
        self.role_approvals_channels_cache = TTLCache(20, 600)
        scheduler.add_job(
            self.refresh_reaction_role_caches,
            name="Refresh reaction-role watched messages and approval channels",
            trigger="cron",
            minute="*/30",
            coalesce=True,
            next_run_time=datetime.now() + timedelta(seconds=5),
            misfire_grace_time=10,
        )
        self.tester_locks = WeakValueDictionary()
        super().__init__(**kwargs)

    async def refresh_reaction_role_caches(self):
        await asyncio.gather(
            self.testflight_storage.list_watched_message_ids(),
            self.testflight_storage.list_approvals_channel_ids(),
        )

    @cachedmethod(
        lambda self: self.role_approvals_channels_cache,
        key=partial(hashkey, "approvals_channels"),
    )
    async def get_default_approvals_channel_id(self, guild_id: str) -> Optional[str]:
        if result := await self.reaction_roles_config_storage.get_config(
            guild_id, "default_approvals_channel"
        ):
            return result.value
        return None

    @cachedmethod(
        lambda self: self.role_approvals_channels_cache,
        key=partial(hashkey, "rule_agreement_role"),
    )
    async def get_rule_agreement_role_id(self, guild_id: str) -> Optional[str]:
        if result := await self.reaction_roles_config_storage.get_config(
            guild_id, "rule_agreement_role"
        ):
            return result.value
        return None

    @cachedmethod(
        lambda self: self.role_approvals_channels_cache,
        key=partial(hashkey, "tester_exit_notification_channel"),
    )
    async def get_tester_exit_notification_channel(
        self, guild_id: str
    ) -> Optional[str]:
        if result := await self.reaction_roles_config_storage.get_config(
            guild_id, "tester_exit_notification_channel"
        ):
            return result.value
        return None

    async def get_rule_agreement_message(
        self, guild_id: str
    ) -> Optional[AgreementMessage]:
        if result := await self.reaction_roles_config_storage.get_config(
            guild_id, "rule_agreement_message"
        ):
            parsed_result = result.parsed_value
            if (channel_id := parsed_result.get("channel")) and (
                message_id := parsed_result.get("message")
            ):
                return AgreementMessage(channel_id, message_id)
        return None

    async def get_approval_emojis(self, guild_id: str) -> set[str]:
        if result := await self.reaction_roles_config_storage.get_config(
            guild_id, "approval_emojis"
        ):
            return set(result.parsed_value)
        return set()

    async def get_removal_emojis(self, guild_id: str | int) -> set[str]:
        if result := await self.reaction_roles_config_storage.get_config(
            str(guild_id), "removal_emojis"
        ):
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

        if payload.member is None:
            log.warning(
                f"Received a {payload.event_type} reaction with no associated `member`"
            )
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

        if reaction_role.requires_rules_approval and (
            rule_agreement_role_id := await self.get_rule_agreement_role_id(
                str(guild_id)
            )
        ):
            if payload.member.get_role(int(rule_agreement_role_id)) is None:
                log.warning("Role reaction from user who has not agreed to the rules!")
                rules_text = "server rules"
                if rules_message_details := await self.get_rule_agreement_message(
                    str(guild_id)
                ):
                    rules_agreement_channel = guild.get_channel(
                        int(rules_message_details.channel_id)
                    )
                    if rules_agreement_channel is None:
                        log.warning(
                            f"Could not find rules agreement channel with "
                            f"ID {rules_message_details.channel_id} in guild {guild.id}"
                        )
                        return
                    rules_message = rules_agreement_channel.get_partial_message(
                        rules_message_details.message_id
                    )
                    rules_text += f" ({rules_message.jump_url})"
                await payload.member.send(
                    "Hi!\n"
                    f"You've requested access to one of our TestFlights, but have not agreed to the {rules_text}.\n"
                    "Please make sure you agree to the rules before requesting access to a TestFlight.",
                    suppress_embeds=True,
                )
                return

        if len(reaction_role.app_ids) == 0:
            log.info(
                f"Reaction Role {reaction_role} not associated with an app. Adding immediately."
            )
            role = guild.get_role(int(reaction_role.role_id))
            if role is None:
                log.warning(f"No role found with ID {reaction_role.role_id}")
                return
            if role not in payload.member.roles:
                await payload.member.add_roles(
                    role,
                    reason=f"Reaction role for {payload.emoji.name} on message {payload.message_id}",
                    atomic=True,
                )
            return

        # Acquire a lock so that multiple reactions don't trample over each other
        async with self.tester_locks.setdefault(str(payload.user_id), asyncio.Lock()):
            tester = await self.testflight_storage.find_tester(str(payload.member.id))
            log.debug(f"Existing tester: {tester and tester.username or 'No'}")
            if tester is None:
                # This is the first time we've seen this tester
                tester = Tester(
                    username=payload.member.name,
                    discord_id=str(payload.member.id),
                )
            else:
                # In case they've changed, update our record
                tester.username = payload.member.name
                tester.discord_id = str(
                    payload.member.id
                )  # This should always be a no-op?
            tester = await self.testflight_storage.upsert_tester(tester)
            log.debug(f"Updated tester: {tester}")
            existing_testing_requests = [
                r
                async for r in self.testflight_storage.list_requests(
                    tester_id=tester.discord_id,
                    app_ids=reaction_role.app_ids,
                    exclude_removed=True,
                )
            ]
            if len(existing_testing_requests) == 0:
                testing_request = await self.testflight_storage.add_request(
                    TestingRequest(
                        tester=tester.id,
                        tester_discord_id=tester.discord_id,
                        app=reaction_role.app_ids[0],
                        server_id=str(payload.guild_id),
                    )
                )
            if not tester.email:
                if registration_message_id := tester.registration_message_id:
                    previous_registration_message = await payload.member.fetch_message(
                        int(registration_message_id)
                    )
                    # If the last message was recent, we don't want to send it again.
                    if previous_registration_message.created_at > (
                        discord.utils.utcnow() - timedelta(minutes=30)
                    ):
                        log.info(
                            f"Skipping registration message."
                            f" Previously sent at: {previous_registration_message.created_at}"
                        )
                        return
                log.debug(f"Sending registration message to {payload.member}")
                registration_message = await self.send_registration_message(
                    payload.member
                )
                tester.registration_message_id = str(registration_message.id)
                await self.testflight_storage.upsert_tester(tester)
                return

        if len(existing_testing_requests) == 0:
            await self.send_request_notification_message(
                payload.member or await self.get_or_fetch_user(payload.user_id),
                tester,
                testing_request,
            )
        else:
            most_recent_existing_request = existing_testing_requests[-1]
            await self.send_request_notification_message(
                payload.member or await self.get_or_fetch_user(payload.user_id),
                tester,
                most_recent_existing_request,
                is_repeat=True,
            )

    async def send_registration_message(
        self, member: discord.Member
    ) -> discord.Message:
        return await member.send(
            "Hi!\n"
            "You've requested access to one of our TestFlights, but we don't have your email on file.\n"
            "Please reply and use the command `/testflight register` to register your details"
        )

    async def send_request_notification_message(
        self,
        user: discord.User,
        tester: Tester,
        request: TestingRequest,
        is_repeat: bool = False,
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
            log.warning(f"No approvals channel found for server {request.server_id}")
            return
        text = ""
        if is_repeat:
            relative_date = discord.utils.format_dt(request.created.datetime, style="R")
            original_message_link = ""
            if notification_message_id := request.notification_message_id:
                notification_message = approval_channel.get_partial_message(
                    int(notification_message_id)
                )
                original_message_link += f" {notification_message.jump_url}"
            text += f"_This is a repeat request. Original request{original_message_link} was {relative_date}_\n"
            if request.approved:
                text += "**This request was already approved**\n"
        text += (
            f"{user.mention} wants access to **{request.app_name}**\n"
            f"Name: {tester.full_name}\n"
            f"Email: {tester.email}\n"
            f"{self.testflight_storage.url_for_request(request)}"
        )
        message = await approval_channel.send(
            text,
            suppress_embeds=True,
        )
        log.debug(f"Sent message: {message}")
        if not is_repeat:
            request.notification_message_id = message.id
        else:
            request.add_further_notification_message_id(message.id)
        await self.testflight_storage.update_request(request)

    async def send_approval_notification(self, request: TestingRequest, tester: Tester):
        user = await self.get_or_fetch_user(int(request.tester_discord_id))
        log.debug(f"Notifying {user} of TestFlight approval")
        await user.send(
            f"Hi again!\n"
            f"Your request to test **{request.app_name}** has been approved.\n"
            f"A TestFlight invite should have been sent to `{tester.email}`"
        )

    async def is_approval_channel(self, channel_id: str, guild_id: str | int) -> bool:
        if channel_id in self.testflight_storage.approvals_channel_ids:
            return True
        default_approvals_channel_id = await self.get_default_approvals_channel_id(
            str(guild_id)
        )
        return channel_id == default_approvals_channel_id

    async def is_own_message(
        self, payload: discord.RawReactionActionEvent
    ) -> tuple[bool, discord.Message]:
        channel = self.get_channel(payload.channel_id)
        message = await get_or_fetch_message(channel, payload.message_id)
        return message.author.id == self.user.id, message

    async def handle_role_approval(self, payload: discord.RawReactionActionEvent):
        guild_id = payload.guild_id
        if guild_id is None:
            return

        if not await self.is_approval_channel(str(payload.channel_id), guild_id):
            return

        log.debug(f"Role approval for: {payload}")

        guild = self.get_guild(guild_id)
        if guild is None:
            log.warning(f"Found no guild for role approval: {payload}")
            return

        channel = guild.get_channel(payload.channel_id)
        (is_self, message) = await self.is_own_message(payload)
        if not is_self:
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

        try:
            await self.add_tester_to_group(payload, tester, app)
        except InvalidAttributeError:
            log.warning(f"Adding tester failed. Skipping role and notification.")
            return

        roles = [
            guild.get_role(int(role_id))
            for role_id in testing_request.app_reaction_roles_ids
        ]
        tester_user = guild.get_member(int(tester.discord_id))
        if not all(r in tester_user.roles for r in roles):
            log.debug(f"Adding roles {roles} to {tester_user}")
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
                    f"{payload.member.mention} Received approval reaction '{payload.emoji.name}'"
                    f" and added roles to member but failed to notify member due to error: {e}",
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

        try:
            other_messages = (
                [
                    channel.get_partial_message(message_id)
                    for message_id in testing_request.further_notification_message_ids
                    if int(message_id) != payload.message_id
                ]
                if testing_request.further_notification_message_ids
                else []
            )
            if int(testing_request.notification_message_id) != payload.message_id:
                other_messages.append(
                    channel.get_partial_message(
                        int(testing_request.notification_message_id)
                    )
                )
            if not other_messages:
                return
            log.debug("Marking other messages with ✔️")
            cached_messages: list[discord.Message] = []
            non_cached_messages: list[asyncio.Task[discord.Message]] = []
            async with asyncio.TaskGroup() as g:
                for other_message in other_messages:
                    if cached_message := other_message.to_reference().cached_message:
                        cached_messages.append(cached_message)
                    else:
                        non_cached_messages.append(g.create_task(other_message.fetch()))
            async with asyncio.TaskGroup() as g:
                g.create_task(mark_request_messages_handled(cached_messages))
                log.debug("Marked cached messages")
                log.debug(
                    f"Marking non-cached messages {[m.result() for m in non_cached_messages]}"
                )
                g.create_task(
                    mark_request_messages_handled(
                        [m.result() for m in non_cached_messages]
                    )
                )
        except discord.DiscordException as e:
            log.error("Failed to mark message with ✔️", exc_info=True)
            await channel.send(
                f"{payload.member.mention} Received approval reaction '{payload.emoji.name}' and added roles to member"
                f" but failed to mark other message with ✔️ due to error: {e}",
                reference=message.to_reference(),
                mention_author=False,
            )
            raise

    async def handle_removal_reaction(
        self, payload: discord.RawReactionActionEvent
    ) -> bool:
        """
        Handles reactions on leave messages that might be a request to remove a tester from the betas.

        It checks if the reaction was applied to one of the bot's messages, in an appropriate channel, and that it matches a configured removal emoji.
        If so, it finds the tester associated with the leave message and removes them
        from the beta groups.

        Args:
            payload (discord.RawReactionActionEvent): The payload of the reaction event.

        Returns:
            bool: True if the reaction was recognised as a removal reaction, False otherwise.
        """
        if payload.guild_id is None:
            return False

        if not await self.is_approval_channel(
            str(payload.channel_id), payload.guild_id
        ):
            return False

        log.debug(f"Role removal for: {payload}")

        guild = self.get_guild(payload.guild_id)
        if guild is None:
            log.warning(f"Found no guild for role removal: {payload}")
            return False

        (is_self, message) = await self.is_own_message(payload)
        if not is_self:
            return False
        await message.add_reaction(processing_emoji)

        removal_emojis = await self.get_removal_emojis(payload.guild_id)
        if payload.emoji.name not in removal_emojis:
            return False

        tester = await self.testflight_storage.find_tester_by_leave_message(
            payload.message_id
        )
        if not tester:
            log.warning(f"No tester found for leave message {payload.message_id}")
            await guild.get_channel(payload.channel_id).send(
                f"Failed to find tester for leave message {payload.message_id}"
            )
            return False

        await self.remove_tester_from_group(payload, tester)
        return True

    async def handle_reaction(self, payload: discord.RawReactionActionEvent) -> bool:
        handled = False
        try:
            if payload.event_type == "REACTION_ADD":
                await self.handle_role_reaction(payload)
                await self.handle_role_approval(payload)
                handled = handled or await self.handle_removal_reaction(payload)
        except AirTableError as e:
            log.error("Failed to handle reaction", exc_info=True)
            channel = self.get_channel(payload.channel_id)
            await channel.send(
                f"{payload.member.mention} Failed to handle reaction: {e}",
                reference=channel.get_partial_message(
                    payload.message_id
                ).to_reference(),
                mention_author=False,
            )
        finally:
            message = await get_or_fetch_message(
                self.get_channel(payload.channel_id), payload.message_id
            )
            await message.remove_reaction(processing_emoji, self.user)
        return handled

    async def add_tester_to_group(
        self, payload: discord.RawReactionActionEvent, tester: Tester, app: model.App
    ):
        try:
            testers_with_email = await self.app_store_connect_client.find_beta_tester(
                tester.email, app
            )
            groups_for_testers = list(
                itertools.chain.from_iterable(
                    [tester.beta_group_ids for tester in testers_with_email]
                )
            )
            if app.beta_group_id in groups_for_testers:
                log.info(f"{tester.email} already in group {app.beta_group_id}")
                return
            await self.app_store_connect_client.create_beta_tester(
                app, tester.email, tester.given_name, tester.family_name
            )
            log.info(f"Added {tester} to Beta Testers")
        except AppStoreConnectError as error:
            channel = self.get_channel(payload.channel_id)
            message = channel.get_partial_message(payload.message_id)
            match error:
                case ApiKeyNotSetError():
                    log.error(
                        f"App Store Api Key not set for {app}",
                        exc_info=True,
                    )
                    await channel.send(
                        f"{payload.member.mention} No Api Key is set for {app.name}, unable to add tester automatically)",
                        reference=message.to_reference(),
                        mention_author=False,
                    )
                case BetaGroupNotSetError():
                    log.error(
                        f"Beta group not set for {app}",
                        exc_info=True,
                    )
                    await channel.send(
                        f"{payload.member.mention} No Beta Group is set for {app.name}, "
                        f"unable to add tester automatically)",
                        reference=message.to_reference(),
                        mention_author=False,
                    )
                case InvalidAttributeError(details=details):
                    log.error(
                        f"Invalid tester attribute {details}",
                        exc_info=True,
                    )
                    await channel.send(
                        f"{payload.member.mention} Tester has an attribute considered invalid by App Store Connect: "
                        f"`{details}`. Unable to add tester automatically)",
                        reference=message.to_reference(),
                        mention_author=False,
                    )
                    raise

    async def remove_tester_from_group(
        self,
        payload: discord.RawReactionActionEvent,
        tester: Tester,
        app: Optional[model.App] = None,
    ):
        try:
            testers_with_email = await self.app_store_connect_client.find_beta_tester(
                tester.email, app
            )

            channel = self.get_channel(payload.channel_id)
            message = channel.get_partial_message(payload.message_id)

            if not testers_with_email:
                log.info(f"Found no testers with email '{tester.email}'")
                await channel.send(
                    f"{payload.member.mention} Found no testers with email '{tester.email}'",
                    reference=message.to_reference(),
                    mention_author=False,
                )
                return

            if len(testers_with_email) > 1:
                msg = f"Found multiple testers with email '{tester.email}': {testers_with_email}"
                log.info(msg)
                await channel.send(
                    f"{payload.member.mention} {msg}",
                    reference=message.to_reference(),
                    mention_author=False,
                )
                return

            app_store_tester = testers_with_email[0]

            if app.beta_group_id not in app_store_tester.beta_group_ids:
                msg = f"{tester.email} not in group {app.beta_group_id}, removal unnecessary"
                log.info(msg)
                return
            await self.app_store_connect_client.delete_beta_tester(
                app_store_tester.id, app
            )
            log.info(f"Removed {tester} from Beta Testers")
            apps = await self.testflight_storage.find_apps_by_beta_group(
                *app_store_tester.beta_group_ids
            )
            records_to_update = [
                r
                async for r in self.testflight_storage.list_requests(
                    tester_id=str(payload.user_id),
                    app_ids=[app.id for app in apps],
                    approval_filter=RequestApprovalFilter.APPROVED,
                    exclude_removed=True,
                )
            ]
            for r in records_to_update:
                r.removed = True
            await self.testflight_storage.update_requests(records_to_update)
        except AppStoreConnectError as error:
            channel = self.get_channel(payload.channel_id)
            message = channel.get_partial_message(payload.message_id)
            match error:
                case ApiKeyNotSetError():
                    log.error(
                        f"App Store Api Key not set for {app}",
                        exc_info=True,
                    )
                    await channel.send(
                        f"{payload.member.mention} No Api Key is set for {app.name}, unable to add tester automatically",
                        reference=message.to_reference(),
                        mention_author=False,
                    )
                case BetaGroupNotSetError():
                    log.error(
                        f"Beta group not set for {app}",
                        exc_info=True,
                    )
                    await channel.send(
                        f"{payload.member.mention} No Beta Group is set for {app.name}, "
                        f"unable to add tester automatically)",
                        reference=message.to_reference(),
                        mention_author=False,
                    )
                case InvalidAttributeError(details=details):
                    log.error(
                        f"Invalid tester attribute {details}",
                        exc_info=True,
                    )
                    await channel.send(
                        f"{payload.member.mention} Tester has an attribute considered invalid by App Store Connect: "
                        f"`{details}`. Unable to add tester automatically)",
                        reference=message.to_reference(),
                        mention_author=False,
                    )
                    raise

    async def on_raw_member_remove(self, payload: discord.RawMemberRemoveEvent):
        log.debug(f"{payload.user} left server {payload.guild_id}")
        exit_notification_channel_id = await self.get_tester_exit_notification_channel(
            str(payload.guild_id)
        )
        if not exit_notification_channel_id:
            return

        user_testing_apps = [
            (await self.testflight_storage.fetch_app(r.app)).name
            async for r in self.testflight_storage.list_requests(
                tester_id=str(payload.user.id), exclude_removed=True
            )
        ]
        if len(user_testing_apps) == 0:
            return

        exit_notification_channel = self.get_channel(int(exit_notification_channel_id))
        if not exit_notification_channel:
            log.warning(
                f"Unable to notify of tester exit: No channel found with id {exit_notification_channel_id}"
            )
            return

        testing_apps_text = ", ".join(user_testing_apps)
        message = await exit_notification_channel.send(
            f"{payload.user.mention} is testing {testing_apps_text}"
            f" but has left the server!",
        )
        tester = await self.testflight_storage.find_tester(str(payload.user.id))
        if not tester:
            await exit_notification_channel.send(
                f"Failed to find Tester record for {payload.user.mention}. This should never happen!"
            )
            return
        tester.leave_message_ids.append(str(message.id))
        try:
            await self.testflight_storage.upsert_tester(tester)
        except AirTableError as e:
            log.error(
                f"Failed to update tester {tester} with leave message ID", exc_info=True
            )
            await exit_notification_channel.send(
                f"Failed to update tester {tester} with leave message ID: {e}"
            )
