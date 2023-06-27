from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import aiohttp
import arrow
import jwt

from botto.storage.beta_testers.model import (
    App,
    BetaGroupNotSetError,
    ApiKeyNotSetError,
)


@dataclass
class ApiKey:
    iss: str
    kid: str
    secret: str


class AppStoreConnectClient:
    def __init__(self, config: dict[str, dict[str, str]]):
        self.config = {}
        for key, value in config.items():
            self.config[key] = ApiKey(
                iss=value["iss"], kid=value["kid"], secret=value["secret"]
            )
        super().__init__()

    def create_token(self, key_id: str) -> str:
        api_key = self.config[key_id]
        now = arrow.utcnow()
        expiration = now.shift(minutes=20)
        return jwt.encode(
            payload={
                "iss": api_key.iss,
                "iat": now.int_timestamp,
                "exp": expiration.int_timestamp,
                "aud": "appstoreconnect-v1",
            },
            key=api_key.secret,
            headers={"alg": "ES256", "kid": api_key.kid, "typ": "JWT"},
        )

    def make_auth_header(self, key_id) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.create_token(key_id)}"}

    async def create_beta_tester(
        self, app: App, email: str, first_name: Optional[str], last_name: Optional[str]
    ):
        if app.beta_group_id is None:
            raise BetaGroupNotSetError(app)
        if app.app_store_key_id is None:
            raise ApiKeyNotSetError(app)
        tester_attributes = {"email": email}
        if first_name := first_name:
            tester_attributes["firstName"] = first_name
        if last_name := last_name:
            tester_attributes["lastName"] = last_name
        relationships = {
            "betaGroups": {"data": [{"id": app.beta_group_id, "type": "betaGroups"}]}
        }
        async with aiohttp.ClientSession() as session:
            await session.post(
                "https://api.appstoreconnect.apple.com/v1/betaTesters",
                json={
                    "data": {
                        "attributes": tester_attributes,
                        "relationships": relationships,
                        "type": "betaTesters",
                    }
                },
                headers=self.make_auth_header(app.app_store_key_id),
                raise_for_status=True,
            )
