class ServiceError(Exception):
    """Ожидаемая бизнес-ошибка. `code` стабилен и используется ботом и API.

    `extra` — дополнительные поля для бота (например, допустимые границы суммы).
    """

    def __init__(self, code: str, **extra):
        super().__init__(code)
        self.code = code
        self.extra = extra
