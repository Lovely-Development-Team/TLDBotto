import discord
import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from botto.clients import ClickUpClient, AppStoreConnectClient, AppStoreServerClient
from botto.reactions import Reactions
from botto.reminder_manager import ReminderManager
from botto.slash_commands import setup_slash
from botto.storage import (
    AirtableMealStorage,
    ReminderStorage,
    TimezoneStorage,
    EnablementStorage,
    ConfigStorage,
    BetaTestersStorage,
    TestFlightConfigStorage,
)
from botto.tld_botto import TLDBotto


def test_startup():
    scheduler = AsyncIOScheduler()

    storage = AirtableMealStorage("fake_base", "fake_key")

    reminder_storage = ReminderStorage("fake_base", "fake_key")

    timezone_storage = TimezoneStorage("fake_base", "fake_key")

    enablement_storage = EnablementStorage("fake_base", "fake_key")

    config_storage = ConfigStorage("fake_base", "fake_key")

    testflight_storage = BetaTestersStorage(
        "fake_base",
        "fake_key",
    )

    testflight_config_storage = TestFlightConfigStorage(
        "fake_base",
        "fake_key",
    )

    reactions = Reactions({})
    reminder_manager = ReminderManager(
        {}, scheduler, reminder_storage, reactions, timezone_storage
    )

    clickup_client = ClickUpClient("fake_token")

    app_store_connect_client = AppStoreConnectClient({})
    app_store_server_client = AppStoreServerClient({})

    client = TLDBotto(
        {},
        reactions,
        scheduler,
        storage,
        timezone_storage,
        reminder_manager,
        enablement_storage,
        clickup_client,
        config_storage,
        testflight_storage,
        testflight_config_storage,
        app_store_connect_client=app_store_connect_client,
    )
    slash = setup_slash(
        client,
        {},
        reminder_manager,
        timezone_storage,
        testflight_storage,
        testflight_config_storage,
        app_store_connect_client,
        app_store_server_client,
    )
    with pytest.raises(discord.LoginFailure):
        client.run("fake_discord_key")
