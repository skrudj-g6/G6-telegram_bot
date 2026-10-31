"""Фоновые задачи backend: автозакрытие заявок без чека и удаление старых чеков.

Работает внутри процесса приложения. Безопасно при нескольких процессах: каждое
действие — условный UPDATE, повторно закрыть одну заявку нельзя.
"""

import asyncio
import logging

from app.db.session import get_session_factory
from app.services import deposits

logger = logging.getLogger(__name__)

EXPIRE_INTERVAL_SECONDS = 30
CLEANUP_EVERY_N_TICKS = 120  # раз в час при интервале 30 секунд


def run_once(*, cleanup: bool) -> None:
    with get_session_factory()() as db:
        expired = deposits.expire_overdue(db)
        if expired:
            logger.info("Закрыто заявок без чека: %s", expired)
        if cleanup:
            removed = deposits.cleanup_receipts(db)
            if removed:
                logger.info("Удалено чеков по сроку хранения: %s", removed)


async def run_forever() -> None:
    tick = 0
    while True:
        try:
            await asyncio.to_thread(run_once, cleanup=tick % CLEANUP_EVERY_N_TICKS == 0)
        except asyncio.CancelledError:
            raise
        except Exception:  # сбой одной итерации не должен останавливать таймер
            logger.exception("Ошибка фоновой задачи")
        tick += 1
        await asyncio.sleep(EXPIRE_INTERVAL_SECONDS)
