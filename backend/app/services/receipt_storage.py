"""Хранение чеков на диске (Q-23: фото и PDF, срок хранения — неделя).

Имя файла генерируется здесь (uuid), пользовательские имена не используются:
обход каталога невозможен. Тип определяется по содержимому, а не по заявленному
content-type.
"""

import os
import re
import uuid
from pathlib import Path

from app.core.config import get_settings

MAX_RECEIPT_BYTES = 10 * 1024 * 1024

_SIGNATURES: tuple[tuple[bytes, str, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"%PDF-", "application/pdf", ".pdf"),
)
_FILENAME_RE = re.compile(r"[0-9a-f]{32}\.(jpg|png|pdf)")


def sniff(data: bytes) -> tuple[str, str] | None:
    """(content_type, расширение) по сигнатуре файла; None — формат не поддерживается."""
    for signature, content_type, extension in _SIGNATURES:
        if data.startswith(signature):
            return content_type, extension
    return None


def _root() -> Path:
    return Path(get_settings().receipts_dir)


def save(data: bytes, extension: str) -> str:
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{extension}"
    temp = root / f"{filename}.part"
    temp.write_bytes(data)
    os.replace(temp, root / filename)  # файл появляется целиком или не появляется
    return filename


def path_for(filename: str) -> Path:
    """Путь к файлу чека (для авторизованной выдачи оператору на этапе 5/8)."""
    if not _FILENAME_RE.fullmatch(filename):
        raise ValueError("Недопустимое имя файла чека")
    return _root() / filename


def delete(filename: str) -> None:
    """Удаляет файл; отсутствие файла не ошибка. Чужие пути игнорируются."""
    if not _FILENAME_RE.fullmatch(filename):
        return
    (_root() / filename).unlink(missing_ok=True)
