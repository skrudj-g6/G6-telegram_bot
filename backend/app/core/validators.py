import re

# Только ASCII-цифры: `\d` в Python принимает и другие Unicode-цифры (баг B-6 из AUDIT.md).
_PLAYER_ID_RE = re.compile(r"[0-9]{4}-[0-9]{4}")


def normalize_player_id(raw: str) -> str | None:
    """Возвращает игровой ID в формате XXXX-XXXX или None, если формат неверный."""
    value = raw.strip()
    if _PLAYER_ID_RE.fullmatch(value):
        return value
    return None
