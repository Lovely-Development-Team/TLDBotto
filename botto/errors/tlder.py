class TlderNotFoundError(Exception):
    def __init__(self, discord_id: str, *args: object) -> None:
        self.discord_id = discord_id
        super().__init__(*args)
