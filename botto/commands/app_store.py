import enum
import itertools
import logging

import discord
from discord import app_commands, Interaction

from botto.clients import AppStoreConnectClient
from botto.storage import BetaTestersStorage
from botto.storage.beta_testers.model import (
    TestingRequest,
    RequestStatus,
    AppStoreConnectError,
    ApiKeyNotSetError,
    BetaGroupNotSetError,
    InvalidAttributeError,
    Tester,
    App,
)
from botto.storage.testflight_config_storage import TestFlightConfigStorage
from botto.tld_botto import TLDBotto

log = logging.getLogger(__name__)


class CommandApp(enum.Enum):
    Pushcut = enum.auto()
    ToolboxPro = enum.auto()
    ToolboxPro2 = enum.auto()
    MenuBox = enum.auto()

    @property
    def record_id(self) -> str:
        """
        Get the record ID for the app in Airtable
        """
        match self:
            case CommandApp.Pushcut:
                return "recczpU4YLc2ZJOsd"
            case CommandApp.ToolboxPro:
                return "recxoKsI2Yvxrh0zM"
            case CommandApp.ToolboxPro2:
                return "recVGXp2JWosd04z9"
            case CommandApp.MenuBox:
                return "recnl6sEm15vMf4H6"


class AppStoreCommands:
    def __init__(
        self,
        client: TLDBotto,
        testflight_storage: BetaTestersStorage,
        testflight_config_storage: TestFlightConfigStorage,
        app_store_connect_client: AppStoreConnectClient,
    ):
        self.client = client
        self.testflight_storage = testflight_storage
        self.testflight_config_storage = testflight_config_storage
        self.app_store_connect_client = app_store_connect_client
        self.command_group = app_commands.Group(
            name="appstore",
            description="Commands for the App Store",
            guild_ids=[client.snailed_it_beta_guild.id],
            default_permissions=discord.Permissions(administrator=True),
        )
        self.setup_group()
        # self.command_group.add_command(discord.app_commands.Command())

    async def add_tester(
        self,
        ctx: Interaction,
        tester: Tester,
        member: discord.Member,
        app: App,
    ) -> bool:
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
                return False
            await self.app_store_connect_client.create_beta_tester(
                app, tester.email, tester.given_name, tester.family_name
            )
            log.info(f"Added {tester} to Beta Testers")
            return True
        except AppStoreConnectError as error:
            match error:
                case ApiKeyNotSetError():
                    log.error(
                        f"App Store Api Key not set for {app}",
                        exc_info=True,
                    )
                    await ctx.followup.send(
                        f"{member.mention} No Api Key is set for {app.name}, unable to add tester automatically)",
                        mention_author=False,
                        ephemeral=True,
                    )
                case BetaGroupNotSetError():
                    log.error(
                        f"Beta group not set for {app}",
                        exc_info=True,
                    )
                    await ctx.followup.send(
                        f"{member.mention} No Beta Group is set for {app.name}, "
                        f"unable to add tester automatically)",
                        mention_author=False,
                        ephemeral=True,
                    )
                case InvalidAttributeError(details=details):
                    log.error(
                        f"Invalid tester attribute {details}",
                        exc_info=True,
                    )
                    await ctx.followup.send(
                        f"{member.mention} Tester has an attribute considered invalid by App Store Connect: "
                        f"`{details}`. Unable to add tester automatically)",
                        mention_author=False,
                        ephemeral=True,
                    )
                    raise

    async def handle_add_tester_existing_request(
        self,
        ctx: Interaction,
        member: discord.Member,
        testing_request: TestingRequest,
    ) -> bool:
        approval_channel = None
        if request_approval_channel_id := testing_request.approval_channel_id:
            approval_channel = self.client.get_channel(int(request_approval_channel_id))
        elif (
            guild_approvals_channel_id := await self.testflight_config_storage.get_default_approvals_channel_id(
                testing_request.server_id
            )
        ) and (
            guild_approvals_channel := self.client.get_channel(
                int(guild_approvals_channel_id)
            )
        ):
            approval_channel = guild_approvals_channel
        if not approval_channel or not testing_request.notification_message_id:
            await ctx.followup.send(
                embed=discord.Embed(
                    url=self.testflight_storage.url_for_request(testing_request),
                    title="Access already requested but request message could not be found",
                )
                .add_field(name="Member", value=member.mention)
                .add_field(name="App", value=testing_request.app_name)
                .add_field(
                    name="Request Status", value=testing_request.status, inline=False
                ),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return testing_request.status != RequestStatus.APPROVED
        notification_message = approval_channel.get_partial_message(
            int(testing_request.notification_message_id)
        )
        await ctx.followup.send(
            embed=discord.Embed(
                url=self.testflight_storage.url_for_request(testing_request),
                title="Access already requested",
            )
            .add_field(name="Latest request", value=notification_message.jump_url)
            .add_field(name="Member", value=member.mention)
            .add_field(name="App", value=testing_request.app_name)
            .add_field(
                name="Request Status", value=testing_request.status, inline=False
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return False

    def setup_group(self):
        @self.command_group.command(
            name="add_tester",
            description="Add tester to an app",
        )
        @app_commands.describe(
            member="The member to add as a tester.",
            app="The app to which to add the tester.",
        )
        @app_commands.checks.has_role("Snailed It")
        async def lookup_order_id(
            ctx: Interaction,
            member: discord.Member,
            app: CommandApp,
        ):
            app_record_id: str = app.record_id
            if not app_record_id:
                await ctx.response.send_message("Invalid app specified", ephemeral=True)
                return
            tester = await self.testflight_storage.find_tester(
                discord_id=str(member.id)
            )
            if not tester:
                await ctx.response.send_message(
                    embed=discord.Embed(
                        title=f"{member.name} is not registered",
                        description=f"{member.mention} has no entry in Airtable",
                    )
                    .add_field(name="Member", value=member.mention)
                    .add_field(name="App", value=app.name),
                    allowed_mentions=discord.AllowedMentions.none(),
                    ephemeral=True,
                )
                return
            await ctx.response.defer(ephemeral=True, thinking=True)
            # In case they've changed, update our record
            tester.username = member.name
            tester = await self.testflight_storage.upsert_tester(tester)
            log.debug(f"Updated tester: {tester}")
            if not tester.email:
                await ctx.followup.send(
                    embed=discord.Embed(
                        title=f"{member.name} is not registered",
                        description=f"{member.mention} has not provided an email address",
                    )
                    .add_field(name="Member", value=member.mention)
                    .add_field(name="App", value=app.name),
                    ephemeral=True,
                )
                return
            existing_testing_requests = [
                r
                async for r in self.testflight_storage.list_requests(
                    tester_id=tester.discord_id,
                    app_ids=[app_record_id],
                    exclude_removed=True,
                )
            ]
            if len(existing_testing_requests) == 0:
                testing_request = TestingRequest(
                    tester=tester.id,
                    tester_discord_id=tester.discord_id,
                    app=app_record_id,
                    server_id=str(ctx.guild_id),
                    status=RequestStatus.APPROVED,
                )
            else:
                testing_request = existing_testing_requests[-1]
                if not await self.handle_add_tester_existing_request(
                    ctx, member, testing_request
                ):
                    return

            app = await self.testflight_storage.fetch_app(app_record_id)
            user_added = await self.add_tester(ctx, tester, member, app)
            guild = self.client.get_guild(int(ctx.guild_id))
            roles = [guild.get_role(int(role_id)) for role_id in app.reaction_role_ids]
            tester_user = guild.get_member(int(tester.discord_id))
            if not all(r in tester_user.roles for r in roles):
                log.debug(f"Adding roles {roles} to {tester_user}")
                try:
                    await tester_user.add_roles(
                        *roles, reason=f"Testflight request for {app.name} approved"
                    )
                except discord.DiscordException as e:
                    log.error("Failed to add role to tester", exc_info=True)
                    await ctx.followup.send(
                        f"Failed to add role to tester: {e}",
                    )
            if user_added:
                log.debug(f"Notifying {member} of TestFlight approval")
                await member.send(
                    f"Hi again!\n"
                    f"You have been approved to test **{testing_request.app_name}**.\n"
                    f"A TestFlight invite should have been sent to `{tester.email}`"
                )
            else:
                log.debug(f"Skipping notification, as {member} already approved")
            if len(existing_testing_requests) == 0:
                testing_request = await self.testflight_storage.add_request(
                    testing_request
                )
            else:
                testing_request = await self.testflight_storage.update_request(
                    testing_request
                )
            await ctx.followup.send(
                embed=discord.Embed(
                    title=f"{member.name} added",
                    url=self.testflight_storage.url_for_request(testing_request),
                )
                .add_field(name="Member", value=member.mention)
                .add_field(name="App", value=app.name),
                allowed_mentions=discord.AllowedMentions.none(),
            )

    @property
    def group(self) -> app_commands.Group:
        return self.command_group
