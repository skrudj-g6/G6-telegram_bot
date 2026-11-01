"""Вывод криптой через отдельный PSP (Q-31).

PSP сам запрашивает у игрока всё необходимое (адрес, сеть), поэтому от бота нужна только
сумма в тенге. Пока PSP не подключён, вывод криптой недоступен: заявка не создаётся, бот
показывает «нет свободных реквизитов, обратитесь через 10 минут» (Q-22). Подключение —
через `set_provider`.
"""

from typing import Protocol


class CryptoPayoutProvider(Protocol):
    def start(self, amount: int) -> dict | None:
        """Открывает выплату у PSP на `amount` тенге. Возвращает данные PSP для заявки
        (ссылка, идентификатор) или None, если PSP сейчас недоступен."""


class NoCryptoPayoutProvider:
    def start(self, amount: int) -> dict | None:
        return None


_provider: CryptoPayoutProvider = NoCryptoPayoutProvider()


def get_provider() -> CryptoPayoutProvider:
    return _provider


def set_provider(provider: CryptoPayoutProvider) -> None:
    global _provider
    _provider = provider
