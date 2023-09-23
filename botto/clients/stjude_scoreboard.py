import logging
from typing import Literal, Optional

import aiohttp

log = logging.getLogger(__name__)


class StJudeScoreboardClient:
    def __init__(self, token: Optional[str]):
        super().__init__()
        self._url = "https://stjude-scoreboard.snailedit.org/api/co-founders"
        self._token = token

    async def update_score(self, co_founder: Literal["myke", "stephen"], score: int):
        async with aiohttp.ClientSession() as session:
            url = f"{self._url}/{co_founder}"
            headers = (
                {"Authorization": f"Bearer {self._token}"}
                if self._token is not None
                else None
            )
            await session.put(
                url, json={"score": score}, headers=headers, raise_for_status=True
            )
