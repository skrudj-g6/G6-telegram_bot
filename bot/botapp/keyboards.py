from aiogram import F
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

BTN_DEPOSIT = "💰 Пополнение"
BTN_WITHDRAW = "📤 Вывод"
BTN_REQUESTS = "📋 Мои заявки"
BTN_PROFILE = "👤 Профиль"
BTN_SUPPORT = "🆘 Поддержка"
MENU_BUTTONS = (BTN_DEPOSIT, BTN_WITHDRAW, BTN_REQUESTS, BTN_PROFILE, BTN_SUPPORT)

# Ввод игрока в диалоге: текст, который не является кнопкой меню. Нажатие кнопки меню
# посреди диалога прерывает его, а не воспринимается как ответ (сумма, имя, ID).
TEXT_INPUT = F.text & ~F.text.in_(MENU_BUTTONS)
NOT_TEXT_INPUT = ~F.text


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_DEPOSIT), KeyboardButton(text=BTN_WITHDRAW)],
            [KeyboardButton(text=BTN_REQUESTS), KeyboardButton(text=BTN_PROFILE)],
            [KeyboardButton(text=BTN_SUPPORT)],
        ],
        resize_keyboard=True,
    )


def _rows(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=list(rows))


def button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def url_button(text: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, url=url)


CANCEL_FLOW = button("✖️ Отмена", "flow:cancel")


def onboarding(invite_url: str) -> InlineKeyboardMarkup:
    rows = []
    if invite_url:
        rows.append([url_button("🚀 Открыть клуб", invite_url)])
    rows.append([button("2️⃣ Регистрация в кассе", "reg:start")])
    return _rows(*rows)


def id_help(support_url: str) -> InlineKeyboardMarkup:
    rows = [[button("Где найти игровой ID?", "reg:where")]]
    if support_url:
        rows.append([url_button("Связаться с админом", support_url)])
    return _rows(*rows)


def retry_id() -> InlineKeyboardMarkup:
    return _rows([button("Ввести игровой ID", "reg:start")])


def where_next() -> InlineKeyboardMarkup:
    return _rows([button("Продолжить", "reg:where2")])


def deposit_methods() -> InlineKeyboardMarkup:
    return _rows(
        [button("💳 Тенге", "dep:m:fiat")],
        [button("🪙 Криптовалюта (USDT)", "dep:m:crypto")],
        [CANCEL_FLOW],
    )


def withdrawal_methods() -> InlineKeyboardMarkup:
    return _rows(
        [button("💳 Тенге", "wd:m:fiat")],
        [button("🪙 Криптовалюта (USDT)", "wd:m:crypto")],
        [CANCEL_FLOW],
    )


def confirm(data: str, text: str = "✅ Подтвердить") -> InlineKeyboardMarkup:
    return _rows([button(text, data)], [CANCEL_FLOW])


def cancel_only() -> InlineKeyboardMarkup:
    return _rows([CANCEL_FLOW])


def banks(items: list[dict]) -> InlineKeyboardMarkup:
    return _rows(*[[button(b["name"], f"wd:bank:{b['id']}")] for b in items], [CANCEL_FLOW])


def request_actions(kind: str, request_id: int, cancellable: bool) -> InlineKeyboardMarkup | None:
    if not cancellable:
        return None
    return _rows([button("❌ Отменить заявку", f"cancel:{kind}:{request_id}")])


def request_list(items: list[tuple[str, int, str]]) -> InlineKeyboardMarkup:
    """items: (kind, id, подпись)."""
    return _rows(*[[button(label, f"req:{kind}:{rid}")] for kind, rid, label in items])


def support(url: str) -> InlineKeyboardMarkup | None:
    return _rows([url_button("Написать в поддержку", url)]) if url else None
