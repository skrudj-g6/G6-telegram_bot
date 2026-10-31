from aiogram import Router
from aiogram.types import CallbackQuery
from data import user_data

router = Router()

@router.callback_query(lambda c: c.data == "type_withdraw")
async def withdraw(call: CallbackQuery):
    await call.answer()
    user_data[call.from_user.id]["type"] = "Вывод"
    await call.message.edit_text("Вы выбрали вывод")