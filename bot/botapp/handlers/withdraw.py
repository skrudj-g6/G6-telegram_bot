import uuid

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from botapp import keyboards, texts
from botapp.api import ApiError, BackendClient
from botapp.common import ready_user
from botapp.config import Config
from botapp.parsing import clean_name, parse_amount

router = Router(name="withdraw")

TERMINAL = {
    "no_requisites_available",
    "withdrawal_already_open",
    "account_not_approved",
    "user_blocked",
    "user_not_found",
}
OPEN_STATUSES = ("pending", "processing")


class Withdraw(StatesGroup):
    amount = State()
    name = State()
    bank = State()
    confirm = State()


@router.message(F.text == keyboards.BTN_WITHDRAW)
async def withdraw_menu(message: Message, state: FSMContext, api: BackendClient, config: Config):
    await state.clear()
    if not await ready_user(message, message.from_user.id, api, config):
        return
    open_request = next(
        (w for w in await api.list_withdrawals(message.from_user.id) if w["status"] in OPEN_STATUSES),
        None,
    )
    if open_request:  # одна открытая заявка на вывод (Q-37)
        await message.answer(
            "У вас уже есть открытая заявка на вывод:\n\n"
            + texts.withdrawal_card(open_request, config.timezone),
            reply_markup=keyboards.request_actions(
                "wd", open_request["id"], open_request["status"] in texts.WITHDRAWAL_CANCELLABLE
            ),
        )
        return
    await message.answer("Выберите способ вывода:", reply_markup=keyboards.withdrawal_methods())


async def _ask_amount(call: CallbackQuery, state: FSMContext, api: BackendClient, method: str):
    await call.answer()
    limits = await api.limits()
    await state.set_state(Withdraw.amount)
    await state.update_data(method=method, key=uuid.uuid4().hex)
    await call.message.answer(
        f"Введите сумму вывода в тенге ({texts.limits_hint(limits, 'withdrawal')}):",
        reply_markup=keyboards.cancel_only(),
    )


@router.callback_query(F.data == "wd:m:fiat")
async def method_fiat(call: CallbackQuery, state: FSMContext, api: BackendClient):
    await _ask_amount(call, state, api, "fiat")


@router.callback_query(F.data == "wd:m:crypto")
async def method_crypto(call: CallbackQuery, state: FSMContext, api: BackendClient):
    # Q-31: данные для выплаты криптой запрашивает PSP, от игрока нужна только сумма.
    await _ask_amount(call, state, api, "crypto")


async def _show_summary(target: Message, state: FSMContext, api: BackendClient) -> None:
    data = await state.get_data()
    quote = await api.withdrawal_quote(data["amount"])
    await state.set_state(Withdraw.confirm)
    await target.answer(
        texts.withdrawal_summary(quote, data["method"], data.get("holder"), data.get("bank_name")),
        reply_markup=keyboards.confirm("wd:ok", "✅ Создать заявку"),
    )


@router.message(Withdraw.amount, keyboards.TEXT_INPUT)
async def amount(message: Message, state: FSMContext, api: BackendClient):
    value = parse_amount(message.text)
    if value is None:
        await message.answer("Введите сумму целым числом в тенге, например 5000.")
        return
    quote = await api.withdrawal_quote(value)
    if not quote["within_limits"]:
        await message.answer(
            f"Сумма вывода должна быть от {texts.money(quote['min'])} до {texts.money(quote['max'])}. "
            "Введите другую сумму.",
            reply_markup=keyboards.cancel_only(),
        )
        return
    await state.update_data(amount=value)
    data = await state.get_data()
    if data["method"] == "crypto":
        await _show_summary(message, state, api)
        return
    await state.set_state(Withdraw.name)
    await message.answer(
        "Введите имя получателя так, как оно указано в банке:", reply_markup=keyboards.cancel_only()
    )


@router.message(Withdraw.name, keyboards.TEXT_INPUT)
async def holder_name(message: Message, state: FSMContext, api: BackendClient):
    name = clean_name(message.text)
    if name is None:
        await message.answer("Имя должно быть от 2 до 100 символов. Введите ещё раз.")
        return
    banks = await api.banks()
    if not banks:
        await state.clear()
        await message.answer("Список банков пока пуст. Обратитесь в поддержку.")
        return
    await state.update_data(holder=name)
    await state.set_state(Withdraw.bank)
    await message.answer("Выберите банк получателя:", reply_markup=keyboards.banks(banks))


@router.callback_query(Withdraw.bank, F.data.startswith("wd:bank:"))
async def choose_bank(call: CallbackQuery, state: FSMContext, api: BackendClient):
    await call.answer()
    try:
        bank_id = int(call.data.split(":")[2])
    except (IndexError, ValueError):
        return
    bank = next((b for b in await api.banks() if b["id"] == bank_id), None)
    if bank is None:
        await call.message.answer(texts.error_text("invalid_bank"))
        return
    await state.update_data(bank_id=bank["id"], bank_name=bank["name"])
    await _show_summary(call.message, state, api)


@router.callback_query(Withdraw.confirm, F.data == "wd:ok")
async def confirm(call: CallbackQuery, state: FSMContext, api: BackendClient):
    await call.answer()
    data = await state.get_data()
    try:
        withdrawal = await api.create_withdrawal(
            call.from_user.id,
            method=data["method"],
            amount=data["amount"],
            key=data["key"],
            holder_name=data.get("holder"),
            bank_id=data.get("bank_id"),
        )
    except ApiError as exc:
        if exc.code in TERMINAL:
            await state.clear()
        raise
    await state.clear()
    await call.message.answer(
        texts.withdrawal_created(withdrawal),
        reply_markup=keyboards.request_actions(
            "wd", withdrawal["id"], withdrawal["status"] in texts.WITHDRAWAL_CANCELLABLE
        ),
    )


@router.message(Withdraw.amount, keyboards.NOT_TEXT_INPUT)
@router.message(Withdraw.name, keyboards.NOT_TEXT_INPUT)
async def not_text(message: Message):
    await message.answer("Введите значение текстом.")


@router.callback_query(F.data.in_({"wd:ok"}) | F.data.startswith("wd:bank:"))
async def stale(call: CallbackQuery):
    await call.answer("Кнопка устарела. Начните заново из меню.", show_alert=True)
