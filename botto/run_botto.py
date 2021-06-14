import os
import json
import logging.config
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from reactions import Reactions
from reminder_manager import ReminderManager
from storage import AirtableMealStorage, ReminderStorage
from tld_botto import TLDBotto
from config import parse

# Configure logging
logging.config.fileConfig(fname="log.conf", disable_existing_loggers=False)
logging.getLogger("discord").setLevel(logging.CRITICAL)
logging.getLogger("discord.gateway").setLevel(logging.INFO)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)
logging.getLogger("urllib").setLevel(logging.CRITICAL)
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
    config["authentication"]["airtable_base"],
    config["authentication"]["airtable_key"]
)

reminder_storage = ReminderStorage(
    config["authentication"]["airtable_base"],
    config["authentication"]["airtable_key"]
)

reminder_manager = ReminderManager(config, scheduler, reminder_storage)

client = TLDBotto(config, Reactions(config), scheduler, storage, reminder_manager)
client.run(config["authentication"]["discord"])
