import asyncio
import logging
from enum import Enum, auto
from functools import partial
from typing import Optional, Union, AsyncGenerator, Iterable

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
    RequestStatus,
)

log = logging.getLogger(__name__)

ConfigCache = dict[str, dict[str, dict[str, ReactionRole]]]


class RequestApprovalFilter(Enum):
    ALL = auto()
    APPROVED = auto()
    UNAPPROVED = auto()


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
        log.debug("Listing watched message IDs")
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
        log.info(f"Watching {len(self.watched_message_ids)} messages")
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

    generate_fetch_tester_key = partial(hashkey, "tester_record_id")

    @cachedmethod(lambda self: self.cache, key=generate_fetch_tester_key)
    async def fetch_tester(self, record_id: str) -> Optional[Tester]:
        log.debug(f"Fetching tester with ID {record_id}")
        result = await self._get(self.testers_url + "/" + record_id)
        return Tester.from_airtable(result)

    async def find_tester(
        self, *, discord_id: Optional[str] = None, email: Optional[str] = None
    ) -> Optional[Tester]:
        log.debug(f"Finding tester with {discord_id=}, {email}")
        if not (discord_id or email):
            raise ValueError("At least one search parameter is required")
        try:
            formula = "AND("
            if discord_id:
                formula += f"{{Discord ID}}='{discord_id}'"
            if email:
                if discord_id:
                    formula += ","
                formula += f"{{Email}}='{email}'"
            formula += ")"
            result_iterator = self._iterate(self.testers_url, filter_by_formula=formula)
            tester_iterator = (Tester.from_airtable(x) async for x in result_iterator)
            try:
                return await anext(tester_iterator)
            except (StopIteration, StopAsyncIteration):
                log.info(f"No Tester found with ID {discord_id}")
                return None
        except AirTableError as e:
            if e.error_type == "NOT_FOUND":
                return None
            raise

    leave_message_ids_field = "fld4FRFQFuibIsgdm"

    async def find_tester_by_leave_message(
        self, message_id: str | int
    ) -> Optional[Tester]:
        log.debug(f"Finding tester for Leave Message ID {message_id}")
        try:
            formula = f"SEARCH('{message_id}', {{{self.leave_message_ids_field}}})"
            result_iterator = self._iterate(self.testers_url, filter_by_formula=formula)
            tester_iterator = (Tester.from_airtable(x) async for x in result_iterator)
            return await anext(tester_iterator, None)
        except AirTableError as e:
            if e.error_type == "NOT_FOUND":
                return None
            raise

    def url_for_tester(self, tester: Tester) -> str:
        if tester.id is None:
            raise MissingRecordIDError(tester)
        return "https://airtable.com/{base}/tblVndkqCyp1dZShG/{record_id}".format(
            base=self.airtable_base, record_id=tester.id
        )

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
        modified_tester = next(
            Tester.from_airtable(data)
            for data in result["records"]
            if data["fields"]["Discord ID"] == tester.discord_id
        )
        self.cache[self.generate_fetch_tester_key(self, modified_tester.id)] = (
            modified_tester
        )
        return modified_tester

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

    async def update_requests(
        self, requests: list[TestingRequest]
    ) -> list[TestingRequest]:
        if any(request.id is None for request in requests):
            raise MissingRecordIDError([request.id is None for request in requests][0])
        log.debug(f"Updating requests: {requests}")
        result = await self._update(
            self.testing_requests_url,
            {"records": [request.to_airtable() for request in requests]},
        )
        return [
            TestingRequest.from_airtable(updated_record)
            for updated_record in result["records"]
        ]

    def list_requests(
        self,
        tester_id: Union[str, int],
        app_ids: Optional[Iterable[Union[str, int]]] = None,
        approval_filter: RequestApprovalFilter = RequestApprovalFilter.ALL,
        exclude_removed: bool = False,
    ) -> AsyncGenerator[TestingRequest, None]:
        formula = f"AND({{Tester Discord ID}}={tester_id}"
        if app_ids:
            joined_app_ids = ",".join(
                [f"{{App Record ID}}='{app_id}'" for app_id in app_ids]
            )
            formula += f",OR({joined_app_ids})"
        match approval_filter:
            case RequestApprovalFilter.UNAPPROVED:
                formula += f",OR({{Approved}}=FALSE(),{{Status}}=BLANK())"
            case RequestApprovalFilter.APPROVED:
                formula += f",OR({{Approved}}=TRUE(),{{Status}}='{RequestStatus.APPROVED.value}')"
        if exclude_removed:
            formula += f",{{Removed}}=FALSE()"
        formula += ")"
        result_iterator = self._iterate(
            self.testing_requests_url,
            filter_by_formula=formula,
            sort=["Created"],
        )
        # PyCharm complains that the return type is actually a `Generator` not an `AsyncGenerator`. PyCharm is wrong.
        # noinspection PyTypeChecker
        return (TestingRequest.from_airtable(x) async for x in result_iterator)

    notification_message_id_field = "fldz3nfv1dougxSd4"

    async def _fetch_requests_by_further_message_id(
        self, *message_ids: Union[str, int]
    ) -> Optional[TestingRequest]:
        joined_message_ids = ",".join(
            [
                f"SEARCH('{message_id}', {{Further Notification Message IDs}})"
                for message_id in message_ids
            ]
        )
        formula = f"OR({joined_message_ids})"
        log.debug(f"Fetching request by further message ID: {message_ids}")
        log.debug(f"Formula: {formula}")
        result_iterator = self._iterate(
            self.testing_requests_url,
            filter_by_formula=formula,
        )
        try:
            return await (
                TestingRequest.from_airtable(x) async for x in result_iterator
            ).__anext__()
        except StopAsyncIteration:
            return None

    async def _fetch_request_by_original_message_id(
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

    async def fetch_request(
        self, message_id: Union[str, int]
    ) -> Optional[TestingRequest]:
        if original_request := await self._fetch_request_by_original_message_id(
            message_id
        ):
            return original_request
        elif further_request := await self._fetch_requests_by_further_message_id(
            message_id
        ):
            return further_request

    def url_for_request(self, request: TestingRequest) -> str:
        if request.id is None:
            raise MissingRecordIDError(request)
        return (
            "https://airtable.com/{base}/tblvxW011j0EZLsCq/{view}/{record_id}".format(
                base=self.airtable_base, view="viwbNCOpxGDB9O9ue", record_id=request.id
            )
        )

    async def list_approvals_channel_ids(self) -> list[str]:
        log.debug("Listing approval channel IDs")
        async with self.approval_channels_lock:
            apps_iterator = self._iterate(
                self.apps_url,
                filter_by_formula="{Approval Channel}",
                fields="Approval Channel",
            )
            approval_channel_entries = [
                reaction_role["fields"]["Approval Channel"]
                async for reaction_role in apps_iterator
                if reaction_role["fields"].get("Approval Channel")
            ]
            self.approvals_channel_ids = set(approval_channel_entries)
        return approval_channel_entries

    async def get_reaction_role(
        self, server_id: str, msg_id: str, key: str
    ) -> Optional[ReactionRole]:
        async with self.reaction_roles_lock:
            try:
                if (
                    (server_config := self.reaction_roles_cache.get(str(server_id)))
                    and (msg_config := server_config.get(str(msg_id)))
                    and (config := msg_config.get(key))
                ):
                    return config
                else:
                    return await self._fetch_reaction(server_id, msg_id, key)
            except KeyError as err:
                log.error(
                    f"Failed to get reaction role for {server_id}/{msg_id}/{key} due to decoding error: {err}"
                )
                return None

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
