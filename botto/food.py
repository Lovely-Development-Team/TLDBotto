import enum
import logging
import re
from enum import Enum

from emoji import UNICODE_EMOJI

log = logging.getLogger("TLDBotto").getChild("food")
log.setLevel(logging.INFO)

default_config = {
    "standard": {
        "triggers": [
            "🍇",
            "🍈",
            "🍉",
            "🍊",
            "🍌",
            "🍍",
            "🥭",
            "🍎",
            "🍏",
            "🍐",
            "🍒",
            "🍓",
            "🫐",
            "🥝",
            "🍅",
            "🫒",
            "🥥",
            "🥑",
            "🥔",
            "🌽",
            "🥜",
            "🌰",
            "🍞",
            "🥐",
            "🥖",
            "🫓",
            "🥨",
            "🥯",
            "🧇",
            "🍖",
            "🍗",
            "🥓",
            "🍔",
            "🍕",
            "🌭",
            "🍟",
            "🥪",
            "🌮",
            "🌯",
            "🫔",
            "🧆",
            "🍳",
            "🍿",
            "🧈",
            "🍘",
            "🍙",
            "🍠",
            "🍢",
            "🥮",
            "🍡",
            "🥟",
            "🥠",
            "🦪",
            "🍩",
            "🍪",
            "🍰",
            "🧁",
            "🍬",
            "🍭",
            "🍼",
            "🥛",
            "☕",
            "🍵",
            "🥤",
            "🧋",
            "🧃",
            "🧉",
        ],
        "responses": ["😋", "echo"],
    },
    "chocolate": {"triggers": "🍫", "responses": ["😋", "🍫", "💜"]},
    "rose": {"triggers": "🌹", "responses": ["🍫"]},
    "alcohol": {
        "triggers": ["🍶", "🍾", "🍷", "🍸", "🍹", "🍺", "🍻", "🥂", "🥃"],
        "responses": ["echo", "🥴"],
    },
    "teapot": {"triggers": "🫖", "responses": ["😋", "☕"]},
    "cutlery_foods": {
        "triggers": ["🥘", "🫕", "🥗", "🍝", "🥧", "🥙", "🥞", "🥩"],
        "responses": ["😋", "echo", "🍴"],
    },
    "chopstick_foods": {
        "triggers": ["🍲", "🍱", "🍚", "🍛", "🍜", "🍣", "🍤", "🍥", "🥡"],
        "responses": ["😋", "echo", "🥢"],
    },
    "spoon_foods": {
        "triggers": ["🥣", "🍧", "🍨", "🍮", "🍯"],
        "responses": ["😋", "echo", "🥄"],
    },
    "tongue_foods": {"triggers": "🍦", "responses": ["👅", "echo", "😋"]},
    "rabbit_food": {"triggers": ["🥬", "🥕"], "responses": ["🐰"]},
    "mouse_food": {"triggers": "🧀", "responses": ["🐭"]},
    "weird_foods": {
        "triggers": ["🍋", "🍆", "🍑", "🫑", "🥒", "🥦", "🧄", "🧅", "🍄", "🥚", "🧈"],
        "responses": ["😕"],
    },
    "eye_roll_foods": {"triggers": ["🍽️"], "responses": ["🙄"]},
    "dangerous_foods": {
        "triggers": ["💣", "🧨", "🗡️", "🔪", "🦠", "🧫"],
        "responses": ["🙅", "😨"],
    },
    "nausea": {"triggers": "🚬", "responses": ["🙅", "🤢"]},
    "vomit": {
        "triggers": ["🐛", "🐜", "🪲", "🦟", "🐞", "🦗", "🪰"],
        "responses": ["🤢", "🤮", "😭"],
    },
    "bee": {"triggers": "🐝", "responses": ["🙅", "echo", "🌻", "👉", "🍯", "😊"]},
    "baby": {"triggers": "👶", "responses": ["🙅", "😢"]},
    "alien": {"triggers": "🛸", "responses": ["👽"]},
    "zombie": {"triggers": "🧠", "responses": ["🧟"]},
    "vampire": {"triggers": ["🩸", "🆎", "🅱️", "🅾️", "🅰️"], "responses": ["🧛"]},
    "robot": {"triggers": ["⚙"], "responses": ["🤖"]},
    "nazar": {"triggers": ["🧿"], "responses": ["👀"]},
    "spicy": {"triggers": "🌶️", "responses": ["🥵"]},
    "ice": {"triggers": "🧊", "responses": ["🥶"]},
    "bone": {"triggers": "🦴", "responses": ["🐶"]},
    "celebrate": {"triggers": "🎂", "responses": ["😋", "party"]},
    "money": {"triggers": ["💸", "💰", "💵"], "responses": ["🤑"]},
    "gift": {"triggers": ["🎁", "💌"], "responses": ["echo", "🫂", "love"]},
}


class SpecialAction(Enum):
    echo = enum.auto()
    party = enum.auto()
    love = enum.auto()


def convert_response(response: str):
    if response == "echo" or response == "party" or response == "love":
        return SpecialAction[response]
    else:
        return response


class FoodLookups:
    def __init__(self, self_id: str, self_name: str, food_config: dict):
        self.lookup = {}
        for item in food_config.values():
            triggers = item["triggers"]
            responses = [convert_response(response) for response in item["responses"]]
            if type(triggers) is list:
                for emoji in triggers:
                    self.lookup.update({emoji: responses})
            else:
                self.lookup.update({triggers: responses})
        self.food_chars = "".join(self.lookup.keys())
        self.food_regex = re.compile(
            r"""(?:feed|pour|give)s?\s(?:{self_id}|{self_name})
                    .*?
                    ([{chars}])(?:\ufe0f)?""".format(
                self_id=self_id, self_name=self_name, chars=self.food_chars
            ),
            re.IGNORECASE | re.VERBOSE | re.UNICODE,
        )
        log.debug(f"Food regex: {self.food_regex}")
        self.not_food_regex = re.compile(
            r"""(?:feed|pour|give)s?\s(?:{self_id}|{self_name})
                    .*?
                    ([{chars}])""".format(
                self_id=self_id,
                self_name=self_name,
                chars="".join(UNICODE_EMOJI["en"].keys()),
            ),
            re.IGNORECASE | re.VERBOSE | re.UNICODE,
        )
        log.info(
            f"Loaded {len(self.lookup)} types of food in {len(food_config)} categories"
        )
