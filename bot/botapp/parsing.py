"""Разбор ввода игрока. Окончательную проверку делает backend: здесь только то, что нужно,
чтобы не отправлять заведомый мусор и дать понятную подсказку."""

import re
from decimal import Decimal, InvalidOperation

_AMOUNT_RE = re.compile(r"^[0-9]{1,12}$")
_USDT_RE = re.compile(r"^[0-9]{1,10}([.,][0-9]{1,2})?$")
_NAME_STRIP = re.compile(r"\s+")
_CURRENCY_TAIL = re.compile(r"(?i)\s*(₸|тг|тенге|kzt)\.?$")


def parse_amount(text: str | None) -> int | None:
    """Целые тенге: «5000», «5 000», «5000 ₸». Дроби, минус и буквы не принимаются."""
    if not text:
        return None
    value = _CURRENCY_TAIL.sub("", text.strip())
    value = re.sub(r"[   ]", "", value)
    if not _AMOUNT_RE.fullmatch(value):
        return None
    number = int(value)
    return number if number > 0 else None


def parse_usdt(text: str | None) -> str | None:
    """USDT: до двух знаков после точки или запятой. Возвращает строку вида «12.34»."""
    if not text:
        return None
    value = re.sub(r"(?i)\s*usdt\s*$", "", text.strip()).replace(" ", "")
    if not _USDT_RE.fullmatch(value):
        return None
    value = value.replace(",", ".")
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    return format(number, "f") if number > 0 else None


def clean_name(text: str | None) -> str | None:
    """Имя получателя: пробелы схлопываются, длина 2–100. Допустимые символы проверяет backend."""
    if not text:
        return None
    name = _NAME_STRIP.sub(" ", text).strip()
    return name if 2 <= len(name) <= 100 else None
