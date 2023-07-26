import logging
from dataclasses import dataclass
from typing import Optional

import arrow


@dataclass
class ReactionRole:
    id: str
    server_id: str
    message_id: str
    reaction_name: str
    role_id: str
    app_ids: list[str]

    @classmethod
    def from_airtable(cls, data: dict) -> "ReactionRole":
        fields = data["fields"]
        return cls(
            id=data["id"],
            server_id=fields["Server ID"],
            message_id=fields["Message ID"],
            reaction_name=fields["Reaction"],
            role_id=fields["Role"],
            app_ids=fields["Apps"],
        )


@dataclass
class Tester:
    username: str
    discord_id: str
    email: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    full_name: Optional[str] = None
    testing_requests: Optional[list[str]] = None
    id: Optional[str] = None
    registration_message_id: Optional[str] = None

    @classmethod
    def from_airtable(cls, data: dict) -> "Tester":
        fields = data["fields"]
        return cls(
            id=data["id"],
            username=fields["Username"],
            discord_id=fields["Discord ID"],
            email=fields.get("Email"),
            given_name=fields.get("Given Name"),
            family_name=fields.get("Family Name"),
            full_name=fields.get("Full Name"),
            testing_requests=fields.get("Testing Requests"),
            registration_message_id=fields.get("Registration Message ID"),
        )

    def to_airtable(self, fields=None) -> dict:
        fields = (
            fields
            if fields
            else [
                "username",
                "discord_id",
                "email",
                "given_name",
                "family_name",
                "testing_requests",
                "registration_message_id",
            ]
        )
        data = {}
        if "username" in fields:
            data["Username"] = self.username
        if "discord_id" in fields:
            data["Discord ID"] = self.discord_id
        if "email" in fields and self.email is not None:
            data["Email"] = self.email
        if "given_name" in fields and self.given_name is not None:
            data["Given Name"] = self.given_name
        if "family_name" in fields and self.family_name is not None:
            data["Family Name"] = self.family_name
        if "testing_requests" in fields and self.testing_requests is not None:
            data["Testing Requests"] = self.testing_requests
        if (
            "registration_message_id" in fields
            and self.registration_message_id is not None
        ):
            data["Registration Message ID"] = self.registration_message_id
        airtable_dict = {
            "fields": data,
        }
        if self.id:
            airtable_dict["id"] = self.id
        return airtable_dict


@dataclass
class TestingRequest:
    tester: str
    tester_discord_id: str
    app: str
    server_id: str
    app_name: Optional[str] = None  # Formula field
    _approved: Optional[bool] = None
    _notification_message_id: Optional[str] = None
    approval_channel_id: Optional[str] = None
    app_reaction_roles_ids: Optional[list[str]] = None
    created: Optional[arrow.Arrow] = None
    id: Optional[str] = None

    @property
    def approved(self) -> bool:
        return self._approved is True

    @approved.setter
    def approved(self, value: bool):
        self._approved = value

    @property
    def notification_message_id(self) -> Optional[str]:
        return self._notification_message_id

    @notification_message_id.setter
    def notification_message_id(self, value):
        self._notification_message_id = str(value)

    @classmethod
    def from_airtable(cls, data: dict) -> "TestingRequest":
        fields = data["fields"]
        try:
            tester: str = fields["Tester"][0]
        except IndexError:
            tester = fields["Tester"]
        try:
            tester_discord_id: str = fields["Tester Discord ID"][0]
        except IndexError:
            tester_discord_id = fields["Tester Discord ID"]
        try:
            app: str = fields["App"][0]
        except IndexError:
            app = fields["App"]
        try:
            app_name: str = fields["App Name"][0]
        except IndexError:
            app_name = fields["App Name"]
        try:
            created = arrow.get(fields["Created"])
        except arrow.ParserError:
            logging.error(
                f"Failed to parse 'Created' field from Airtable: {fields['Created']}",
                exc_info=True,
            )
            created = None
        return cls(
            id=data["id"],
            tester=tester,
            tester_discord_id=tester_discord_id,
            app=app,
            app_name=app_name,
            _approved=fields.get("Approved"),
            _notification_message_id=fields.get("Notification Message ID"),
            approval_channel_id=fields.get("Approval Channel"),
            app_reaction_roles_ids=fields.get("App Reaction Role IDs"),
            server_id=fields["Server ID"],
            created=created,
        )

    def to_airtable(self, fields=None) -> dict:
        fields = (
            fields
            if fields
            else [
                "tester",
                "app",
                "approved",
                "server_id",
                "notification_message_id",
                "app_reaction_roles_ids",
            ]
        )
        data = {}
        if "tester" in fields:
            data["Tester"] = [self.tester]
        if "app" in fields:
            data["App"] = [self.app]
        if "approved" in fields and self._approved is not None:
            data["Approved"] = self._approved
        if "server_id" in fields:
            data["Server ID"] = self.server_id
        if (
            "notification_message_id" in fields
            and self._notification_message_id is not None
        ):
            data["Notification Message ID"] = self._notification_message_id
        airtable_dict = {
            "fields": data,
        }
        if self.id:
            airtable_dict["id"] = self.id
        return airtable_dict


@dataclass
class App:
    id: str
    name: str
    approval_channel: Optional[str]
    reaction_role_ids: list[str]
    app_store_key_id: Optional[str]
    beta_group_id: Optional[str]

    @classmethod
    def from_airtable(cls, data: dict) -> "App":
        fields = data["fields"]
        return cls(
            id=data["id"],
            name=fields["Name"],
            approval_channel=fields.get("Approval Channel"),
            reaction_role_ids=fields["Reaction Role IDs"],
            app_store_key_id=fields["App Store Key ID"],
            beta_group_id=fields["Beta Group ID"],
        )


class MissingRecordIDError(Exception):
    def __init__(self, record: Optional[object], *args: object) -> None:
        self.record = record
        super().__init__(record, *args)


class AppStoreConnectError(Exception):
    pass


class ApiKeyNotSetError(AppStoreConnectError):
    def __init__(self, app: App, *args: object) -> None:
        self.app_name = app.name
        super().__init__(app.name, *args)


class BetaGroupNotSetError(AppStoreConnectError):
    def __init__(self, app: App, *args: object) -> None:
        self.app_name = app.name
        super().__init__(app.name, *args)


class ConfigError(Exception):
    def __init__(self, message: str, *args: object) -> None:
        super().__init__(message, *args)
