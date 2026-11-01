"""Общие шаги: вход игрока по статусу аккаунта и проверка допуска к кассе."""

from aiogram.types import Message

from botapp import keyboards, texts
from botapp.api import BackendClient
from botapp.config import Config


async def show_entry(message: Message, user: dict, config: Config) -> bool:
    """Показывает экран по состоянию игрока. True — игрок допущен к кассе (аккаунт подтверждён).

    Зарегистрированного игрока повторно по воронке не ведём (Q-20).
    """
    if user["status"] == "blocked":
        await message.answer(texts.error_text("user_blocked"))
        return False

    account = user.get("poker_account")
    if account is None:
        await message.answer(
            "Добро пожаловать в Altyn Crown!\n"
            f"🏆 ID клуба: {texts.e(config.club_id)}\n\n"
            "Чтобы начать играть, нужно:\n"
            "1️⃣ Вступить в клуб\n"
            "2️⃣ Пройти регистрацию в кассе\n\n"
            "Выберите действие:",
            reply_markup=keyboards.onboarding(config.club_invite_url),
        )
        return False
    if account["status"] == "pending":
        await message.answer(
            f"⏳ Игровой ID <code>{texts.e(account['player_id'])}</code> отправлен администратору "
            "на подтверждение. Как только вас примут в клуб, касса станет доступна.\n"
            "Проверить статус можно командой /start.",
            reply_markup=keyboards.main_menu(),
        )
        return False
    if account["status"] == "rejected":
        reason = account.get("reject_reason")
        await message.answer(
            "❌ Администратор отклонил ваш игровой ID."
            + (f"\nПричина: {texts.e(reason)}" if reason else "")
            + "\n\nМожно ввести ID заново.",
            reply_markup=keyboards.retry_id(),
        )
        return False

    await message.answer("Выберите действие в меню ниже 👇", reply_markup=keyboards.main_menu())
    return True


async def ready_user(
    message: Message, telegram_id: int, api: BackendClient, config: Config
) -> dict | None:
    """Игрок, допущенный к кассе, или None (с объяснением, что делать дальше)."""
    user = await api.profile(telegram_id)
    if user is None:
        await message.answer("Сначала отправьте /start")
        return None
    if user["status"] == "blocked":
        await message.answer(texts.error_text("user_blocked"))
        return None
    account = user.get("poker_account")
    if account is None or account["status"] != "approved":
        await show_entry(message, user, config)
        return None
    return user
