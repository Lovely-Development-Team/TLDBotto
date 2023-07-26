import asyncio
import logging
from functools import partial
from typing import Optional, Union, AsyncGenerator

from cachetools import TTLCache
from cachetools.keys import hashkey
from asyncache import cachedmethod

from botto.models import AirTableError
from botto.storage.storage import Storage
from botto.storage.beta_testers.model import (
    ReactionRole,
    Tester,
    TestingRequest,
    MissingRecordIDError,
    App,
)

log = logging.getLogger(__name__)

ConfigCache = dict[str, dict[str, dict[str, ReactionRole]]]


class BetaTestersStorage(Storage):
    def __init__(self, snailedit_airtable_base: str, snailedit_airtable_key: str):
        super().__init__(snailedit_airtable_base, snailedit_airtable_key)
        self.reactions_roles_config_url = (
            "https://api.airtable.com/v0/{base}/Reaction Roles".format(
                base=snailedit_airtable_base
            )
        )
        self.testers_url = "https://api.airtable.com/v0/{base}/Testers".format(
            base=snailedit_airtable_base
        )
        self.apps_url = "https://api.airtable.com/v0/{base}/Apps".format(
            base=snailedit_airtable_base
        )
        self.testing_requests_url = (
            "https://api.airtable.com/v0/{base}/tblvxW011j0EZLsCq".format(
                base=snailedit_airtable_base
            )
        )
        self.reaction_roles_lock = asyncio.Lock()
        self.reaction_roles_cache: ConfigCache = {}
        self.watched_message_ids: set[str] = set()
        self.approval_channels_lock = asyncio.Lock()
        self.approvals_channel_ids: set[str] = set()
        self.auth_header = {"Authorization": f"Bearer {self.airtable_key}"}
        self.cache = TTLCache(maxsize=20, ttl=60 * 60)

    async def list_watched_message_ids(self) -> list[str]:
        async with self.reaction_roles_lock:
            reaction_roles_iterator = self._iterate(
                self.reactions_roles_config_url,
                filter_by_formula=None,
                fields="Message ID",
            )
            reaction_role_entries = [
                reaction_role["fields"]["Message ID"]
                async for reaction_role in reaction_roles_iterator
            ]
            self.watched_message_ids = set(reaction_role_entries)
        return reaction_role_entries

    async def list_reaction_roles(self) -> list[ReactionRole]:
        async with self.reaction_roles_lock:
            reaction_roles_iterator = self._iterate(
                self.reactions_roles_config_url, filter_by_formula=None
            )
            reaction_role_entries = [
                ReactionRole.from_airtable(x) async for x in reaction_roles_iterator
            ]
            for config in reaction_role_entries:
                server_config = self.reaction_roles_cache.get(config.server_id)
                if server_config is None:
                    server_config = {}
                    self.reaction_roles_cache[config.server_id] = server_config
                message_config = server_config.get(config.message_id, {})
                message_config[config.reaction_name] = config
                server_config[config.message_id] = message_config
                self.watched_message_ids.add(config.message_id)
        return reaction_role_entries

    async def list_reaction_roles_by_server(self) -> ConfigCache:
        await self.list_reaction_roles()
        return self.reaction_roles_cache

    @cachedmethod(lambda self: self.cache, key=partial(hashkey, "tester_record_id"))
    async def fetch_tester(self, record_id: str) -> Optional[Tester]:
        log.debug(f"Fetching tester with ID {record_id}")
        result = await self._get(self.testers_url + "/" + record_id)
        return Tester.from_airtable(result)

    async def find_tester(self, discord_id: str) -> Optional[Tester]:
        log.debug(f"Finding tester with ID {discord_id}")
        try:
            result_iterator = self._iterate(
                self.testers_url, filter_by_formula=f"{{Discord ID}}='{discord_id}'"
            )
            tester_iterator = (Tester.from_airtable(x) async for x in result_iterator)
            try:
                return await tester_iterator.__anext__()
            except (StopIteration, StopAsyncIteration):
                log.info(f"No Tester found with ID {discord_id}")
                return None
        except AirTableError as e:
            if e.error_type == "NOT_FOUND":
                return None
            raise

    async def _fetch_reaction(
        self, server_id: str, msg_id, reaction_name: str
    ) -> Optional[ReactionRole]:
        log.debug(f"Fetching role mapping for {reaction_name} in {server_id}")
        try:
            result_iterator = self._iterate(
                self.reactions_roles_config_url,
                filter_by_formula=f"AND({{Server ID}}='{server_id}',{{Message ID}}='{msg_id}',"
                f"{{Reaction}}='{reaction_name}')",
            )
            roles_iterator = (
                ReactionRole.from_airtable(x) async for x in result_iterator
            )
            try:
                reaction_role = await roles_iterator.__anext__()
            except (StopIteration, StopAsyncIteration):
                log.info(
                    f"No Role found for Server '{server_id}' on message '{msg_id}' with name '{reaction_name}'"
                )
                return None
            server_config = self.reaction_roles_cache.get(server_id)
            if server_config is None:
                server_config = {}
                self.reaction_roles_cache[server_id] = server_config
            message_config = server_config.get(msg_id, {})
            message_config[reaction_name] = reaction_role
            server_config[msg_id] = message_config
            self.watched_message_ids.add(msg_id)
            return reaction_role
        except AirTableError as e:
            if e.error_type == "NOT_FOUND":
                return None
            raise

    async def upsert_tester(self, tester: Tester) -> Tester:
        result = await self._update(
            self.testers_url, tester.to_airtable(), upsert_fields=["Discord ID"]
        )
        return next(
            Tester.from_airtable(data)
            for data in result["records"]
            if data["fields"]["Discord ID"] == tester.discord_id
        )

    async def add_request(self, request: TestingRequest) -> TestingRequest:
        return TestingRequest.from_airtable(
            await self._insert(self.testing_requests_url, request.to_airtable())
        )

    async def update_request(self, request: TestingRequest) -> Optional[TestingRequest]:
        if request.id is None:
            raise MissingRecordIDError(request)
        log.debug(f"Updating request: {request}")
        result = await self._update(
            self.testing_requests_url,
            request.to_airtable(),
        )
        return TestingRequest.from_airtable(result)

    def list_requests(
        self, tester_id: Union[str, int], exclude_approved: bool = False
    ) -> AsyncGenerator[TestingRequest, None]:
        tester_id_condition = f"{{Tester Discord ID}}={tester_id}"
        if exclude_approved:
            formula = f"AND({tester_id_condition},{{Approved}}=FALSE())"
        else:
            formula = tester_id_condition
        result_iterator = self._iterate(
            self.testing_requests_url,
            filter_by_formula=formula,
        )
        # PyCharm complains that the return type is actually a `Generator` not an `AsyncGenerator`. PyCharm is wrong.
        # noinspection PyTypeChecker
        return (TestingRequest.from_airtable(x) async for x in result_iterator)

    notification_message_id_field = "fldz3nfv1dougxSd4"

    async def fetch_request(
        self, message_id: Union[str, int]
    ) -> Optional[TestingRequest]:
        result_iterator = self._iterate(
            self.testing_requests_url,
            filter_by_formula=f"{{{self.notification_message_id_field}}}={message_id}",
        )
        try:
            return await (
                TestingRequest.from_airtable(x) async for x in result_iterator
            ).__anext__()
        except StopAsyncIteration:
            return None

    def url_for_request(self, request: TestingRequest) -> str:
        if request.id is None:
            raise MissingRecordIDError(request)
        return (
            "https://airtable.com/{base}/tblvxW011j0EZLsCq/{view}/{record_id}".format(
                base=self.airtable_base, view="viwbNCOpxGDB9O9ue", record_id=request.id
            )
        )

    async def list_approvals_channel_ids(self) -> list[str]:
        async with self.approval_channels_lock:
            reaction_roles_iterator = self._iterate(
                self.testing_requests_url,
                filter_by_formula="{Approval Channel}",
                fields="Approval Channel",
            )
            approval_channel_entries = [
                reaction_role["fields"]["Approval Channel"]
                async for reaction_role in reaction_roles_iterator
                if reaction_role["fields"].get("Approval Channel")
            ]
            self.approvals_channel_ids = set(approval_channel_entries)
        return approval_channel_entries

    async def get_reaction_role(
        self, server_id: str, msg_id: str, key: str
    ) -> Optional[ReactionRole]:
        async with self.reaction_roles_lock:
            if (
                (server_config := self.reaction_roles_cache.get(str(server_id)))
                and (msg_config := server_config.get(str(msg_id)))
                and (config := msg_config.get(key))
            ):
                return config
            else:
                return await self._fetch_reaction(server_id, msg_id, key)

    @cachedmethod(lambda self: self.cache, key=partial(hashkey, "app"))
    async def fetch_app(self, record_id: str) -> Optional[App]:
        log.debug(f"Fetching app with ID {record_id}")
        result = await self._get(self.apps_url + "/" + record_id)
        return App.from_airtable(result)

    @cachedmethod(lambda self: self.cache, key=partial(hashkey, "app_beta_groups"))
    async def find_apps_by_beta_group(self, *group_ids: str) -> list[App]:
        log.debug(f"Finding apps for Beta Group IDs {group_ids}")
        joined_beta_groups = ",".join(
            [f"{{Beta Group ID}}='{group_id}'" for group_id in group_ids]
        )
        formula = f"OR({joined_beta_groups})"
        apps_iterator = self._iterate(
            self.apps_url,
            filter_by_formula=formula,
        )
        return [App.from_airtable(app_data) async for app_data in apps_iterator]
