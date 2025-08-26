from dataclasses import dataclass
from datetime import datetime

from bson import ObjectId

from botto.models import Intro, Meal


@dataclass
class MongoBaseMeal:
    _id: ObjectId
    name: str
    texts: list[str]


class MongoInto(MongoBaseMeal, Intro):

    @property
    def messages(self):
        return self.texts

    @classmethod
    def from_mongo(cls, data: dict) -> "MongoInto":
        return cls(
            _id=data.get("_id"),
            name=data.get("name"),
            texts=data.get("messages"),
        )


class MongoMeal(MongoBaseMeal, Meal):

    @property
    def messages(self):
        return self.texts

    @classmethod
    def from_mongo(cls, data: dict) -> "MongoMeal":
        start_time = data.get("start_time")
        end_time = data.get("end_time")

        return cls(
            _id=data.get("_id"),
            name=data.get("name"),
            start=datetime.strptime(start_time, "%H:%M").time() if start_time else None,
            end=datetime.strptime(end_time, "%H:%M").time() if end_time else None,
            emoji=data.get("emoji"),
            texts=data.get("messages"),
        )
