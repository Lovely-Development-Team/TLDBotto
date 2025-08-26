import logging

from pymongo import AsyncMongoClient


logging.getLogger("pymongo.command").setLevel(logging.DEBUG)
logging.getLogger("pymongo.topology").setLevel(logging.INFO)
logging.getLogger("pymongo.connection").setLevel(logging.INFO)


class MongoStorage:
    client: AsyncMongoClient

    def __init__(self, username: str, password: str, host: str):
        self.client = AsyncMongoClient(
            f"mongodb+srv://{username}:{password}@{host}/?retryWrites=true&w=majority&appName=Tildy",
            uuidRepresentation="standard",
            tz_aware=True,
        )
