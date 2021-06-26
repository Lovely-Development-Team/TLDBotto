import re
from dataclasses import dataclass
from re import Pattern
from typing import Optional

from food import FoodLookups


class PatternReactions:
    def __init__(self, pattern_reactions: dict) -> None:
        self.reaction_map = pattern_reactions
        super().__init__()

    def matches(self, text: str) -> Optional[str]:
        for key, value in self.reaction_map.items():
            if value["trigger"].search(text):
                return key


@dataclass
class SuggestionRegexes:
    at_command: [Pattern]
    pokes: Pattern
    sorry: Pattern
    apologising: Pattern
    off_topic: Pattern
    love: Pattern
    hug: Pattern
    food: FoodLookups
    band: Pattern
    party: Pattern
    complaint: Pattern
    patterns: PatternReactions
    triggers: dict[str, list[Pattern]]
    at_triggers: dict[str, list[Pattern]]


laugh_emojis = "[😆😂🤣]"


def compile_triggers(self_id: str, trigger_dict: dict) -> dict:
    for name, triggers in trigger_dict.items():
        trigger_dict[name] = [
            re.compile(
                "^{trigger}".format(trigger=trigger.replace("{bot_id}", self_id)),
                re.IGNORECASE,
            )
            for trigger in triggers
        ]
    return trigger_dict


def compile_regexes(bot_user_id: str, config: dict) -> SuggestionRegexes:
    self_id = rf"<@!?{bot_user_id}>"

    # Compile trigger regexes
    trigger_dict = compile_triggers(self_id, config["triggers"])
    at_trigger_dict = compile_triggers(self_id, config["at_triggers"])

    regexes = SuggestionRegexes(
        at_command=[re.compile(rf"^{self_id}(?P<command>.*)")],
        pokes=re.compile(rf"pokes? {self_id}", re.IGNORECASE),
        sorry=re.compile(rf"sorry,? {self_id}", re.IGNORECASE),
        apologising=re.compile(
            rf"""
            (?:
                I['"’m]+ #Match I/I'm
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
        ),
        off_topic=re.compile(rf"off( +|\-)topic", re.IGNORECASE),
        love=re.compile(rf"(?:I )?love( you,?)? {self_id}", re.IGNORECASE),
        hug=re.compile(rf"Hugs? {self_id}|Gives {self_id} a?\s?hugs?", re.IGNORECASE),
        food=FoodLookups(self_id, config["food"]),
        band=re.compile(
            rf"What('|’)?s +your +fav(ou?rite)? +band +{self_id} ?\?*", re.IGNORECASE
        ),
        party=re.compile(
            rf"(?<!third)(?<!3rd)(?:^|\s)(?P<partyword>part(?:a*y|ies))", re.IGNORECASE
        ),
        complaint=re.compile(
            r"(?:BOTTO.?\s+COME\.?\s+ON\s*|COME\.?\s+ON\s+BOTTO.?\s*)"
        ),
        patterns=PatternReactions(config["pattern_reactions"]),
        triggers=trigger_dict,
        at_triggers=at_trigger_dict,
    )
    return regexes
