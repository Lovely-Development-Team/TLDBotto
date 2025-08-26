from datetime import datetime, UTC
from decimal import Decimal
from typing import Optional, TypedDict

from botto.storage.models.user import DiscordUser
from botto.storage.mongo_storage import MongoStorage
from pymongo.asynchronous.collection import AsyncCollection
from bson.decimal128 import Decimal128
from bson import ObjectId


class EnablementStorage(MongoStorage):
    def __init__(self, username: str, password: str, host: str):
        super().__init__(username, password, host)
        self.database = self.client.get_database("general")
        self.collection: AsyncCollection = self.database.get_collection("enablements")

    async def add(
        self,
        name: str,
        enabled: DiscordUser,
        enabled_by: DiscordUser,
        message_link: str,
        amount: Optional[Decimal],
    ):
        Enablement = TypedDict(
            "Enablement",
            {
                "name": str,
                "enablee": ObjectId,
                "enabler": ObjectId,
                "date": datetime,
                "message_link": str,
                "amount": Decimal128,
            },
            total=False,
        )
        enablement_data = Enablement(
            name=name,
            enablee=enabled["_id"],
            enabler=enabled_by["_id"],
            date=datetime.now(UTC),
            message_link=message_link,
        )
        if amount := amount:
            enablement_data["amount"] = Decimal128(amount)
        await self.collection.insert_one(enablement_data)
