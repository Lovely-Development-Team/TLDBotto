import os
import json
import logging.config
import asyncio

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from botto.clients import ClickUpClient, AppStoreConnectClient, AppStoreServerClient
from botto.reactions import Reactions
from botto.reminder_manager import ReminderManager
from botto.storage import (
    AirtableMealStorage,
    ReminderStorage,
    TimezoneStorage,
    ConfigStorage,
    BetaTestersStorage,
    TestFlightConfigStorage,
)
from botto.storage.enablement_storage import EnablementStorage
from botto.tld_botto import TLDBotto
from botto.config import parse
from botto.slash_commands import setup_slash

log = logging.getLogger("TLDBotto")

try:
    config_path = os.getenv("MOTTOBOTTO_CONFIG", "config.json")
    log.debug(f"Config path: %s", config_path)
    config_to_parse = {}
    if os.path.isfile(config_path):
        config_to_parse = json.load(open(config_path))
    config = parse(config_to_parse)
except (IOError, OSError, ValueError) as err:
    log.error(f"Config file invalid: {err}")
    exit(1)

log.info(f"Triggers: {config['triggers']}")

scheduler = AsyncIOScheduler(timezone=pytz.UTC)

storage = AirtableMealStorage(
    config["authentication"]["airtable_base"], config["authentication"]["airtable_key"]
)

reminder_storage = ReminderStorage(
    config["authentication"]["airtable_base"], config["authentication"]["airtable_key"]
)

timezone_storage = TimezoneStorage(
    config["authentication"]["airtable_base"], config["authentication"]["airtable_key"]
)

enablement_storage = EnablementStorage(
    config["authentication"]["airtable_base"], config["authentication"]["airtable_key"]
)

config_storage = ConfigStorage(
    config["authentication"]["airtable_base"], config["authentication"]["airtable_key"]
)

testflight_storage = BetaTestersStorage(
    config["authentication"]["snailed_it"]["airtable_base"],
    config["authentication"]["snailed_it"]["airtable_key"],
)

testflight_config_storage = TestFlightConfigStorage(
    config["authentication"]["snailed_it"]["airtable_base"],
    config["authentication"]["snailed_it"]["airtable_key"],
)

reactions = Reactions(config)
reminder_manager = ReminderManager(
    config, scheduler, reminder_storage, reactions, timezone_storage
)

clickup_client = ClickUpClient(config["authentication"]["clickup"])

app_store_connect_client = AppStoreConnectClient(
    config["authentication"]["app_store_connect"]
)
app_store_server_client = AppStoreServerClient(
    config["authentication"]["app_store_server"]
)
client = TLDBotto(
    config,
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
    config,
    reminder_manager,
    timezone_storage,
    testflight_storage,
    app_store_connect_client,
    app_store_server_client,
)


async def main():
    async with client:
        await client.start(config["authentication"]["discord"])


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
loop.close()
