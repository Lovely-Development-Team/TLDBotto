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
    any_channel_voting_guilds: list[str]
    members_vote_not_required: dict[str, set[str]]
    ping_disallowed_roles: set[PingDisallowedRole]


def parse(config):
    defaults = {
        "id": None,
        "authentication": {
            "discord": "",
            "airtable_key": "",
            "airtable_base": "",
        },
        "channels": {"include": set(), "exclude": set(), "voting": {"voting"}},
        "voting": VotingConfig(
            any_channel_voting_guilds=["833842753799848016", "880491989995499600"],
            members_vote_not_required={
                "833842753799848016": set(),
                "880491989995499600": set()
            },
            ping_disallowed_roles={
                PingDisallowedRole(role_id=None, name="voting_ping_disallowed")
            },
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
            "dizzy": "😵‍💫",
            "feature_disabled": "📴"
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
                "trigger": "(?:('|’)(re|m|s)|am|are|is|was) (?:(\S{1,25} ){0,3})(?:(snail|🐌)(ie(\S*)|s|-(\S*))?)",
                "reactions": ["🐌"],
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
            "please": {
                "trigger": "^pl(?:e+)ase",
                "reactions": ["🥺"],
            },
            "goodnight": {
                "trigger": "[Gg]ood\s?night\s+(?:{bot_id}|tildy)",
                "reactions": [
                    "💤",
                    "😴",
                    "🛏️",
                ],
            },
            "outage": {"trigger": "outage", "reactions": ["😵"]},
            "chocolate": {"trigger": "chocolate", "reactions": ["🍫"]},
            "cow": {
                "trigger": "^(?:c+{lb}*o+{lb}*w+{lb}*s*|m+{lb}*o{lb}*o+{lb}?)[\s\t\n\r\v]*$".format(
                    lb=line_break_matcher
                ),
                "reactions": ["🐮", "🐄"],
            },
            "honk": {
                "trigger": "(?:^|\s)honk(?:$|\s)",
                "reactions": ["🦆", "📣", "🎺", "🎷", "📢"],
            },
            "fisrt": {
                "trigger": "^\s*f[isr]{2,3}t\s*$",
                "reactions": ["🤦"],
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
            "enabled": ["(?:#|!)enabled\s*(?P<text>.*)?"],
            "drama_llama": ["Oh no", "drama", "llama", "<:ohno\S*:\d+"],
            "remaining_voters": [
                "!remaining\s*(?P<ping>!ping)?",
                "drama",
                "llama",
                "<:ohno\S*:\d+",
            ],
        },
        "drama_llama_id": 760972696284299294,
        "at_triggers": {
            "add_reminder": ["!remind(?:er)? (?P<timestamp>[^.]*).(?P<text>.*)"],
        },
        "timezones": [],
        "meals": {
            "auto_reminder_hours": ["8", "13", "18", "20", "1"],
            "guilds": [],
            "intro_text": ["Reminder!"],
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
        "disabled_features": {}
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

    if channels := decode_base64_env("TLDBOTTO_CHANNELS"):
        for key in channels.keys():
            defaults["channels"][key] = set(channels.get(key, []))

    if channels := os.getenv("TLDBOTTO_ANY_CHANNEL_VOTING_GUILDS"):
        defaults["voting"].any_channel_voting_guilds = channels

    if members_vote_not_required_env := decode_base64_env(
        "TLDBOTTO_MEMBERS_VOTE_NOT_REQUIRED"
    ):
        for guild, members in members_vote_not_required_env.items():
            defaults["voting"].members_vote_not_required[str(guild)] = set(
                members
            )

    if ping_disallowed_roles := decode_base64_env(
        "TLDBOTTO_VOTING_PING_DISALLOWED_ROLES"
    ):
        if isinstance(ping_disallowed_roles, list):
            disallowed_roles_list = [
                PingDisallowedRole(
                    role_id=role.get("role_id"), name=role.get("name")
                )
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

    if threshold := os.getenv("TLDBOTTO_NEXT_DAY_THRESHOLD"):
        defaults["time_is_next_day_threshold_hours"] = int(threshold)

    if disabled_features := decode_base64_env("TLDBOTTO_DISABLED_FEATURES"):
        defaults["disabled_features"] = set(disabled_features)

    if id := os.getenv("TLDBOTTO_ID"):
        defaults["id"] = id

    for idx, zone in enumerate(defaults["timezones"]):
        defaults["timezones"][idx] = pytz.timezone(zone)

    return defaults
