import os
import json
import logging.config
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from botto.reactions import Reactions
from botto.reminder_manager import ReminderManager
from botto.storage import AirtableMealStorage, ReminderStorage, TimezoneStorage
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

scheduler = AsyncIOScheduler()

storage = AirtableMealStorage(
    config["authentication"]["airtable_base"], config["authentication"]["airtable_key"]
)

reminder_storage = ReminderStorage(
    config["authentication"]["airtable_base"], config["authentication"]["airtable_key"]
)

timezone_storage = TimezoneStorage(
    config["authentication"]["airtable_base"], config["authentication"]["airtable_key"]
)

reactions = Reactions(config)
reminder_manager = ReminderManager(config, scheduler, reminder_storage, reactions)

client = TLDBotto(config, reactions, scheduler, storage, timezone_storage, reminder_manager)
slash = setup_slash(client, config, reminder_manager, timezone_storage)

client.run(config["authentication"]["discord"])