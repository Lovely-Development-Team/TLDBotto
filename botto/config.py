import re
import os
from datetime import datetime

import pytz as pytz

import food


def parse(config):
    defaults = {
        "id": None,
        "authentication": {
            "discord": "",
            "airtable_key": "",
            "airtable_base": "",
        },
        "channels": {
            "include": [],
            "exclude": [],
        },
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
            "favorite_band": ["🇧", "🇹", "🇸"],
            "off_topic": ["😆", "🤣", "😂", "🤪"],
            "party": ["🎉", "🎂", "🎈", "🥳", "🍾", "🎁", "🎊", "🪅", "👯", "🎆", "🎇"],
            "delete_confirmed": "✅",
        },
        "food": food.default_config,
        "special_reactions": {},
        "triggers": {
            "meal_time": [],
        },
        "timezones": [],
        "meals": {
            "auto_reminder_hours": [
                "8",
                "13",
                "18"
            ],
            "guilds": [],
            "intro_text": ["Reminder!"],
            "times": {}
        },
        "should_reply": True,
        "approval_reaction": "mottoapproval",
        "leaderboard_link": None,
        "delete_unapproved_after_hours": 24,
        "trigger_on_mention": True,
        "confirm_delete_reaction": "🧨",
        "support_channel": None,
        "watching_status": "for food",
    }

    for key in defaults.keys():
        if isinstance(defaults[key], dict):
            defaults[key].update(config.get(key, {}))
        else:
            defaults[key] = config.get(key, defaults[key])

    # Compile trigger regexes
    for key, triggers in defaults["triggers"].items():
        defaults["triggers"][key] = [
            re.compile(f"^{t}", re.IGNORECASE) for t in triggers
        ]

    # Environment variables override config files

    if token := os.getenv("TLDBOTTO_DISCORD_TOKEN"):
        defaults["authentication"]["discord"] = token

    if token := os.getenv("TLDBOTTO_AIRTABLE_KEY"):
        defaults["authentication"]["airtable_key"] = token

    if token := os.getenv("TLDBOTTO_AIRTABLE_BASE"):
        defaults["authentication"]["airtable_base"] = token

    for idx, zone in enumerate(defaults["meals"]["timezones"]):
        defaults["timezones"][idx] = pytz.timezone(zone)

    for key, detail in defaults["meals"]["times"].items():
        start_time = defaults["meals"]["times"][key]["start"]
        end_time = defaults["meals"]["times"][key]["end"]
        defaults["meals"]["times"][key]["start"] = datetime.strptime(start_time, "%H:%M:%SZ").time()
        defaults["meals"]["times"][key]["end"] = datetime.strptime(end_time, "%H:%M:%SZ").time()

    return defaults
