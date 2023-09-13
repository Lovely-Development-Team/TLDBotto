import base64
import binascii
import json
import logging
import os
from collections import namedtuple
from dataclasses import dataclass

import pytz as pytz

from . import food

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


line_break_matcher = "[\t\n\r\v]"

PingDisallowedRole = namedtuple("PingDisallowedRole", ["role_id", "name"])


@dataclass
class VotingConfig:
    any_channel_guilds: list[str]
    members_not_required: dict[str, set[str]]
    ping_disallowed_roles: set[PingDisallowedRole]
    exclusion_emojis: set[str]


bot_id_pattern = "{bot_id}"
bot_name_pattern = "{bot_name}"
bot_id_or_name_pattern = f"(?:{bot_id_pattern}|{bot_name_pattern})"


def parse(config):
    defaults: dict = {
        "id": None,
        "authentication": {
            "discord": "",
            "airtable_key": "",
            "airtable_base": "",
            "clickup": "",
            "snailed_it": {"airtable_key": "", "airtable_base": ""},
            # Format: {"theKeyId": "iss": "theIssuerId", "kid": "theKeyId", "secret": "theKey"}
            "app_store_connect": {},
        },
        "channels": {"include": set(), "exclude": set(), "voting": {"voting"}},
        "voting": VotingConfig(
            any_channel_guilds=["833842753799848016", "880491989995499600"],
            members_not_required={},
            ping_disallowed_roles={
                PingDisallowedRole(role_id=None, name="voting_ping_disallowed")
            },
            exclusion_emojis={"🙅‍"},
        ),
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
            "confirm": "👍",
            "decline": "👎",
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
            "enabled": "💸",
            "no_amount": ["💰", "❓"],
            "unrecognised_currency": ["💷", "❓"],
            "unknown_person": ["🧍", "❓"],
            "unknown_person_timezone": ["🧍", "🗺️", "❓"],
            "dizzy": "😵‍💫",
            "feature_disabled": "📴",
        },
        "bot_name_regexes": ["tildy"],
        "pattern_reactions": {
            "pokes": {
                "trigger": f"pokes? {bot_id_or_name_pattern}",
                "reactions": ["👈", "👆", "👇", "👉", "😢", "🤪", "😝"],
            },
            "vroom": {
                "trigger": "^vroom (?:vroom)+",
                "reactions": ["🚗", "🚘", "🏎️", "🛺", "🛵", "🏍️"],
            },
            "off-topic": {
                "trigger": r"off( +|\-)topic",
                "reactions": ["😆", "🤣", "😂", "🤪"],
                "exclude_guilds": ["890978723451523083"],
            },
            "favourite_band": {
                "trigger": rf"What('|’)?s +your +fav(ou?rite)? +band +{bot_id_pattern} ?\?*",
                "reactions": ["🇧", "🇹", "🇸"],
                "reaction_type": "ORDERED",
            },
            "snail": {
                "trigger": r"(?:('|’)(re|m|s)|am|are|is|was) (?:(\S{1,25} ){0,3})(?:(snail|🐌)(ie(\S*)|s|-(\S*))?)",
                "reactions": ["🐌"],
            },
            "complaint": {
                "trigger": rf"(?:(?:BOTTO|{bot_name_pattern}).?\s+COME\.?\s+ON\s*|COME\.?\s+ON\s+(?:BOTTO|{bot_name_pattern}).?\s*)",
                "reactions": ["🤷"],
            },
            "hello": {
                "trigger": rf"h(i|ello|eya?)\s+{bot_id_or_name_pattern}",
                "reactions": ["👋"],
            },
            "horse": {
                "trigger": "horse",
                "reactions": ["🐎"],
            },
            "please": {
                "trigger": "^pl(?:e+)ase",
                "reactions": ["🥺"],
                "exclude_guilds": ["833842753799848016", "890978723451523083"],
            },
            "goodnight": {
                "trigger": rf"[Gg]ood\s?night\s+{bot_id_or_name_pattern}",
                "reactions": [
                    "💤",
                    "😴",
                    "🛏️",
                ],
            },
            "outage": {"trigger": "outage", "reactions": ["😵"]},
            "chocolate": {"trigger": "chocolate", "reactions": ["🍫"]},
            "cow": {
                "trigger": r"^(?:c+{lb}*o+{lb}*w+{lb}*s*|m+{lb}*o{lb}*o+{lb}?)[\s\t\n\r\v]*$".format(
                    lb=line_break_matcher
                ),
                "reactions": ["🐮", "🐄"],
            },
            "honk": {
                "trigger": r"(?:^|\s)honk(?:$|\s)",
                "reactions": ["🦆", "📣", "🎺", "🎷", "📢"],
            },
            "fisrt": {
                "trigger": r"^\s*f[isr]{2,3}t\s*$",
                "reactions": ["🤦"],
            },
            "good bot": {
                "trigger": r"^\s*good\s*bot\s*$",
                "reactions": ["😊"],
            },
        },
        "food": food.default_config,
        "special_reactions": {},
        "triggers": {
            "meal_time": ["!meal(?:time)?s?$"],
            "timezones": ["!times?"],
            "job_schedule": ["!schedule"],
            "yell": [r"!bottoyellat(?P<person>[^.]*)(?:\.(?P<text>.*))?"],
            "reminder_explain": ["!remind(?:er)? (?P<timestamp>[^.]*).(?P<text>.*)"],
            "remove_reactions": [
                r"\(?Not now,?\s+(?:{bot_name}|{bot_id})[.!]?\)?$",
                r"\(?Wrong party,?\s+(?:{bot_name}|{bot_id})[.!]?\)?$",
            ],
            "enabled": [r"(?:#|!)enabled\s*(?P<text>.*)?"],
            "drama_llama": [r"Oh\s*no", "drama", "llama", "🦙", r"<:ohno\S*:\d+"],
            "remaining_voters": [r"!remaining\s*(?P<ping>!ping)?"],
            "clickup_task": [r".*(?:\s+|\(|^)#(?P<task_id>\w\w+)(?:\s+|\)|:|$).*"],
        },
        "clickup_enabled_guilds": ["833842753799848016"],
        "drama_llama_id": 760972696284299294,
        "at_triggers": {
            "add_reminder": ["!remind(?:er)? (?P<timestamp>[^.]*).(?P<text>.*)"],
        },
        "timezones": [],
        "meals": {
            "auto_reminder_hours": ["8", "13", "18", "20", "1"],
            "guilds": [],
            "previous_to_keep": 2,
        },
        "time_is_next_day_threshold_hours": 6,
        "reminder_channel": "833842753799848019",
        "should_reply": True,
        "approval_reaction": "mottoapproval",
        "leaderboard_link": None,
        "delete_unapproved_after_hours": 24,
        "trigger_on_mention": True,
        "confirm_delete_reaction": "🧨",
        "support_channel": None,
        "watching_statūs": ["for food", "for snails", "for apologies", "for love"],
        "disabled_features": {},
    }

    if isinstance(config, dict):
        for key in defaults.keys():
            if isinstance(defaults[key], dict):
                defaults[key].update(config.get(key, {}))
            else:
                defaults[key] = config.get(key, defaults[key])

    # Environment variables override config files

    if token := os.getenv("DISCORD_TOKEN"):
        defaults["authentication"]["discord"] = token

    if token := os.getenv("TLD_AIRTABLE_KEY"):
        defaults["authentication"]["airtable_key"] = token

    if token := os.getenv("TLDBOTTO_AIRTABLE_BASE"):
        defaults["authentication"]["airtable_base"] = token

    if token := os.getenv("TLDBOTTO_CLICKUP_TOKEN"):
        defaults["authentication"]["clickup"] = token

    if token := os.getenv("SNAILEDIT_AIRTABLE_KEY"):
        defaults["authentication"]["snailed_it"]["airtable_key"] = token

    if token := os.getenv("SNAILEDIT_AIRTABLE_BASE"):
        defaults["authentication"]["snailed_it"]["airtable_base"] = token

    if app_store_connect_api_keys := decode_base64_env("APP_STORE_CONNECT_API_KEYS"):
        defaults["authentication"]["app_store_connect"] = app_store_connect_api_keys
        for key, value in app_store_connect_api_keys.items():
            try:
                defaults["authentication"]["app_store_connect"][key] = {
                    "iss": value["iss"],
                    "kid": value["kid"],
                    "secret": base64.b64decode(value["secret"]).decode("utf-8"),
                }
            except binascii.Error:
                log.error(
                    f"Unable to decode base64 secret for kid '{key}'", exc_info=True
                )

    if channels := decode_base64_env("TLDBOTTO_CHANNELS"):
        for key in channels.keys():
            defaults["channels"][key] = set(channels.get(key, []))

    if channels := os.getenv("TLDBOTTO_ANY_CHANNEL_VOTING_GUILDS"):
        defaults["voting"].any_channel_guilds = channels

    if members_vote_not_required_env := decode_base64_env(
        "TLDBOTTO_MEMBERS_VOTE_NOT_REQUIRED"
    ):
        defaults["voting"].members_not_required = members_vote_not_required_env

    for guild, members in defaults["voting"].members_not_required.items():
        defaults["voting"].members_not_required[str(guild)] = set(members)

    if ping_disallowed_roles := decode_base64_env(
        "TLDBOTTO_VOTING_PING_DISALLOWED_ROLES"
    ):
        if isinstance(ping_disallowed_roles, list):
            disallowed_roles_list = [
                PingDisallowedRole(role_id=role.get("role_id"), name=role.get("name"))
                for role in ping_disallowed_roles
            ]
            defaults["voting"].ping_disallowed_roles = set(disallowed_roles_list)
        else:
            log.warning("TLDBOTTO_VOTING_PING_DISALLOWED_ROLES env is not a list")

    log.debug(
        "Roles disallowing voting pings: {roles}".format(
            roles=defaults["voting"].ping_disallowed_roles
        )
    )

    if timezones := decode_base64_env("TLDBOTTO_TIMEZONES"):
        defaults["timezones"] = timezones

    if meals := decode_base64_env("TLDBOTTO_MEAL_CONFIG"):
        defaults["meals"] = meals

    if reminder_hours := decode_base64_env("TLDBOTTO_MEAL_REMINDER_HOURS"):
        current_meals = defaults.get("meals", {})
        current_meals["auto_reminder_hours"] = reminder_hours
        defaults["meals"] = current_meals

    if reminders_to_keep := decode_base64_env(
        "TLDBOTTO_MEAL_PREVIOUS_REMINDERS_TO_KEEP"
    ):
        current_meals = defaults.get("meals", {})
        current_meals["previous_to_keep"] = int(reminders_to_keep)
        defaults["meals"] = current_meals

    if threshold := os.getenv("TLDBOTTO_NEXT_DAY_THRESHOLD"):
        defaults["time_is_next_day_threshold_hours"] = int(threshold)

    if disabled_features := decode_base64_env("TLDBOTTO_DISABLED_FEATURES"):
        defaults["disabled_features"] = set(disabled_features)

    if clickup_enabled_guilds := decode_base64_env("TLDBOTTO_CLICKUP_ENABLED_GUILDS"):
        defaults["clickup_enabled_guilds"] = clickup_enabled_guilds

    defaults["clickup_enabled_guilds"] = set(defaults["clickup_enabled_guilds"])

    if id := os.getenv("TLDBOTTO_ID"):
        defaults["id"] = id

    for idx, zone in enumerate(defaults["timezones"]):
        defaults["timezones"][idx] = pytz.timezone(zone)

    return defaults
