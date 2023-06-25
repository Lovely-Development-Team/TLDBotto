import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Callable, Awaitable, Optional, Literal, Protocol, Union

import aiohttp
from aiohttp import ClientSession

from botto.models import AirTableError

log = logging.getLogger(__name__)


async def run_request(
    action_to_run: Callable[[ClientSession], Awaitable[dict]],
    session: Optional[ClientSession] = None,
):
    if not session:
        async with aiohttp.ClientSession() as new_session:
            return await action_to_run(new_session)
    else:
        return await action_to_run(session)


async def airtable_sleep():
    await asyncio.sleep(1.0 / 5)


class Storage:
    semaphore = asyncio.Semaphore(5)

    def __init__(
        self,
        airtable_base: str,
        airtable_key: str,
    ):
        self.airtable_base = airtable_base
        self.airtable_key = airtable_key
        self.auth_header = {"Authorization": f"Bearer {self.airtable_key}"}

    async def _get(
        self,
        url: str,
        params: Optional[dict[str, str]] = None,
        session: Optional[ClientSession] = None,
    ) -> dict:
        async def run_fetch(session_to_use: ClientSession):
            async with session_to_use.get(
                url,
                params=params,
                headers=self.auth_header,
            ) as r:
                if r.status != 200:
                    raise AirTableError(r.url, await r.json())
                motto_response: dict = await r.json()
                return motto_response

        async with self.semaphore:
            result = await run_request(run_fetch, session)
            await airtable_sleep()
            return result

    async def _iterate(
        self,
        base_url: str,
        *,
        filter_by_formula: Optional[str],
        sort: Optional[list[str]] = None,
        session: Optional[ClientSession] = None,
        fields: Optional[Union[list[str], str]] = None,
    ) -> AsyncGenerator[dict]:
        params = {}
        if filter_by_formula:
            params = {"filterByFormula": filter_by_formula}
        if sort:
            for idx, field in enumerate(sort):
                params.update({"sort[{index}][field]".format(index=idx): field})
                params.update({"sort[{index}][direction]".format(index=idx): "asc"})
        if fields:
            params.update({"fields[]": fields})
        offset = None
        while True:
            if offset:
                params.update(offset=offset)
            async with self.semaphore:
                response = await self._get(base_url, params, session)
                await airtable_sleep()
            records = response.get("records", [])
            for record in records:
                yield record
            offset = response.get("offset")
            if not offset:
                break

    async def _delete(
        self,
        base_url: str,
        records_to_delete: [str],
        session: Optional[ClientSession] = None,
    ):
        async def run_delete(session_to_use: ClientSession):
            async with session_to_use.delete(
                (
                    base_url
                    if len(records_to_delete) > 1
                    else base_url + f"/{records_to_delete[0]}"
                ),
                params=(
                    {"records": records_to_delete}
                    if len(records_to_delete) > 1
                    else None
                ),
                headers=self.auth_header,
            ) as r:
                if r.status != 200:
                    raise AirTableError(r.url, await r.json())

        async with self.semaphore:
            result = await run_request(run_delete, session)
            await airtable_sleep()
            return result

    async def _modify(
        self,
        url: str,
        method: Literal["post", "patch"],
        record: dict,
        upsert_fields: Optional[list[str]],
        session: Optional[ClientSession] = None,
    ):
        async def run_insert(session_to_use: ClientSession):
            is_single_record = "records" not in record
            has_fields = "fields" not in record
            data: dict[str, Union[str, dict, list]] = (
                {"fields": record} if is_single_record and has_fields else record
            )
            entity_url = url
            if upsert_fields is not None:
                if "records" not in record:
                    data["records"] = [data.copy()]
                    data.pop("fields")
                    if data.get("id"):
                        data.pop("id")
                data["performUpsert"] = {"fieldsToMergeOn": upsert_fields}
            elif is_single_record and (record_id := record.get("id")):
                entity_url += "/" + record_id
                record.pop("id")

            async with session_to_use.request(
                method,
                entity_url,
                json=data,
                headers=self.auth_header,
            ) as r:
                if r.status != 200:
                    raise AirTableError(r.url, await r.json(), data)
                response: dict = await r.json()
                return response

        async with self.semaphore:
            result = await run_request(run_insert, session)
            await airtable_sleep()
            return result

    async def _insert(
        self,
        url: str,
        record: dict,
        session: Optional[ClientSession] = None,
        upsert_fields: Optional[list[str]] = None,
    ) -> dict:
        return await self._modify(url, "post", record, upsert_fields, session)

    async def _update(
        self,
        url: str,
        record: dict,
        session: Optional[ClientSession] = None,
        upsert_fields: Optional[list[str]] = None,
    ) -> dict:
        return await self._modify(url, "patch", record, upsert_fields, session)
