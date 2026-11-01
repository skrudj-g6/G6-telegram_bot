import logging
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message

from botapp import keyboards, texts
from botapp.api import ApiError, BackendClient
from botapp.common import show_entry
from botapp.config import Config

logger = logging.getLogger(__name__)
router = Router(name="registration")

IMAGES = Path(__file__).resolve().parents[2] / "images"

INSTRUCTION = (
    "Для регистрации введите игровой ID из приложения ClubGG.\n\n"
    "Где его найти:\n"
    "1️⃣ Нажмите «Профиль» в правом углу экрана\n"
    "2️⃣ В верхней части экрана, под никнеймом, указан игровой ID\n\n"
    "Введите ID в формате XXXX-XXXX"
)


class Registration(StatesGroup):
    waiting_id = State()


@router.callback_query(F.data == "reg:start")
async def reg_start(call: CallbackQuery, state: FSMContext, config: Config):
    await call.answer()
    await state.set_state(Registration.waiting_id)
    await call.message.answer(INSTRUCTION, reply_markup=keyboards.id_help(config.support_url))


async def _send_help_photo(call: CallbackQuery, filename: str, caption: str, markup) -> None:
    path = IMAGES / filename
    if path.is_file():
        await call.message.answer_photo(FSInputFile(path), caption=caption, reply_markup=markup)
    else:  # картинки не критичны: подсказка работает и текстом
        logger.warning("Нет файла подсказки %s", filename)
        await call.message.answer(caption, reply_markup=markup)


@router.callback_query(F.data == "reg:where")
async def reg_where(call: CallbackQuery):
    await call.answer()
    await _send_help_photo(
        call, "lobby.jpg", "В главном меню нажмите на кнопку «Профиль»", keyboards.where_next()
    )


@router.callback_query(F.data == "reg:where2")
async def reg_where2(call: CallbackQuery):
    await call.answer()
    await _send_help_photo(
        call,
        "userprofile.jpg",
        "В профиле игрока, под никнеймом, указан ваш игровой ID",
        keyboards.retry_id(),
    )


@router.message(Registration.waiting_id, keyboards.TEXT_INPUT)
async def reg_player_id(
    message: Message, state: FSMContext, api: BackendClient, config: Config
):
    try:
        await api.link_account(message.from_user.id, message.text.strip())
    except ApiError as exc:
        if exc.code == "invalid_player_id":
            await message.answer(
                "❌ " + texts.error_text(exc.code), reply_markup=keyboards.id_help(config.support_url)
            )
            return
        if exc.code == "player_id_taken":
            await message.answer(texts.error_text(exc.code, exc.extra))
            if exc.extra.get("blocked"):
                await state.clear()
            return
        if exc.code in ("account_locked", "user_blocked", "user_not_found"):
            await state.clear()
        raise
    await state.clear()
    user = await api.profile(message.from_user.id)
    await show_entry(message, user, config)


@router.message(Registration.waiting_id, keyboards.NOT_TEXT_INPUT)
async def reg_not_text(message: Message):
    await message.answer("Введите игровой ID текстом в формате XXXX-XXXX")
