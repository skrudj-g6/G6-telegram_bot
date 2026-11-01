import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import ExceptionTypeFilter
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import ErrorEvent

from botapp import texts
from botapp.api import ApiError, ApiUnavailable, BackendClient
from botapp.config import Config
from botapp.handlers import deposit, receipts, registration, requests, start, withdraw

logger = logging.getLogger(__name__)


async def _reply(event: ErrorEvent, text: str) -> None:
    update = event.update
    if update.callback_query is not None:
        target = update.callback_query.message  # callback уже подтверждён в обработчике
    else:
        target = update.message
    if target is not None:
        await target.answer(text)


async def on_api_error(event: ErrorEvent) -> bool:
    exc = event.exception
    await _reply(event, texts.error_text(exc.code, exc.extra))
    return True


async def on_unavailable(event: ErrorEvent) -> bool:
    logger.warning("Backend недоступен: %s", event.exception)
    await _reply(event, texts.UNAVAILABLE)
    return True


async def on_unexpected(event: ErrorEvent) -> bool:
    logger.exception("Необработанная ошибка", exc_info=event.exception)
    await _reply(event, texts.GENERIC_ERROR)
    return True


def build_dispatcher(config: Config, api: BackendClient) -> Dispatcher:
    storage = RedisStorage.from_url(config.redis_url) if config.redis_url else MemoryStorage()
    dp = Dispatcher(storage=storage, api=api, config=config)
    # Порядок важен: кнопки меню и /start сначала, затем диалоги, чек — отдельно.
    dp.include_routers(
        start.router,
        registration.router,
        deposit.router,
        withdraw.router,
        requests.router,
        receipts.router,
    )
    dp.errors.register(on_api_error, ExceptionTypeFilter(ApiError))
    dp.errors.register(on_unavailable, ExceptionTypeFilter(ApiUnavailable))
    dp.errors.register(on_unexpected)
    return dp


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # в URL нет секретов, но шума много
    config = Config.from_env()
    api = BackendClient(config.backend_url, config.service_token)
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher(config, api)
    logger.info("Бот запущен (club=%s)", config.club_id)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await api.aclose()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
