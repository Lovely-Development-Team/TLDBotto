from typing import TypedDict

from botto.storage.models.server_config import ServerConfig


class RuleAgreementMessage(TypedDict):
    channel: str
    message: str


class ConfigValues(TypedDict, total=False):
    default_approvals_channel: str
    approval_emojis: [str]
    removal_emojis: [str]
    rule_agreement_role: str
    rule_agreement_message: RuleAgreementMessage
    tester_exit_notifications_channel: str
    rejection_emojis: [str]


class TestFlightServerConfig(ServerConfig):
    config: ConfigValues
