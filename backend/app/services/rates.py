"""Автоматический курс USDT/KZT (Q-30).

Курс получает фоновая задача (`worker.py`) и записывает в `app_settings`. Пока курс
свежий, пополнение криптой работает; если источник недоступен дольше
`usdt_rate_max_age_minutes`, оно временно отключается — по устаревшему курсу заявки
не создаются. В режиме `manual` (курс задал владелец) автообновление не вмешивается.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Protocol

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services import app_settings

logger = logging.getLogger(__name__)

# Курс, отличающийся от свежего предыдущего больше чем на 20%, считается сбоем источника
# и не применяется. Если рынок действительно так сдвинулся, владелец задаёт курс вручную.
MAX_CHANGE = Decimal("0.20")
HTTP_TIMEOUT_SECONDS = 10.0

UPDATED = "updated"
REJECTED = "rejected"
SKIPPED = "skipped"


class RateFetchError(Exception):
    """Источник курса недоступен или вернул непонятный ответ."""


class RateProvider(Protocol):
    name: str

    def fetch(self) -> Decimal:
        """Тенге за 1 USDT. Бросает RateFetchError, если получить курс не удалось."""


class CoinGeckoProvider:
    """Рыночный курс Tether к тенге с публичного API CoinGecko."""

    name = "coingecko"

    def __init__(self, url: str, client: httpx.Client | None = None):
        self._url = url
        self._client = client

    def fetch(self) -> Decimal:
        try:
            getter = self._client.get if self._client is not None else httpx.get
            response = getter(
                self._url,
                params={"ids": "tether", "vs_currencies": "kzt"},
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return Decimal(str(response.json()["tether"]["kzt"]))
        except (httpx.HTTPError, ValueError, KeyError, TypeError, InvalidOperation) as exc:
            # Только тип ошибки: ответ источника в логи не пишем.
            raise RateFetchError(type(exc).__name__) from exc


_provider: RateProvider | None = None
_provider_overridden = False


def get_provider() -> RateProvider | None:
    """Провайдер из настроек (`RATE_SOURCE`); None — автообновление выключено."""
    if _provider_overridden:
        return _provider
    settings = get_settings()
    if settings.rate_source == "coingecko":
        return CoinGeckoProvider(settings.rate_source_url)
    return None


def set_provider(provider: RateProvider | None) -> None:
    """Подмена источника (подключение другого провайдера и тесты)."""
    global _provider, _provider_overridden
    _provider, _provider_overridden = provider, True


def refresh_usdt_rate(
    db: Session, provider: RateProvider | None = None, now: datetime | None = None
) -> str:
    """Обновляет курс из источника. Возвращает UPDATED, REJECTED или SKIPPED.

    Сетевые ошибки (RateFetchError) пробрасываются вызывающему.
    """
    if app_settings.get_usdt_rate_mode(db) == app_settings.MODE_MANUAL:
        return SKIPPED
    provider = provider or get_provider()
    if provider is None:
        return SKIPPED

    now = now or datetime.now(timezone.utc)
    fetched = provider.fetch()
    if not fetched.is_finite() or fetched <= 0:
        logger.error("Источник %s вернул недопустимый курс", provider.name)
        return REJECTED
    rate = fetched.quantize(Decimal("0.01"))
    if rate <= 0:
        return REJECTED

    previous = app_settings.get_usdt_rate(db, now)  # None, если нет или устарел
    if previous is not None and abs(rate - previous) / previous > MAX_CHANGE:
        logger.error(
            "Курс от %s отклонён: изменение больше %s%% (было %s, пришло %s)",
            provider.name,
            int(MAX_CHANGE * 100),
            previous,
            rate,
        )
        return REJECTED

    app_settings.set_str(db, app_settings.USDT_RATE_KEY, format(rate, "f"))
    app_settings.set_str(db, app_settings.USDT_RATE_UPDATED_KEY, now.isoformat())
    app_settings.set_str(db, app_settings.USDT_RATE_SOURCE_KEY, f"auto:{provider.name}")
    db.commit()
    return UPDATED
