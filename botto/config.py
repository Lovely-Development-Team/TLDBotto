import base64
import binascii
import json
import logging
import re
import os
from datetime import datetime

import pytz as pytz

import food

log = logging.getLogger("TLDBotto").getChild("config")
log.setLevel(logging.DEBUG)


def decode_base64_env(key: str):
    if meals := os.getenv(key):
        decoded = None
        try:
            decoded = base64.b64decode(meals)
            return json.loads(decoded)
        except binascii.Error:
            log.error(f"Unable to decode base64 {key} config", exc_info=True)
            raise
        except json.JSONDecodeError as error:
            log.error(f"Unable to parse decoded {key} config: {error}", exc_info=True)
            if decoded:
                log.debug(f"Decoded config file: {decoded}")
            raise


def parse(config):
    defaults = {
        "id": None,
        "authentication": {
            "discord": "",
            "airtable_key": "",
            "airtable_base": "",
        },
        "channels": {"include": [], "exclude": [], "voting": ["voting"]},
        "reactions": {
            "success": "📥",
            "repeat": "♻️",
            "unknown": "❓",
            "skynet": "👽",
            "fishing": "🎣",
            "invalid": "🙅",
            "pending": "⏳",
            "deleted": "🗑",
            "invalid_emoji": "⚠️",
            "valid_emoji": "✅",
            "reject": "❌",
            "wave": "👋",
            "poke": ["👈", "👆", "👇", "👉", "😢", "🤪", "😝"],
            "love": [
                "❤️",
                "💕",
                "♥️",
                "💖",
                "💙",
                "💗",
                "💜",
                "💞",
                "💛",
                "💚",
                "❣️",
                "🧡",
                "💘",
                "💝",
                "💟",
                "🤍",
                "🤎",
                "💌",
                "😍",
                "🥰",
            ],
            "hug": ["🤗", "🫂"],
            "rule_1": ["⚠️", "1️⃣", "⚠️"],
            "party": [
                "🎉",
                "🎂",
                "🍰",
                "🧁",
                "🎈",
                "🥳",
                "🍾",
                "🥂",
                "🎁",
                "🎊",
                "🪅",
                "👯",
                "💃",
                "🕺",
                "🎆",
                "🎇",
                "💯",
            ],
            "delete_confirmed": "✅",
            "nice_try": "😝",
        },
        "pattern_reactions": {
            "pokes": {
                "trigger": "pokes? {bot_id}",
                "reactions": ["👈", "👆", "👇", "👉", "😢", "🤪", "😝"],
            },
            "vroom": {
                "trigger": "^vroom (?:vroom)+",
                "reactions": ["🚗", "🚘", "🏎️", "🛺", "🛵", "🏍️"],
            },
            "off-topic": {
                "trigger": "off( +|\-)topic",
                "reactions": ["😆", "🤣", "😂", "🤪"],
            },
            "favourite_band": {
                "trigger": "What('|’)?s +your +fav(ou?rite)? +band +{bot_id} ?\?*",
                "reactions": ["🇧", "🇹", "🇸"],
                "reaction_type": "ORDERED",
            },
            "snail": {
                "trigger": "^i am\s+(?:also)?\s*(?:🐌|snail)",
                "reactions": ["🐌"]
            },
            "complaint": {
                "trigger": "(?:(?:BOTTO|TILDY).?\s+COME\.?\s+ON\s*|COME\.?\s+ON\s+(?:BOTTO|TILDY).?\s*)",
                "reactions": ["🤷"],
            },
            "hello": {
                "trigger": "h(i|ello|eya?)\s+({bot_id}|tildy)",
                "reactions": ["👋"],
            },
            "horse": {
                "trigger": "horse",
                "reactions": ["🐎"],
            },
        },
        "food": food.default_config,
        "special_reactions": {},
        "triggers": {
            "meal_time": ["!meal(?:time)?s?$"],
            "timezones": ["!times?"],
            "job_schedule": ["!schedule"],
            "yell": ["!bottoyellat(?P<person>[^.]*)(?:\.(?P<text>.*))?"],
            "reminder_explain": ["!remind(?:er)? (?P<timestamp>[^.]*).(?P<text>.*)"],
            "remove_reactions": [
                "\(?Not now,?\s+(?:Tildy|{bot_id})[.!]?\)?$",
                "\(?Wrong party,?\s+(?:Tildy|{bot_id})[.!]?\)?$",
            ],
        },
        "at_triggers": {
            "add_reminder": ["!remind(?:er)? (?P<timestamp>[^.]*).(?P<text>.*)"],
        },
        "timezones": [],
        "meals": {
            "auto_reminder_hours": ["8", "13", "18", "20", "1"],
            "guilds": [],
            "intro_text": ["Reminder!"]
        },
        "reminder_channel": "833842753799848019",
        "should_reply": True,
        "approval_reaction": "mottoapproval",
        "leaderboard_link": None,
        "delete_unapproved_after_hours": 24,
        "trigger_on_mention": True,
        "confirm_delete_reaction": "🧨",
        "support_channel": None,
        "watching_statūs": ["for food", "for snails", "for apologies", "for love"],
    }

    if isinstance(config, dict):
        for key in defaults.keys():
            if isinstance(defaults[key], dict):
                defaults[key].update(config.get(key, {}))
            else:
                defaults[key] = config.get(key, defaults[key])

    # Environment variables override config files

    if token := os.getenv("TLDBOTTO_DISCORD_TOKEN"):
        defaults["authentication"]["discord"] = token

    if token := os.getenv("TLDBOTTO_AIRTABLE_KEY"):
        defaults["authentication"]["airtable_key"] = token

    if token := os.getenv("TLDBOTTO_AIRTABLE_BASE"):
        defaults["authentication"]["airtable_base"] = token

    if channels := os.getenv("TLDBOTTO_CHANNELS"):
        for key in channels.keys():
            defaults["channels"][key] = channels.get(key, [])

    if timezones := decode_base64_env("TLDBOTTO_TIMEZONES"):
        defaults["timezones"] = timezones

    if meals := decode_base64_env("TLDBOTTO_MEAL_CONFIG"):
        defaults["meals"] = meals

    if id := os.getenv("TLDBOTTO_ID"):
        defaults["id"] = id

    for idx, zone in enumerate(defaults["timezones"]):
        defaults["timezones"][idx] = pytz.timezone(zone)

    return defaults
