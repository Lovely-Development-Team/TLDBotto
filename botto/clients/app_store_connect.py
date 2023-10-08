import logging
from dataclasses import dataclass
from typing import Optional, Literal

import aiohttp
import arrow
import jwt
from aiohttp import ClientResponseError

from botto.storage.beta_testers.model import (
    App,
    BetaGroupNotSetError,
    ApiKeyNotSetError,
    ConfigError,
    InvalidAttributeError,
)

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


@dataclass
class ApiKey:
    iss: str
    kid: str
    secret: str


@dataclass(frozen=True, slots=True)
class BetaTester:
    id: str
    email: str
    first_name: str
    last_name: Optional[str]
    invite_type: Literal["EMAIL", "PUBLIC_LINK"]
    beta_group_ids: list[str]


class AppStoreConnectClient:
    def __init__(self, config: dict[str, dict[str, str]]):
        self.config = {}
        for key, value in config.items():
            self.config[key] = ApiKey(
                iss=value["iss"], kid=value["kid"], secret=value["secret"]
            )
        super().__init__()

    def create_token(self, key_id: str) -> str:
        try:
            api_key = self.config[key_id]
        except KeyError as e:
            raise ConfigError(f"Api Key {key_id} not found in config") from e
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

    async def find_beta_tester(
        self, email: str, app: Optional[App] = None
    ) -> list[BetaTester]:
        async def run_command(key_id):
            async with aiohttp.ClientSession() as session:
                response = await session.get(
                    "https://api.appstoreconnect.apple.com/v1/betaTesters",
                    params={
                        "filter[email]": email,
                        "fields[betaTesters]": "betaGroups,email,firstName,lastName",
                    },
                    headers=self.make_auth_header(key_id),
                    raise_for_status=True,
                )
                json = await response.json()
                testers = []
                if data := json.get("data"):
                    for tester in data:
                        attributes = tester.get("attributes", {})
                        relationships = tester.get("relationships", {})
                        beta_groups_link = (
                            relationships.get("betaGroups", {})
                            .get("links", {})
                            .get("self")
                        )
                        ids_response = await (
                            await session.get(
                                beta_groups_link,
                                headers=self.make_auth_header(key_id),
                                raise_for_status=True,
                            )
                        ).json()
                        beta_groups = [
                            group["id"]
                            for group in ids_response.get("data", [])
                            if group.get("id") is not None
                        ]
                        testers.append(
                            BetaTester(
                                id=tester["id"],
                                email=attributes.get("email"),
                                first_name=attributes.get("firstName"),
                                last_name=attributes.get("lastName"),
                                invite_type=attributes.get("inviteType"),
                                beta_group_ids=beta_groups,
                            )
                        )
                return testers

        testers = []
        if app := app:
            app_testers = await run_command(app.app_store_key_id)
            testers.extend(app_testers)
        else:
            for key in self.config.keys():
                app_testers = await run_command(key)
                testers.extend(app_testers)
        return testers

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
            data = {
                "attributes": tester_attributes,
                "relationships": relationships,
                "type": "betaTesters",
            }
            response = await session.post(
                "https://api.appstoreconnect.apple.com/v1/betaTesters",
                json={"data": data},
                headers=self.make_auth_header(app.app_store_key_id),
            )
            response_body: dict = await response.json()
            try:
                response.raise_for_status()
            except ClientResponseError:
                log.error(
                    f"Unable to create beta tester with data {data}. Response: {response_body}",
                )
                if errors := response_body.get("errors"):
                    invalid_attribute_details = [
                        error["detail"]
                        for error in errors
                        if error.get("code") == "ENTITY_ERROR.ATTRIBUTE.INVALID"
                        and error.get("detail") is not None
                    ]
                    raise InvalidAttributeError(invalid_attribute_details)
                raise
