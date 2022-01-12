import re
from dataclasses import dataclass
from re import Pattern
from typing import Optional

import discord

from botto.food import FoodLookups


class PatternReactions:
    def __init__(self, pattern_reactions: dict) -> None:
        self.reaction_map = pattern_reactions
        super().__init__()

    def matches(self, message: discord.Message) -> list[str]:
        matching_keys = []
        for key, value in self.reaction_map.items():
            if str(message.guild.id) not in value.get("exclude_guilds", []) and value[
                "trigger"
            ].search(message.content):
                matching_keys.append(key)
        return matching_keys


laugh_emojis = "[😆😂🤣]"


class SuggestionRegexes:
    at_command: [Pattern]
    sorry: Pattern
    apologising: Pattern
    love: Pattern
    hug: Pattern
    food: FoodLookups
    party: Pattern
    patterns: PatternReactions
    triggers: dict[str, list[Pattern]]
    at_triggers: dict[str, list[Pattern]]
    convert_time: Pattern

    _bot_id: str
    _bot_name: Pattern

    def _compile_triggers(self, self_id: str, trigger_dict: dict) -> dict:
        for name, triggers in trigger_dict.items():
            trigger_dict[name] = [
                re.compile(
                    "^{trigger}".format(trigger=replace_bot_id(trigger, self_id)),
                    re.IGNORECASE,
                )
                for trigger in triggers
            ]
        return trigger_dict

    def __init__(self, bot_user_id: str, config: dict) -> None:
        super().__init__()
        self._bot_id = bot_user_id
        self.bot_name = re.compile(
            rf"(?:{'|'.join(config.get('bot_name_regexes', []))})",
            re.IGNORECASE | re.UNICODE,
        )

        self_id = rf"<@!?{bot_user_id}>"
        # Compile trigger regexes
        trigger_dict = self._compile_triggers(self_id, config["triggers"])
        at_trigger_dict = self._compile_triggers(self_id, config["at_triggers"])

        # Compile pattern reactions
        for key, triggers in config["pattern_reactions"].items():
            config["pattern_reactions"][key]["trigger"] = re.compile(
                replace_bot_id(config["pattern_reactions"][key]["trigger"], self_id),
                re.IGNORECASE | re.UNICODE,
            )

        self.at_command = [re.compile(rf"^{self_id}(?P<command>.*)")]
        self.sorry = re.compile(rf"sorry,? {self_id}", re.IGNORECASE)
        self.apologising = re.compile(
            rf"""
                    (?:
                        I['"’m]* #Match I/I'm
                        |my
                        |ye[ah|es]* # Match variations on yeah/yes
                        |(n*o+)+
                        |\(
                        |^ # Match the start of a string
                    )
                    [,.;\s]* # Match any number of spaces/punctuation
                    (?:
                      (?:
                        (?:sincer|great) # Matching the start of sincere/great
                        (?:est|e(?:ly)?)? # Match the end of sincerest/sincere/sincerely
                        |so|very|[ms]uch
                      )
                    .?)* # Match any number of "sincerely", "greatest", "so" etc. with or without characters in between
                    \s* # Match any number of spaces
                    (sorry|apologi([zs]e|es)) # Match sorry/apologise/apologies,etc.
                    (?!\s*(?:{laugh_emojis}|to\s+hear\s+that)\s*)
                """,
            re.IGNORECASE | re.VERBOSE | re.UNICODE,
        )
        self.love = re.compile(rf"(?:I )?love( you,?)? {self_id}", re.IGNORECASE)
        self.hug = re.compile(
            rf"Hugs? {self_id}|Gives {self_id} a?\s?hugs?", re.IGNORECASE
        )
        self.food = FoodLookups(self_id, config["food"])
        self.party = re.compile(
            rf"(?<!third)(?<!3rd)(?<!wrong)(?:^|\s)(?P<partyword>part(?:a*y|ies)(?P<punctuation>!+|\?+|$)|WOOT WOOT!?)\s?",
            re.IGNORECASE,
        )
        self.patterns = PatternReactions(config["pattern_reactions"])
        self.triggers = trigger_dict
        self.at_triggers = at_trigger_dict
        self.convert_time = re.compile(
            r"(?:^|[\s\-–—])(?P<time>(?P<hours>[0-2]?[0-9])(?P<minutes>:\d\d)?\s?(?P<am_pm>AM|PM)?(?:\s?\+\d\d?(?::\d\d)?(?::\d\d)?)?)",
            re.IGNORECASE,
        )

    def replace_bot_name(self, pattern: str) -> str:
        return self.bot_name.sub("{bot_name}", pattern)


def replace_bot_id(pattern: str, bot_id: str) -> str:
    return pattern.replace("{bot_id}", bot_id)
