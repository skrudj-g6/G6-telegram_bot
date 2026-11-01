"""Пароли и токены сотрудников (D-4) на стандартной библиотеке.

Пароли: scrypt с солью. Access-токен: JWT HS256 (подпись HMAC-SHA256), живёт недолго.
Refresh-токен — случайная строка; в БД хранится только её SHA-256.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def password_is_acceptable(password: str) -> bool:
    return MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64e(salt)}${_b64e(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode(), salt=_b64d(salt), n=int(n), r=int(r), p=int(p), dklen=32
        )
        return hmac.compare_digest(actual, _b64d(digest))
    except (ValueError, TypeError):
        return False


# Хеш несуществующего пользователя: вход с неизвестным логином занимает столько же времени.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def encode_jwt(claims: dict, secret: str) -> str:
    header = _b64e(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64e(json.dumps(claims, separators=(",", ":")).encode())
    signature = hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    return f"{header}.{body}.{_b64e(signature)}"


def decode_jwt(token: str, secret: str, now: float | None = None) -> dict | None:
    """Claims токена или None, если подпись, алгоритм или срок не подходят."""
    try:
        header_part, body_part, signature_part = token.split(".")
        header = json.loads(_b64d(header_part))
        if header.get("alg") != "HS256":  # alg=none и другие алгоритмы не принимаются
            return None
        expected = hmac.new(
            secret.encode(), f"{header_part}.{body_part}".encode(), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected, _b64d(signature_part)):
            return None
        claims = json.loads(_b64d(body_part))
        if not isinstance(claims, dict):
            return None
        exp = claims.get("exp")
        if isinstance(exp, bool) or not isinstance(exp, (int, float)):
            return None
        if (now if now is not None else time.time()) >= exp:
            return None
        return claims
    except (ValueError, TypeError, UnicodeDecodeError):
        return None


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
