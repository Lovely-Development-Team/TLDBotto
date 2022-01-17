import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import aiohttp

from botto.errors import ClickupError

log = logging.getLogger(__name__)


class ClickUpClient:
    def __init__(self, clickup_token: str):
        super().__init__()
        self._clickup_token = clickup_token
        self._url = "https://api.clickup.com/api/v2"
        self._auth_header = {"Authorization": f"{self._clickup_token}"}

    async def get_task(self, task_id) -> Optional["ClickupTask"]:
        async with aiohttp.ClientSession() as session:
            url = f"{self._url}/task/{task_id}"
            response = await session.get(url, headers=self._auth_header)
            json = await response.json()
            if response.ok:
                return ClickupTask.from_json(json)
            elif response.status == 404:
                return None
            else:
                raise ClickupError(url, json)


@dataclass
class ClickupStatus:
    name: str
    colour: str

    @classmethod
    def from_json(cls, data: dict) -> "ClickupStatus":
        return cls(name=data.get("status"), colour=data.get("color"))


@dataclass
class ClickupTask:
    id: str
    name: str
    description: Optional[str]
    status: ClickupStatus
    date_created: Optional[datetime]
    date_updated: Optional[datetime]
    date_closed: Optional[datetime]
    creator_name: str
    tags: list[dict]
    priority: Optional[str]
    url: str

    @classmethod
    def from_json(cls, data: dict) -> "ClickupTask":
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            status=ClickupStatus.from_json(data["status"]),
            date_created=datetime.fromtimestamp(int(data["date_created"]) / 1000)
            if data["date_created"]
            else None,
            date_updated=datetime.fromtimestamp(int(data["date_updated"]) / 1000)
            if data["date_updated"]
            else None,
            date_closed=datetime.fromtimestamp(int(data["date_closed"]) / 1000)
            if data["date_closed"]
            else None,
            creator_name=data["creator"].get("username"),
            tags=data.get("tags", []),
            priority=data["priority"].get("priority") if data.get("priority") else None,
            url=data.get("url"),
        )
