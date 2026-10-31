class ServiceError(Exception):
    """Ожидаемая бизнес-ошибка. `code` стабилен и используется ботом и API."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
