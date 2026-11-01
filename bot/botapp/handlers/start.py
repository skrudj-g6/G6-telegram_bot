from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from botapp import keyboards, texts
from botapp.api import BackendClient
from botapp.common import ready_user, show_entry
from botapp.config import Config

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, api: BackendClient, config: Config):
    await state.clear()
    user = message.from_user
    registered = await api.register(user.id, user.username, user.first_name or "Игрок")
    await show_entry(message, registered, config)


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext, api: BackendClient, config: Config):
    await state.clear()
    if await ready_user(message, message.from_user.id, api, config):
        await message.answer("Выберите действие в меню ниже 👇", reply_markup=keyboards.main_menu())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=keyboards.main_menu())


@router.callback_query(F.data == "flow:cancel")
async def flow_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    await call.message.answer("Отменено.", reply_markup=keyboards.main_menu())


@router.message(F.text == keyboards.BTN_PROFILE)
async def profile(message: Message, state: FSMContext, api: BackendClient, config: Config):
    await state.clear()
    user = await api.profile(message.from_user.id)
    if user is None:
        await message.answer("Сначала отправьте /start")
        return
    await message.answer(texts.profile_card(user, config.club_id))


@router.message(F.text == keyboards.BTN_SUPPORT)
async def support(message: Message, state: FSMContext, config: Config):
    await state.clear()
    markup = keyboards.support(config.support_url)
    await message.answer(
        "🆘 По любым вопросам по кассе обратитесь в поддержку."
        if markup
        else "🆘 Контакт поддержки пока не настроен. Обратитесь к администратору клуба.",
        reply_markup=markup,
    )
