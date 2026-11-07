"""Доставка уведомлений игрокам.

Бот периодически забирает у backend готовые уведомления, отправляет их в Telegram и
подтверждает результат. Токен бота нужен только здесь, backend в Telegram не ходит.
"""

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

from botapp import keyboards, texts
from botapp.api import ApiError, ApiUnavailable, BackendClient

logger = logging.getLogger(__name__)

POLL_SECONDS = 5
BATCH = 20
SEND_PAUSE = 0.05  # ~20 сообщений в секунду, ниже лимита Telegram


def _markup(name: str | None):
    if name == "menu":
        return keyboards.main_menu()
    if name == "retry_id":
        return keyboards.retry_id()
    return None


async def deliver(bot: Bot, api: BackendClient, item: dict) -> None:
    """Отправляет одно уведомление и сообщает backend результат."""
    rendered = texts.render_notification(item)
    if rendered is None:
        await api.notification_failed(item["id"], permanent=True, error="unknown_notification")
        return
    text, markup = rendered
    try:
        await bot.send_message(item["telegram_id"], text, reply_markup=_markup(markup))
    except TelegramRetryAfter as exc:
        await api.notification_failed(
            item["id"], permanent=False, error="flood_control", retry_after=int(exc.retry_after)
        )
    except TelegramForbiddenError:
        # Игрок заблокировал бота или удалил чат: повторять бессмысленно.
        await api.notification_failed(item["id"], permanent=True, error="forbidden")
    except TelegramBadRequest as exc:
        await api.notification_failed(
            item["id"], permanent=True, error=f"bad_request: {str(exc)[:60]}"
        )
    except TelegramAPIError as exc:
        await api.notification_failed(item["id"], permanent=False, error=type(exc).__name__)
    else:
        await api.notification_sent(item["id"])


async def run_once(bot: Bot, api: BackendClient) -> int:
    items = await api.claim_notifications(BATCH)
    for item in items:
        try:
            await deliver(bot, api, item)
        except (ApiError, ApiUnavailable) as exc:
            # Не смогли сообщить результат: запись вернётся в очередь после окончания аренды.
            logger.warning("Уведомление %s: нет подтверждения (%s)", item["id"], exc)
        await asyncio.sleep(SEND_PAUSE)
    return len(items)


async def run_forever(bot: Bot, api: BackendClient) -> None:
    while True:
        try:
            count = await run_once(bot, api)
            await asyncio.sleep(0 if count >= BATCH else POLL_SECONDS)
        except asyncio.CancelledError:
            raise
        except (ApiError, ApiUnavailable) as exc:
            logger.warning("Очередь уведомлений недоступна: %s", exc)
            await asyncio.sleep(POLL_SECONDS * 2)
        except Exception:
            logger.exception("Ошибка доставки уведомлений")
            await asyncio.sleep(POLL_SECONDS * 2)
