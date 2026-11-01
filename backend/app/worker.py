"""Фоновые задачи backend: автозакрытие заявок без чека, удаление старых чеков и
обновление курса USDT.

Работает внутри процесса приложения. Безопасно при нескольких процессах: каждое
действие — условный UPDATE, повторно закрыть одну заявку нельзя.
"""

import asyncio
import logging

from app.db.session import get_session_factory
from app.services import deposits, rates

logger = logging.getLogger(__name__)

TICK_SECONDS = 30
CLEANUP_EVERY_N_TICKS = 120  # раз в час
RATE_EVERY_N_TICKS = 10  # раз в 5 минут


def run_once(*, cleanup: bool, refresh_rate: bool = False) -> None:
    with get_session_factory()() as db:
        expired = deposits.expire_overdue(db)
        if expired:
            logger.info("Закрыто заявок без чека: %s", expired)
        if cleanup:
            removed = deposits.cleanup_receipts(db)
            if removed:
                logger.info("Удалено чеков по сроку хранения: %s", removed)

    if refresh_rate:
        # Сбой источника курса не должен мешать закрытию заявок, поэтому отдельно.
        try:
            with get_session_factory()() as db:
                if rates.refresh_usdt_rate(db) == rates.UPDATED:
                    logger.info("Курс USDT обновлён")
        except rates.RateFetchError as exc:
            logger.warning("Не удалось получить курс USDT (%s)", exc)


async def run_forever() -> None:
    tick = 0
    while True:
        try:
            await asyncio.to_thread(
                run_once,
                cleanup=tick % CLEANUP_EVERY_N_TICKS == 0,
                refresh_rate=tick % RATE_EVERY_N_TICKS == 0,
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # сбой одной итерации не должен останавливать таймер
            logger.exception("Ошибка фоновой задачи")
        tick += 1
        await asyncio.sleep(TICK_SECONDS)
