import asyncio
import logging

import aiohttp
from appstoreserverlibrary.models.JWSTransactionDecodedPayload import (
    JWSTransactionDecodedPayload,
)
from appstoreserverlibrary.models.OrderLookupStatus import OrderLookupStatus

from appstoreserverlibrary.api_client import AppStoreServerAPIClient, APIException
from appstoreserverlibrary.models.Environment import Environment
from appstoreserverlibrary.signed_data_verifier import (
    VerificationException,
    SignedDataVerifier,
)

from botto.storage.beta_testers.model import App

log = logging.getLogger(__name__)

APPLE_ROOT_CERT_URLS = [
    "https://www.apple.com/appleca/AppleIncRootCertificate.cer",
    "https://www.apple.com/certificateauthority/AppleComputerRootCertificate.cer",
    "https://www.apple.com/certificateauthority/AppleRootCA-G2.cer",
    "https://www.apple.com/certificateauthority/AppleRootCA-G3.cer",
]


class AppStoreServerClient:
    def __init__(self, config: dict[str, dict[str, str]]):
        self.api_clients: dict[str, AppStoreServerAPIClient] = {}
        self.apple_root_certs: list[bytes] = []
        self.data_verifiers: dict[str, SignedDataVerifier] = {}
        self.config = config
        super().__init__()

    def get_api_client(self, app: App) -> AppStoreServerAPIClient:
        key_id = app.app_store_server_key_id
        if key_id not in self.api_clients:
            self.api_clients[key_id] = AppStoreServerAPIClient(
                str.encode(self.config[key_id]["secret"]),
                self.config[key_id]["kid"],
                self.config[key_id]["iss"],
                app.bundle_id,
                Environment.PRODUCTION,
            )
        return self.api_clients[key_id]

    async def download_cert(self, url: str) -> bytes:
        async with aiohttp.ClientSession() as session:
            response = await session.get(url, raise_for_status=True)
            return await response.read()

    async def download_apple_root_certs(self) -> list[bytes]:
        download_tasks: list[asyncio.Task[bytes]]
        async with asyncio.TaskGroup() as g:
            download_tasks = [
                g.create_task(self.download_cert(url)) for url in APPLE_ROOT_CERT_URLS
            ]
        return [await task for task in download_tasks]

    async def get_sign_data_verifier(self, app: App) -> SignedDataVerifier:
        key_id = app.app_store_server_key_id
        if not self.apple_root_certs:
            self.apple_root_certs = await self.download_apple_root_certs()
        if key_id not in self.data_verifiers:
            self.data_verifiers[key_id] = SignedDataVerifier(
                self.apple_root_certs,
                True,
                Environment.PRODUCTION,
                app.bundle_id,
                app.apple_id,
            )
        return self.data_verifiers[key_id]

    async def lookup_order_id(
        self, app: App, order_id: str
    ) -> list[JWSTransactionDecodedPayload]:
        log.info(f"Looking up order ID {order_id} for app {app.bundle_id}")
        api_client = self.get_api_client(app)
        try:
            response = await asyncio.to_thread(api_client.look_up_order_id, order_id)
            if response.status == OrderLookupStatus.INVALID:
                raise OrderIdInvalidError(order_id)
            data_verifier = await self.get_sign_data_verifier(app)
            decoded_transactions = [
                data_verifier.verify_and_decode_signed_transaction(t)
                for t in response.signedTransactions
            ]
            return decoded_transactions
        except (APIException, VerificationException) as e:
            raise OrderLookupError(
                f"Error looking up order ID {order_id} for app {app.bundle_id}"
            ) from e


class OrderLookupError(Exception):
    pass


class OrderIdInvalidError(OrderLookupError):
    def __init__(self, order_id: str):
        self.order_id = order_id
        super().__init__(f"Order ID {order_id} is invalid")
