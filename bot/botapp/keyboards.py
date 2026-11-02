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
            [
                KeyboardButton(text=BTN_DEPOSIT, style="success"),
                KeyboardButton(text=BTN_WITHDRAW, style="danger"),
            ],
            [KeyboardButton(text=BTN_REQUESTS), KeyboardButton(text=BTN_PROFILE, style="primary")],
            [KeyboardButton(text=BTN_SUPPORT)],
        ],
        resize_keyboard=True,
    )


def _rows(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=list(rows))


# Цвета кнопок (Q-50): success — зелёный, danger — красный, primary — синий.
SUCCESS, DANGER, PRIMARY = "success", "danger", "primary"


def button(text: str, data: str, style: str | None = None) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data, style=style)


def url_button(text: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, url=url)


CANCEL_FLOW = button("✖️ Отмена", "flow:cancel", DANGER)


def onboarding() -> InlineKeyboardMarkup:
    return _rows([button("1️⃣ ВСТУПИТЬ В КЛУБ", "club:join", SUCCESS)])


def open_club(invite_url: str) -> InlineKeyboardMarkup:
    return _rows([url_button("🚀 ОТКРЫТЬ КЛУБ", invite_url)])


def register_in_cashier() -> InlineKeyboardMarkup:
    return _rows([button("2️⃣ Регистрация в кассе", "reg:start", PRIMARY)])


def id_help(support_url: str) -> InlineKeyboardMarkup:
    rows = [[button("Где найти игровой ID?", "reg:where")]]
    if support_url:
        rows.append([url_button("Связаться с админом", support_url)])
    return _rows(*rows)


def retry_id() -> InlineKeyboardMarkup:
    return _rows([button("Ввести игровой ID", "reg:start", SUCCESS)])


def where_next() -> InlineKeyboardMarkup:
    return _rows([button("Продолжить", "reg:where2", PRIMARY)])


def deposit_methods() -> InlineKeyboardMarkup:
    return _rows(
        [button("💳 Тенге", "dep:m:fiat", SUCCESS)],
        [button("🪙 Криптовалюта (USDT)", "dep:m:crypto", PRIMARY)],
        [CANCEL_FLOW],
    )


def withdrawal_methods() -> InlineKeyboardMarkup:
    return _rows(
        [button("💳 Тенге", "wd:m:fiat", SUCCESS)],
        [button("🪙 Криптовалюта (USDT)", "wd:m:crypto", PRIMARY)],
        [CANCEL_FLOW],
    )


def confirm(data: str, text: str = "✅ Подтвердить") -> InlineKeyboardMarkup:
    return _rows([button(text, data, SUCCESS)], [CANCEL_FLOW])


def cancel_only() -> InlineKeyboardMarkup:
    return _rows([CANCEL_FLOW])


def banks(items: list[dict]) -> InlineKeyboardMarkup:
    return _rows(*[[button(b["name"], f"wd:bank:{b['id']}")] for b in items], [CANCEL_FLOW])


def request_actions(kind: str, request_id: int, cancellable: bool) -> InlineKeyboardMarkup | None:
    if not cancellable:
        return None
    return _rows([button("❌ Отменить заявку", f"cancel:{kind}:{request_id}", DANGER)])


def request_list(items: list[tuple[str, int, str]]) -> InlineKeyboardMarkup:
    """items: (kind, id, подпись)."""
    return _rows(*[[button(label, f"req:{kind}:{rid}")] for kind, rid, label in items])


def support(url: str) -> InlineKeyboardMarkup | None:
    return _rows([url_button("Написать в поддержку", url)]) if url else None
