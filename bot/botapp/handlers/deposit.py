import uuid

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from botapp import keyboards, texts
from botapp.api import ApiError, BackendClient
from botapp.common import ready_user
from botapp.config import Config
from botapp.parsing import parse_amount, parse_usdt

router = Router(name="deposit")

# Коды, после которых продолжать диалог бессмысленно: состояние сбрасывается.
TERMINAL = {
    "no_requisites_available",
    "deposit_awaiting_receipt",
    "account_not_approved",
    "user_blocked",
    "user_not_found",
}


class Deposit(StatesGroup):
    amount_fiat = State()
    amount_crypto = State()
    confirm_crypto = State()


async def _awaiting_receipt(api: BackendClient, telegram_id: int) -> dict | None:
    return next(
        (d for d in await api.list_deposits(telegram_id) if d["status"] == "awaiting_receipt"), None
    )


@router.message(F.text == keyboards.BTN_DEPOSIT)
async def deposit_menu(message: Message, state: FSMContext, api: BackendClient, config: Config):
    await state.clear()
    if not await ready_user(message, message.from_user.id, api, config):
        return
    existing = await _awaiting_receipt(api, message.from_user.id)
    if existing:  # Ждём чек по прежней заявке: новую создать нельзя
        await message.answer(
            "У вас уже есть заявка, ожидающая чек:\n\n" + texts.deposit_card(existing, config.timezone),
            reply_markup=keyboards.request_actions("dep", existing["id"], True),
        )
        return
    await message.answer("Выберите способ пополнения:", reply_markup=keyboards.deposit_methods())


@router.callback_query(F.data == "dep:m:fiat")
async def method_fiat(call: CallbackQuery, state: FSMContext, api: BackendClient):
    await call.answer()
    limits = await api.limits()
    await state.set_state(Deposit.amount_fiat)
    await state.update_data(key=uuid.uuid4().hex)
    await call.message.answer(
        f"Введите сумму пополнения в тенге ({texts.limits_hint(limits, 'deposit')}):",
        reply_markup=keyboards.cancel_only(),
    )


@router.callback_query(F.data == "dep:m:crypto")
async def method_crypto(call: CallbackQuery, state: FSMContext, api: BackendClient):
    await call.answer()
    limits = await api.limits()
    await state.set_state(Deposit.amount_crypto)
    await state.update_data(key=uuid.uuid4().hex)
    await call.message.answer(
        "Введите, сколько USDT вы хотите внести (например, 25 или 25.50). "
        "Сумму в тенге мы рассчитаем по текущему курсу.\n"
        f"Лимит заявки: {texts.limits_hint(limits, 'deposit')}.",
        reply_markup=keyboards.cancel_only(),
    )


async def _created(message: Message, deposit: dict, config: Config) -> None:
    await message.answer(
        texts.deposit_created(deposit, config.timezone),
        reply_markup=keyboards.request_actions("dep", deposit["id"], True),
    )


@router.message(Deposit.amount_fiat, keyboards.TEXT_INPUT)
async def fiat_amount(message: Message, state: FSMContext, api: BackendClient, config: Config):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("Введите сумму целым числом в тенге, например 5000.")
        return
    key = (await state.get_data())["key"]
    try:
        deposit = await api.create_deposit(
            message.from_user.id, method="fiat", amount=amount, key=key
        )
    except ApiError as exc:
        if exc.code in TERMINAL:
            await state.clear()
        raise
    await state.clear()
    await _created(message, deposit, config)


@router.message(Deposit.amount_crypto, keyboards.TEXT_INPUT)
async def crypto_amount(message: Message, state: FSMContext, api: BackendClient):
    usdt = parse_usdt(message.text)
    if usdt is None:
        await message.answer("Введите количество USDT числом, не более двух знаков после точки.")
        return
    try:
        quote = await api.usdt_quote(usdt)
    except ApiError as exc:
        if exc.code == "exchange_rate_unavailable":
            await state.clear()
        raise
    if not quote["within_limits"]:
        await message.answer(
            f"{quote['usdt_amount']} USDT ≈ {texts.money(quote['kzt_amount'])}. "
            f"Сумма заявки должна быть от {texts.money(quote['min'])} до {texts.money(quote['max'])}. "
            "Введите другую сумму.",
            reply_markup=keyboards.cancel_only(),
        )
        return
    await state.set_state(Deposit.confirm_crypto)
    await state.update_data(usdt=usdt)
    lines = [
        "🪙 <b>Проверьте заявку</b>",
        "",
        f"Вы вносите: <b>{texts.e(quote['usdt_amount'])} USDT</b>",
        f"Курс: {texts.e(quote['rate'])} ₸ за 1 USDT",
        f"Сумма: {texts.money(quote['kzt_amount'])}",
    ]
    note = texts.percent_note(quote["commission_percent"], quote["commission_amount"])
    if note:
        lines.append(note)
    lines.append(f"К зачислению на игровой счёт: <b>{texts.money(quote['credit_amount'])}</b>")
    lines.append("\nКурс фиксируется в момент создания заявки.")
    await message.answer(
        "\n".join(lines), reply_markup=keyboards.confirm("dep:ok", "✅ Создать заявку")
    )


@router.callback_query(Deposit.confirm_crypto, F.data == "dep:ok")
async def crypto_confirm(
    call: CallbackQuery, state: FSMContext, api: BackendClient, config: Config
):
    await call.answer()
    data = await state.get_data()
    try:
        deposit = await api.create_deposit(
            call.from_user.id, method="crypto", usdt_amount=data["usdt"], key=data["key"]
        )
    except ApiError as exc:
        if exc.code in TERMINAL or exc.code == "exchange_rate_unavailable":
            await state.clear()
        raise
    await state.clear()
    await _created(call.message, deposit, config)


@router.message(Deposit.amount_fiat, keyboards.NOT_TEXT_INPUT)
@router.message(Deposit.amount_crypto, keyboards.NOT_TEXT_INPUT)
async def amount_not_text(message: Message):
    await message.answer("Введите сумму текстом.")


@router.callback_query(F.data == "dep:ok")
async def stale_confirm(call: CallbackQuery):
    await call.answer("Кнопка устарела. Начните заново из меню.", show_alert=True)
