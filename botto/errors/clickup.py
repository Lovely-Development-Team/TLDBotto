class ClickupError(Exception):
    def __init__(self, url: str, response: dict) -> None:
        self.url = url
        self.message = response["err"]
        self.code = response["ECODE"]
        super().__init__()

    def __repr__(self) -> str:
        return "{class_name}(code:{error_code}, message:'{error_message}', url:{url})".format(
            class_name=self.__class__,
            error_code=self.code,
            error_message=self.message,
            url=self.url,
        )

    def __str__(self) -> str:
        str_rep = "Error from AirTable operation of type '{error_code}', with message:'{error_message}'. " "\nRequest URL: {url}".format(
            error_code=self.code,
            error_message=self.message,
            url=self.url,
        )
        return str_rep
