from aiogram import Router
from aiogram.types import CallbackQuery
from data import user_data

router = Router()

@router.callback_query(lambda c: c.data == "type_profile")
async def profile(call: CallbackQuery):
    await call.answer()
    data = user_data.get(call.from_user.id, {})
    await call.message.edit_text(f"👤 Ваш ID: {data.get('player_id', '—')}")