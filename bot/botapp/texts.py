"""Тексты и форматирование для игрока. Все пользовательские значения экранируются (HTML)."""

from datetime import datetime, timezone
from html import escape as _escape
from zoneinfo import ZoneInfo

NO_REQUISITES = "😔 Сейчас нет свободных реквизитов. Обратитесь через 10 минут."
UNAVAILABLE = "⚠️ Сервис временно недоступен. Попробуйте через несколько минут."
GENERIC_ERROR = "⚠️ Что-то пошло не так. Попробуйте позже."

DEPOSIT_STATUS = {
    "awaiting_receipt": "⏳ Ожидает чек",
    "pending": "🕓 На проверке",
    "processing": "🔄 В обработке",
    "completed": "✅ Выполнена",
    "rejected": "❌ Отклонена",
    "cancelled": "🚫 Отменена",
    "expired": "⌛ Время вышло",
}
WITHDRAWAL_STATUS = {
    "pending": "🕓 На проверке",
    "processing": "🔄 В обработке",
    "completed": "✅ Выполнена",
    "rejected": "❌ Отклонена",
    "cancelled": "🚫 Отменена",
}
METHOD = {"fiat": "Тенге", "crypto": "Криптовалюта (USDT)"}

# Статусы, в которых игрок может отменить заявку (Q-5, Q-36).
DEPOSIT_CANCELLABLE = {"awaiting_receipt"}
WITHDRAWAL_CANCELLABLE = {"pending"}


def e(value) -> str:
    return _escape(str(value), quote=False)


