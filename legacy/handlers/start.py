import asyncio
from aiogram import Router
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command

router = Router()


@router.message(Command("start"))
async def start_handler(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="1️⃣ ВСТУПИТЬ В КЛУБ",
                callback_data="join_club",
                style="success"
            )
        ],
    ])

    await message.answer(
        "Добро пожаловать в Altyn Сrown!\n"
        "🏆 ID клуба: 692609\n\n"
        "Чтобы начать играть нужно:\n"
        "1️⃣ Вступить в клуб\n"
        "2️⃣ Пройти регистрацию в кассе\n\n"
        "Выберите действие:",
        reply_markup=kb
    )


@router.callback_query(lambda c: c.data == "join_club")
async def join_club(call: CallbackQuery):
    await call.answer()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🚀 ОТКРЫТЬ КЛУБ",
                url="https://clubgg.app.link/mIiESaFVq2b"
            )
        ]
    ])

    await call.message.answer("🔗 Перейдите по ссылке:", reply_markup=kb)

    await asyncio.sleep(10)

    kb2 = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=" 2️⃣ Регистрация в кассе",
                callback_data="open_cash",
                style="primary"
            )
        ]
    ])

    await call.message.answer(
        "⏳ Теперь доступна регистрация:",
        reply_markup=kb2
    )