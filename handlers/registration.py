from aiogram import Router
from aiogram.types import FSInputFile, Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from data import user_data
from utils import is_valid_id

router = Router()


@router.callback_query(lambda c: c.data == "open_cash")
async def open_cash(call: CallbackQuery):
    await call.answer()
    user_data.setdefault(call.from_user.id, {})["awaiting_id"] = True
    await call.message.answer("Для регистрации вам необходимо ввести игровой ID из приложения ClubGG.\n\nВаш игровой ID можно найти в профиле игрока в ClubGG:\n1️⃣Нажмите на кнопку <Профиль> в правом углу экрана\n2️⃣ В вехней части экрана, ниже никнейма, написан ваш игровой ID\n\nВведите ID игрока в формате XXXX-XXXX")

@router.message()
async def handle_id(message: Message):
    user_id = message.from_user.id

    if not user_data.get(user_id, {}).get("awaiting_id"):
        return

    text = message.text.strip()

    if not is_valid_id(text):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Ввести игровой ID", callback_data="retry_id")],
            [InlineKeyboardButton(text="Где найти игровой ID?", callback_data="where_id")],
            [InlineKeyboardButton(text="Связаться с Админом", url="https://t.me/your_admin")]
        ])

        await message.answer("❌ Вы не верно ввели ваш игровой ID", reply_markup=kb)
        return

    user_data[user_id] = {
        "player_id": text,
        "awaiting_id": False
    }

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="💰 Пополнение",
                callback_data="type_deposit",
                style="success"
            )
        ],
        [
            InlineKeyboardButton(
                text="📤 Вывод",
                callback_data="type_withdraw",
                style="danger"
            )
        ],
        [
            InlineKeyboardButton(
                text="👤 Личный кабинет",
                callback_data="type_profile",
                style="primary"
            )
        ]
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

    photo1 = FSInputFile("images/lobby.jpg")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Продолжить",
                callback_data="where_id_step2",
                style="primary"
            )
        ]
    ])

    await call.message.answer_photo(
        photo=photo1,
        caption="В главном меню нажмите на кнопку Профиль",
        reply_markup=kb
    )


@router.callback_query(lambda c: c.data == "where_id_step2")
async def where_id_step2(call: CallbackQuery):
    await call.answer()

    photo2 = FSInputFile("images/userprofile.jpg")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Ввести игровой ID",
                callback_data="retry_id",
                style="success"
            )
        ]
    ])

    await call.message.answer_photo(
        photo=photo2,
        caption="В профиле игрока сверху ниже Никнейма вы можете найти свой игровой ID",
        reply_markup=kb
    )