import asyncio
import logging
from datetime import datetime
from typing import Union, Optional, Literal

import arrow
import pytz
from dateutil import parser as dateparser
import discord
from discord import app_commands, Interaction

from botto import responses
from botto.clients import AppStoreConnectClient
from botto.clients.stjude_scoreboard import StJudeScoreboardClient
from botto.message_checks import get_or_fetch_member
from botto.models import AirTableError, Timezone
from botto.reminder_manager import (
    ReminderManager,
    TimeTravelError,
    ReminderParsingError,
)
from botto.storage import TimezoneStorage, BetaTestersStorage
from botto.errors import TlderNotFoundError
from botto.tld_botto import TLDBotto
from botto.views.testflight_form import TestFlightForm

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


def setup_slash(
    client: TLDBotto,
    config: dict,
    reminder_manager: ReminderManager,
    timezones: TimezoneStorage,
    testflight_storage: BetaTestersStorage,
    app_store_connect: AppStoreConnectClient,
):
    client.tree.clear_commands(guild=None)
    client.tree.clear_commands(guild=client.snailed_it_beta_guild)
    st_jude_scoreboard_client = StJudeScoreboardClient(
        token=config.get("authentication", {}).get("st_jude_scoreboard_key")
    )

    @client.tree.command(
        name="ping",
        description="Checks Tildy's response time to Discord",
    )
    async def ping(
        interaction: discord.Interaction,
    ):
        log.debug(f"/ping from {interaction.user}")
        await interaction.response.send_message(
            f"Pong! ({interaction.client.latency * 1000}ms)"
        )

    async def _yell(
        ctx: Interaction, person: Union[str, discord.Member], message: Optional[str]
    ):
        log.debug(f"/yell from {ctx.user.id} at {person}: '{message}'")
        message_length = len(message)
        if message_length > 280:
            log.info(f"Message was {message_length} rejecting")
            await ctx.response.send_message(
                "Please limit your yelling to the length of a tweet 🙄"
            )
            return
        response_text = responses.yell_at_someone(person, message)
        await ctx.response.send_message(response_text)

    @client.tree.command(
        name="yell",
        description="Have Botto yell at someone",
    )
    @app_commands.describe(person="The person to yell at.")
    @app_commands.guild_only
    async def yell(ctx: Interaction, person: str, message: Optional[str]):
        await _yell(ctx, person, message)

    @client.tree.command(
        name="yellat",
        description="Have Botto yell at someone (with selection)",
    )
    @app_commands.describe(
        person="The person to yell at.", message="The message to yell."
    )
    @app_commands.guilds(
        client.snailed_it_guild, client.tld_guild, client.developer_hub_guild
    )
    async def yell_at(ctx: Interaction, person: discord.Member, message: Optional[str]):
        await _yell(ctx, person, message)

    def _local_times(time_now: datetime = datetime.utcnow()) -> list[datetime]:
        return [time_now.astimezone(zone) for zone in config["timezones"]]

    @client.tree.command(
        name="times",
        description="Get the current times for TLDers",
    )
    @app_commands.describe(
        current_time="The time to use as 'now'.",
    )
    @app_commands.guilds(
        client.snailed_it_guild, client.tld_guild, client.developer_hub_guild
    )
    async def send_local_times(ctx: Interaction, current_time: Optional[str]):
        parsed_time = datetime.utcnow()
        has_responded = False
        if current_time:
            try:
                parsed_time = dateparser.parse(current_time)
            except ValueError as error:
                await ctx.response.send_message(
                    f"Failed to parse provided time: {error}"
                )
                has_responded = True

        log.debug(f"/times from: {ctx.user} relative to {parsed_time}")
        local_times_string = responses.get_local_times(
            local_times=_local_times(parsed_time)
        )
        converted_string = f"{current_time} converted:\n" if current_time else ""
        if has_responded:
            await ctx.followup.send(converted_string + local_times_string)
        else:
            await ctx.response.send_message(converted_string + local_times_string)

    reminders = app_commands.Group(
        name="reminders", description="Reminders commands", guild_only=True
    )

    @reminders.command(name="list", description="List the currently-set reminders")
    @app_commands.describe(
        channel="Limit list to a specific channel",
    )
    async def list_reminders(
        ctx: Interaction, channel: Optional[app_commands.AppCommandChannel]
    ):
        log.debug(f"/reminder list from: {ctx.user} channel: {ctx.channel}")
        reminders = await reminder_manager.list_reminders(ctx.guild, channel)
        log.debug(f"Reminders: {reminders}")
        reminder_message = "\n".join(
            [await reminder_manager.build_reminder_description(r) for r in reminders]
        )
        await ctx.response.send_message(discord.utils.escape_mentions(reminder_message))

    client.tree.add_command(reminders)

    @client.tree.command(
        name="reminder",
        description="Set a reminder",
    )
    @app_commands.describe(
        at="The date/time of the reminder.",
        message="The message associated with the reminder.",
        advance_warning="Should Tildy send a 15 minute advance warning?",
        channel="What channel should Tildy send a message to? (Defaults to the current one)",
    )
    @app_commands.guilds(
        client.snailed_it_guild, client.tld_guild, client.developer_hub_guild
    )
    async def reminder(
        ctx: Interaction,
        at: str,
        message: str,
        advance_warning: Optional[bool],
        channel: Optional[app_commands.AppCommandChannel],
    ):
        try:
            advance_warning = advance_warning is True
            channel: discord.TextChannel = channel or ctx.channel
            log.debug(
                f"/reminder from: {ctx.user} at: {at}, advance warning: {advance_warning}, channel: {channel}"
            )
            created_reminder = await reminder_manager.add_reminder_slash(
                ctx.user, at, message, channel, advance_reminder=advance_warning
            )
            reminder_message = await reminder_manager.build_reminder_message(
                created_reminder
            )
            await ctx.response.send_message(reminder_message)
        except TimeTravelError as error:
            log.error("Reminder request expected time travel")
            await ctx.response.send_message(error.message, ephemeral=True)
        except ReminderParsingError:
            log.error("Failed to process reminder time", exc_info=True)
            await ctx.response.send_message(
                f"I'm sorry, I was unable to process this time 😢.", ephemeral=True
            )

    @client.tree.command(
        name="unixtime",
        description="Convert a timestamp to Unix Time and display it to you (only)",
    )
    @app_commands.describe(
        timestamp="The date/time of the reminder.",
    )
    async def unix_time(ctx: Interaction, timestamp: str):
        try:
            log.debug(f"/unixtime from: {ctx.user} timestamp: {timestamp}")
            parsed_date = dateparser.parse(timestamp)
        except (ValueError, OverflowError):
            log.error(f"Failed to parse date: {timestamp}", exc_info=True)
            await ctx.response.send_message(
                "Sorry, I was unable to parse that time", ephemeral=True
            )
            return
        unix_timestamp = round(parsed_date.timestamp())
        await ctx.response.send_message(
            f"{timestamp} (parsed as `{parsed_date}`) is `{unix_timestamp}` in Unix Time",
            ephemeral=True,
        )

    @client.tree.command(
        name="time",
        description="Display a time using `<t:>`",
    )
    @app_commands.describe(
        timestamp="Sends a response displaying this timestamp in everyone's local time.",
    )
    async def time(ctx: Interaction, timestamp: str):
        try:
            log.debug(f"/time from: {ctx.user} timestamp: {timestamp}")
            parsed_date = dateparser.parse(timestamp)
        except (ValueError, OverflowError):
            log.error(f"Failed to parse date: {timestamp}", exc_info=True)
            await ctx.response.send_message(
                "Sorry, I was unable to parse that time", ephemeral=True
            )
            return
        unix_timestamp = round(parsed_date.timestamp())
        await ctx.response.send_message(
            f"{timestamp} (parsed as `{parsed_date}`) is <t:{unix_timestamp}> (<t:{unix_timestamp}:R>)"
        )

    async def _get_timezone(discord_id: str) -> Timezone:
        tlder = await timezones.get_tlder(discord_id)
        if tlder is None:
            raise TlderNotFoundError(discord_id)
        timezone = await timezones.get_timezone(tlder.timezone_id)
        return timezone

    timezone_commands = app_commands.Group(
        name="timezones",
        description="Display a time using `<t:>`",
        guild_ids=[guild.id for guild in client.expected_guilds],
    )

    @timezone_commands.error
    async def on_timezones_error(ctx: Interaction, error: Exception):
        log.error(f"Timezone command failed: {ctx.command.name}", exc_info=True)

    timezones_get = app_commands.Group(
        name="get",
        description="Get details of configured timezones",
        parent=timezone_commands,
    )

    @timezones_get.command(
        name="current",
        description="Get your timezone",
    )
    async def get_timezone(ctx: Interaction):
        log.debug(f"/timezones get current from {ctx.user}")
        try:
            timezone = await _get_timezone(str(ctx.user.id))
            await ctx.response.send_message(
                "Your currently configured timezone is: {timezone_name} (UTC{offset})".format(
                    timezone_name=timezone.name,
                    offset=arrow.now(timezone.name).format("Z"),
                ),
                ephemeral=True,
            )
        except TlderNotFoundError:
            log.info(f"{ctx.user} has not configured timezone")
            await ctx.response.send_message(
                "Sorry, you don't have a timezone configured 😢", ephemeral=True
            )
            return

    @timezones_get.command(name="user", description="Get the user's timezone")
    @app_commands.describe(
        person="The user for whom to get the timezone",
    )
    async def get_user_timezone(ctx: Interaction, person: discord.Member):
        log.debug(f"/timezones get user from {ctx.user} for {person}")
        try:
            await ctx.response.defer(thinking=True)
            timezone = await _get_timezone(str(person.id))
            await ctx.followup.send(
                "{person_name}'s currently configured timezone is: {timezone_name} (UTC{offset})".format(
                    person_name=person.display_name,
                    timezone_name=timezone.name,
                    offset=arrow.now(timezone.name).format("Z"),
                )
            )
        except TlderNotFoundError:
            log.info(f"{person} has not configured a timezone")
            await ctx.response.send_message(
                f"{person.display_name} does not appear to have a timezone configured"
            )
            return

    @timezone_commands.command(
        name="set",
        description="Set your timezone. Must be an identifier in the TZ Database.",
    )
    @app_commands.describe(
        timezone_name="Timezone name, as it appears in the TZ Database."
    )
    async def set_my_timezone(ctx: Interaction, timezone_name: str):
        log.debug(f"/timezones set from {ctx.user} for timezone name {timezone_name}")
        tzinfo: pytz.tzinfo
        try:
            tzinfo = pytz.timezone(timezone_name)
        except pytz.UnknownTimeZoneError:
            await ctx.response.send_message(
                f"Sorry, {timezone_name} is not a known TZ DB key", ephemeral=True
            )
            return
        get_tlder_request = timezones.get_tlder(str(ctx.user.id))
        db_timezone = await timezones.find_timezone(tzinfo.zone)
        if db_timezone is None:
            log.info(f"{tzinfo.zone} not found, adding new timezone")
            db_timezone = await timezones.add_timezone(tzinfo.zone)
        if tlder := await get_tlder_request:
            log.info("Updating existing TLDer's timezone")
            try:
                await timezones.update_tlder(tlder, timezone_id=db_timezone.id)
            except AirTableError:
                log.error(f"Failed to update TLDer", exc_info=True)
                await ctx.response.send_message(
                    "Internal error updating TLDer {dizzy}".format(
                        dizzy=config["reactions"]["dizzy"]
                    )
                )
                return
        else:
            log.info("Adding new TLDer with timezone")
            member = (
                await get_or_fetch_member(ctx.guild, ctx.user.id)
                if ctx.guild
                else ctx.user
            )
            await timezones.add_tlder(
                member.display_name, str(ctx.user.id), db_timezone.id
            )
        await ctx.response.send_message(
            "Your timezone has been set to: {timezone_name} (UTC{offset})".format(
                timezone_name=db_timezone.name,
                offset=arrow.now(db_timezone.name).format("Z"),
            ),
            ephemeral=True,
        )

    client.tree.add_command(timezone_commands)

    meals = app_commands.Group(
        name="meals",
        description="Commands for meal reminders",
        guild_ids=[833842753799848016],
    )

    @meals.command(
        name="times", description="Get currently-configured automatic reminder times"
    )
    async def get_meal_times(ctx: Interaction):
        log.debug(f"/timezones times from {ctx.user}")
        if meal_reminder_hours := config.get("meals", {}).get("auto_reminder_hours"):
            reminder_hours = ",".join(meal_reminder_hours)
            await ctx.response.send_message(
                f"Meal auto reminder hours sent at: {reminder_hours}"
            )
        else:
            await ctx.response.send_message("No meal reminder config found")

    client.tree.add_command(meals)

    testflight = app_commands.Group(
        name="testflight",
        description="Commands for TestFlight",
        default_permissions=discord.Permissions(send_messages=True),
    )

    def check_mutual_guilds(ctx: discord.Interaction) -> bool:
        return len(ctx.user.mutual_guilds) > 0

    @testflight.command(
        name="register",
        description="Register your email for TestFlight",
    )
    @app_commands.checks.cooldown(rate=1, per=5.0)
    @app_commands.check(check_mutual_guilds)
    async def testflight_register(ctx: Interaction):
        log.info("/testflight register")

        log.debug(f"Sending registration form")
        await ctx.response.send_modal(
            TestFlightForm(
                testflight_storage,
            )
        )

    @testflight_register.error
    async def on_testflight_registration_error(ctx: Interaction, error: Exception):
        log.error("Failed to show registration form", exc_info=True)

    client.tree.add_command(testflight)

    app_store = app_commands.Group(
        name="appstore",
        description="Commands for the App Store",
        guild_ids=[client.snailed_it_beta_guild.id],
        default_permissions=discord.Permissions(administrator=True),
    )

    async def send_tester_details(ctx, tester_email):
        log.info(f"Finding beta testers with email {tester_email}")
        await ctx.response.defer(ephemeral=True, thinking=True)
        matching_testers = await app_store_connect.find_beta_tester(email=tester_email)
        apps_to_testers = {}
        for tester in matching_testers:
            apps_to_testers[tester.id] = asyncio.create_task(
                testflight_storage.find_apps_by_beta_group(*tester.beta_group_ids)
            )
        response_message = ""
        for tester in matching_testers:
            response_message += f"**ID**: {tester.id}\n"
            if tester.first_name:
                response_message += f"**First name**: {tester.first_name}\n"
            if tester.last_name:
                response_message += f"**Last name**: {tester.last_name}\n"
            if tester.email:
                response_message += f"**Email name**: {tester.email}\n"
            apps = await apps_to_testers[tester.id]
            app_names = [app.name for app in apps]
            log.debug(f"App names: {app_names}")
            response_message += "**Apps**: " + ",".join(app_names)
            if len(app_names) > 0:
                response_message += "\n\n"
            else:
                response_message += "\n"
        await ctx.followup.send(f"{response_message}", ephemeral=True)

    @app_store.command(
        name="lookup_tester",
        description="Lookup details of a Beta Tester",
    )
    @app_commands.describe(
        tester_email="Email address of the tester.",
    )
    @app_commands.checks.has_role("Snailed It")
    async def lookup_tester(
        ctx: Interaction,
        tester_email: str,
    ):
        await send_tester_details(ctx, tester_email)

    @app_store.command(
        name="lookup_user",
        description="Lookup beta testing details of a user",
    )
    @app_commands.describe(
        member="Member to lookup.",
    )
    @app_commands.checks.has_role("Snailed It")
    async def lookup_user(
        ctx: Interaction,
        member: discord.Member,
    ):
        tester = await testflight_storage.find_tester(member.id)
        if not tester:
            await ctx.response.send_message(
                f"User {member.mention} is not a beta tester", ephemeral=True
            )
            return
        await send_tester_details(ctx, tester.email)

    @app_store.error
    async def on_app_store_error(ctx: Interaction, error: Exception):
        log.error("Failed to query app store", exc_info=True)

    client.tree.add_command(app_store)

    cache = app_commands.Group(
        name="cache",
        description="Manage caches",
        guild_ids=[
            client.snailed_it_beta_guild.id,
        ],
        default_permissions=discord.Permissions(administrator=True),
    )

    cache_clear = app_commands.Group(
        name="clear",
        description="Clear caches",
        parent=cache,
        default_permissions=discord.Permissions(administrator=True),
    )

    @cache_clear.command(
        name="reaction_roles",
        description="Clear cached reaction roles",
    )
    @app_commands.checks.has_role("Snailed It")
    async def clear_reaction_roles(
        ctx: Interaction,
    ):
        await ctx.response.defer(ephemeral=True, thinking=True)
        log.info("Starting ID cache refresh")
        async with asyncio.TaskGroup() as tg:
            tg.create_task(client.refresh_reaction_role_caches())
            tg.create_task(
                client.reaction_roles_config_storage.clear_server_cache(
                    str(ctx.guild_id)
                )
            )
        log.info("Completed ID cache refresh")
        log.info("Clearing role approvals channel cache")
        client.role_approvals_channels_cache.clear()
        log.info("Clearing reaction roles cache")
        client.testflight_storage.reaction_roles_cache.clear()
        await ctx.followup.send(f"Cleared reaction roles cache", ephemeral=True)

    @cache_clear.command(
        name="config",
        description="Clear cached config for this server",
    )
    @app_commands.checks.has_role("Snailed It")
    async def clear_config(
        ctx: Interaction,
    ):
        await client.reaction_roles_config_storage.clear_server_cache(str(ctx.guild_id))
        await ctx.response.send_message(f"Cleared server config cache", ephemeral=True)

    @cache.error
    async def on_cache_error(ctx: Interaction, error: Exception):
        log.error("Failed to execute cache command", exc_info=True)

    client.tree.add_command(cache)

    st_jude = app_commands.Group(
        name="st-jude",
        description="Commands related to Relay FM for St Jude",
        guild_ids=[
            client.tld_guild.id,
        ],
    )

    st_jude_score = app_commands.Group(
        name="score",
        description="Commands related to Relay FM for St Jude",
        parent=st_jude,
    )

    @st_jude_score.command(
        name="update",
        description="Update the score for a co-founder",
    )
    async def update_score(
        ctx: Interaction, co_founder: Literal["myke", "stephen"], score: float
    ):
        import aiohttp

        try:
            await st_jude_scoreboard_client.update_score(co_founder, score)
            await ctx.response.send_message(
                f"Updated {co_founder.capitalize()}'s score to {score}"
            )
        except aiohttp.ClientResponseError as e:
            log.error("Failed to update score", exc_info=True)
            await ctx.response.send_message(
                f"Failed to update score due to error: {e.message}"
            )

    @st_jude_score.error
    async def on_app_store_error(ctx: Interaction, error: Exception):
        log.error("Failed to update St Jude score", exc_info=True)

    client.tree.add_command(st_jude)
