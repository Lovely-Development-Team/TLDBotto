from typing import TypedDict, Required


class ServerConfig(TypedDict, total=False):
    _id: str
    server_id: Required[str]


class ConfigValues(TypedDict, total=False):
    disabled_features: [str]
    respond_member_dms: bool
    dm_log_channel: str


class GeneralServerConfig(ServerConfig):
    config: ConfigValues
