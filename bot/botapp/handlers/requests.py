from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from botapp import keyboards, texts
from botapp.api import BackendClient
from botapp.common import ready_user
from botapp.config import Config

router = Router(name="requests")

SHOWN = 10


@router.message(F.text == keyboards.BTN_REQUESTS)
async def my_requests(message: Message, state: FSMContext, api: BackendClient, config: Config):
    await state.clear()
    tg = message.from_user.id
    if not await ready_user(message, tg, api, config):
        return
    items = [("dep", d) for d in await api.list_deposits(tg)] + [
        ("wd", w) for w in await api.list_withdrawals(tg)
    ]
    items.sort(key=lambda pair: pair[1]["created_at"], reverse=True)
    items = items[:SHOWN]
    if not items:
        await message.answer("Заявок пока нет.")
        return
    buttons = [
        (kind, r["id"], texts.request_line(kind, r, config.timezone)) for kind, r in items
    ]
    await message.answer(
        "📋 <b>Ваши последние заявки</b> (нажмите, чтобы открыть):",
        reply_markup=keyboards.request_list(buttons),
    )


@router.callback_query(F.data.regexp(r"^req:(dep|wd):\d+$"))
async def open_request(call: CallbackQuery, api: BackendClient, config: Config):
    await call.answer()
    _, kind, raw_id = call.data.split(":")
    request_id, tg = int(raw_id), call.from_user.id
    if kind == "dep":
        d = await api.get_deposit(tg, request_id)
        text = texts.deposit_card(d, config.timezone)
        markup = keyboards.request_actions("dep", d["id"], d["status"] in texts.DEPOSIT_CANCELLABLE)
    else:
        w = await api.get_withdrawal(tg, request_id)
        text = texts.withdrawal_card(w, config.timezone)
        markup = keyboards.request_actions("wd", w["id"], w["status"] in texts.WITHDRAWAL_CANCELLABLE)
    await call.message.answer(text, reply_markup=markup)


@router.callback_query(F.data.regexp(r"^cancel:(dep|wd):\d+$"))
async def cancel_request(call: CallbackQuery, api: BackendClient, config: Config):
    await call.answer()
    _, kind, raw_id = call.data.split(":")
    request_id, tg = int(raw_id), call.from_user.id
    if kind == "dep":
        d = await api.cancel_deposit(tg, request_id)
        text = texts.deposit_card(d, config.timezone)
    else:
        w = await api.cancel_withdrawal(tg, request_id)
        text = texts.withdrawal_card(w, config.timezone)
    await call.message.answer("🚫 Заявка отменена.\n\n" + text)