def money(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " ₸"


def percent_note(percent: str, delta: int) -> str | None:
    """Строка про процент клуба: бонус (+) или комиссия (−). None, если процента нет (Q-34)."""
    if delta == 0:
        return None
    shown = percent if percent.startswith("-") else f"+{percent}"
    label = "Бонус" if delta > 0 else "Комиссия"
    return f"{label} {e(shown)}%: {'+' if delta > 0 else '−'}{money(abs(delta))}"


def local_time(iso: str, tz: ZoneInfo) -> str:
    value = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(tz).strftime("%d.%m %H:%M")


def clock_time(iso: str, tz: ZoneInfo) -> str:
    return local_time(iso, tz)[-5:]


def details_lines(details: dict | None) -> str:
    """Реквизиты от платёжки показываются как пришли: набор полей определяет платёжка."""
    if not details:
        return ""
    return "\n".join(f"{e(key)}: <code>{e(value)}</code>" for key, value in details.items())


# --- Карточки ---------------------------------------------------------------------


def deposit_created(d: dict, tz: ZoneInfo) -> str:
    lines = ["✅ <b>Заявка на пополнение создана</b>", ""]
    if d.get("usdt_amount"):
        lines.append(f"Сумма: <b>{e(d['usdt_amount'])} USDT</b> ≈ {money(d['amount'])}")
        lines.append(f"Курс: {e(d['exchange_rate'])} ₸ за 1 USDT")
    else:
        lines.append(f"Сумма: <b>{money(d['amount'])}</b>")
    note = percent_note(d["commission_percent"], d["commission_amount"])
    if note:
        lines.append(note)
    lines.append(f"К зачислению на игровой счёт: <b>{money(d['credit_amount'])}</b>")
    if d.get("payment_details"):
        lines += ["", "💳 <b>Реквизиты для оплаты:</b>", details_lines(d["payment_details"])]
    lines += [
        "",
        f"📎 Оплатите и отправьте сюда чек (фото или PDF) <b>до {clock_time(d['expires_at'], tz)}</b>. "
        "Если чек не придёт вовремя, заявка закроется автоматически.",
    ]
    return "\n".join(lines)


def deposit_card(d: dict, tz: ZoneInfo) -> str:
    lines = [
        f"💰 <b>Пополнение №{d['id']}</b>",
        f"Статус: {DEPOSIT_STATUS.get(d['status'], e(d['status']))}",
        f"Способ: {METHOD.get(d['method'], e(d['method']))}",
    ]
    if d.get("usdt_amount"):
        lines.append(f"Сумма: {e(d['usdt_amount'])} USDT ≈ {money(d['amount'])}")
    else:
        lines.append(f"Сумма: {money(d['amount'])}")
    lines.append(f"К зачислению: {money(d['credit_amount'])}")
    lines.append(f"Создана: {local_time(d['created_at'], tz)}")
    if d["status"] == "awaiting_receipt":
        if d.get("payment_details"):
            lines += ["", "💳 <b>Реквизиты:</b>", details_lines(d["payment_details"])]
        lines.append(f"\n📎 Отправьте чек до {clock_time(d['expires_at'], tz)}.")
    if d.get("reject_reason"):
        lines.append(f"Причина отказа: {e(d['reject_reason'])}")
    return "\n".join(lines)


def withdrawal_summary(q: dict, method: str, holder: str | None, bank: str | None) -> str:
    lines = ["📤 <b>Проверьте заявку на вывод</b>", ""]
    lines.append(f"Способ: {METHOD.get(method, e(method))}")
    lines.append(f"Сумма вывода: <b>{money(q['amount'])}</b>")
    note = percent_note(q["commission_percent"], q["commission_amount"])
    if note:
        lines.append(note)
    lines.append(f"Вы получите: <b>{money(q['payout_amount'])}</b>")
    if holder:
        lines.append(f"Получатель: {e(holder)}")
    if bank:
        lines.append(f"Банк: {e(bank)}")
    return "\n".join(lines)


def withdrawal_created(w: dict) -> str:
    lines = ["✅ <b>Заявка на вывод создана</b>", ""]
    lines.append(f"Сумма вывода: {money(w['amount'])}")
    note = percent_note(w["commission_percent"], w["commission_amount"])
    if note:
        lines.append(note)
    lines.append(f"Вы получите: <b>{money(w['payout_amount'])}</b>")
    if w.get("holder_name"):
        lines.append(f"Получатель: {e(w['holder_name'])}")
    if w.get("bank_name"):
        lines.append(f"Банк: {e(w['bank_name'])}")
    if w.get("payment_details"):
        lines += ["", details_lines(w["payment_details"])]
    lines += ["", "Оператор обработает заявку. Статус смотрите в «Мои заявки»."]
    return "\n".join(lines)


def withdrawal_card(w: dict, tz: ZoneInfo) -> str:
    lines = [
        f"📤 <b>Вывод №{w['id']}</b>",
        f"Статус: {WITHDRAWAL_STATUS.get(w['status'], e(w['status']))}",
        f"Способ: {METHOD.get(w['method'], e(w['method']))}",
        f"Сумма вывода: {money(w['amount'])}",
        f"Вы получите: {money(w['payout_amount'])}",
    ]
    if w.get("holder_name"):
        lines.append(f"Получатель: {e(w['holder_name'])}")
    if w.get("bank_name"):
        lines.append(f"Банк: {e(w['bank_name'])}")
    lines.append(f"Создана: {local_time(w['created_at'], tz)}")
    if w.get("reject_reason"):
        lines.append(f"Причина отказа: {e(w['reject_reason'])}")
    return "\n".join(lines)


def request_line(kind: str, r: dict, tz: ZoneInfo) -> str:
    statuses = DEPOSIT_STATUS if kind == "dep" else WITHDRAWAL_STATUS
    icon = "💰" if kind == "dep" else "📤"
    return (
        f"{icon} №{r['id']} · {money(r['amount'])} · "
        f"{statuses.get(r['status'], e(r['status']))} · {local_time(r['created_at'], tz)}"
    )


def profile_card(user: dict, club_id: str) -> str:
    account = user.get("poker_account")
    lines = ["👤 <b>Мой профиль</b>", f"Клуб: {e(club_id)}"]
    if account is None:
        lines.append("Игровой ID: не указан")
    else:
        status = {
            "pending": "ожидает подтверждения",
            "approved": "подтверждён",
            "rejected": "отклонён",
        }.get(account["status"], e(account["status"]))
        lines.append(f"Игровой ID: <code>{e(account['player_id'])}</code> ({status})")
        if account.get("reject_reason"):
            lines.append(f"Причина отказа: {e(account['reject_reason'])}")
    return "\n".join(lines)


def limits_hint(limits: dict, kind: str) -> str:
    low, high = limits[kind]["min"], limits[kind]["max"]
    return f"от {money(low)} до {money(high)}"


# --- Ошибки -----------------------------------------------------------------------

_ERRORS = {
    "no_requisites_available": NO_REQUISITES,
    "exchange_rate_unavailable": "📉 Курс USDT временно недоступен. Попробуйте позже или пополните в тенге.",
    "deposit_awaiting_receipt": (
        "У вас уже есть заявка, ожидающая чек. Отправьте чек или отмените заявку в «Мои заявки»."
    ),
    "withdrawal_already_open": (
        "У вас уже есть открытая заявка на вывод. Дождитесь обработки или отмените её в «Мои заявки»."
    ),
    "account_not_approved": "Ваш игровой ID ещё не подтверждён администратором.",
    "user_blocked": "🚫 Доступ к боту закрыт. Для уточнения обратитесь в поддержку.",
    "invalid_holder_name": "Имя указано неверно. Используйте буквы, пробел, дефис, точку.",
    "invalid_bank": "Выберите банк из списка.",
    "invalid_amount": "Некорректная сумма.",
    "request_expired": "⌛ Время на отправку чека вышло, заявка закрыта. Создайте новую.",
    "invalid_transition": "Статус заявки уже изменился. Откройте «Мои заявки».",
    "invalid_receipt": "Не удалось принять файл. Отправьте фото или PDF (JPEG, PNG, PDF).",
    "receipt_too_large": "Файл больше 10 МБ. Отправьте файл поменьше.",
    "request_not_found": "Заявка не найдена.",
    "invalid_player_id": "Неверный формат. Нужен игровой ID вида XXXX-XXXX (только цифры).",
    "account_locked": "Игровой ID уже подтверждён, изменить его может только администратор.",
    "user_not_found": "Сначала отправьте /start.",
}


def error_text(code: str, extra: dict | None = None) -> str:
    extra = extra or {}
    if code == "amount_out_of_range" and "amount_kzt" in extra:
        return (
            f"Эквивалент {money(extra['amount_kzt'])} вне лимитов: "
            f"от {money(extra.get('min', 0))} до {money(extra.get('max', 0))}."
        )
    if code == "amount_out_of_range":
        return f"Сумма должна быть от {money(extra.get('min', 0))} до {money(extra.get('max', 0))}."
    if code == "player_id_taken":
        if extra.get("blocked"):
            return "🚫 Этот игровой ID уже зарегистрирован другим игроком. Доступ к боту закрыт."
        return (
            "⚠️ Этот игровой ID уже зарегистрирован другим игроком. "
            "Проверьте ID. При повторной попытке доступ к боту будет закрыт."
        )
    return _ERRORS.get(code, GENERIC_ERROR)
