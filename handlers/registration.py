from aiogram import Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from data import user_data
from utils import is_valid_id

router = Router()


@router.callback_query(lambda c: c.data == "open_cash")
async def open_cash(call: CallbackQuery):
    await call.answer()
    user_data.setdefault(call.from_user.id, {})["awaiting_id"] = True
    await call.message.answer("Введите ID игрока в формате XXXX-XXXX")


@router.message()
async def handle_id(message: Message):
    user_id = message.from_user.id

    if not user_data.get(user_id, {}).get("awaiting_id"):
        return

    text = message.text.strip()

    if not is_valid_id(text):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Ввести ещё раз", callback_data="retry_id")],
            [InlineKeyboardButton(text="Где найти айди?", callback_data="where_id")],
            [InlineKeyboardButton(text="Связь с Админом", url="https://t.me/your_admin")]
        ])

        await message.answer("❌ Неверный формат ID", reply_markup=kb)
        return

    user_data[user_id] = {
        "player_id": text,
        "awaiting_id": False
    }

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Пополнение", callback_data="type_deposit")],
        [InlineKeyboardButton(text="📤 Вывод", callback_data="type_withdraw")],
        [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="type_profile")]
    ])

    await message.answer("Выберите действие:", reply_markup=kb)


@router.callback_query(lambda c: c.data == "retry_id")
async def retry_id(call: CallbackQuery):
    await call.answer()
    user_data.setdefault(call.from_user.id, {})["awaiting_id"] = True
    await call.message.answer("Введите ID игрока в формате XXXX-XXXX")


@router.callback_query(lambda c: c.data == "where_id")
async def where_id(call: CallbackQuery):
    await call.answer()
    await call.message.answer("📍 ID можно найти в профиле игрока в игре.")