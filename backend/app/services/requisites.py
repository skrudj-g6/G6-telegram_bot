"""Источник платёжных реквизитов для пополнения.

Платёжка пока не подключена (Q-22): по умолчанию свободных реквизитов нет, заявка не
создаётся, бот показывает «нет свободных реквизитов, обратитесь через 10 минут».
Когда платёжка появится, достаточно подставить свою реализацию через `set_provider`.
"""

from decimal import Decimal
from typing import Protocol


class RequisitesProvider(Protocol):
    def reserve(
        self, method: str, amount: int, usdt_amount: Decimal | None = None
    ) -> dict | None:
        """Возвращает реквизиты для оплаты или None, если свободных нет.

        `amount` — тенге; для crypto дополнительно передаётся `usdt_amount`.
        """


class NoRequisitesProvider:
    def reserve(
        self, method: str, amount: int, usdt_amount: Decimal | None = None
    ) -> dict | None:
        return None


_provider: RequisitesProvider = NoRequisitesProvider()


def get_provider() -> RequisitesProvider:
    return _provider


def set_provider(provider: RequisitesProvider) -> None:
    global _provider
    _provider = provider
