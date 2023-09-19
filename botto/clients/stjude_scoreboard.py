import logging
from typing import Literal

import aiohttp

log = logging.getLogger(__name__)


class StJudeScoreboardClient:
    def __init__(self):
        super().__init__()
        self._url = "https://stjude-scoreboard.snailedit.org/api/co-founders"

    async def update_score(self, co_founder: Literal["myke", "stephen"], score: int):
        async with aiohttp.ClientSession() as session:
            url = f"{self._url}/{co_founder}"
            await session.put(url, json={"score": score}, raise_for_status=True)
