from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from data import user_data

router = Router()

@router.callback_query(lambda c: c.data == "type_deposit")
async def deposit(call: CallbackQuery):
    await call.answer()
    user_data[call.from_user.id]["type"] = "Пополнение"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🇰🇿 Казахстан", callback_data="country_kz")],
        [InlineKeyboardButton("₿ Крипто", callback_data="country_crypto")]
    ])

    await call.message.edit_text("Выберите страну:", reply_markup=kb)