import json
import time

from app.core import security

SECRET = "s" * 40


def test_password_hash_roundtrip_and_salt():
    first = security.hash_password("correct-horse-battery")
    second = security.hash_password("correct-horse-battery")
    assert first != second  # соль разная
    assert security.verify_password("correct-horse-battery", first)
    assert not security.verify_password("wrong-password-1", first)
    assert "correct-horse" not in first


def test_verify_password_rejects_garbage_hash():
    for bad in ["", "plain", "scrypt$1$2", "md5$a$b$c$d$e", "scrypt$x$y$z$a$b"]:
        assert security.verify_password("anything", bad) is False


def test_password_policy():
    assert not security.password_is_acceptable("short")
    assert security.password_is_acceptable("x" * 10)
    assert not security.password_is_acceptable("x" * 129)


def test_jwt_roundtrip():
    token = security.encode_jwt({"sub": "1", "exp": time.time() + 60}, SECRET)
    assert security.decode_jwt(token, SECRET)["sub"] == "1"


def test_jwt_rejects_wrong_secret_expired_and_tampered():
    token = security.encode_jwt({"sub": "1", "exp": time.time() + 60}, SECRET)
    assert security.decode_jwt(token, "x" * 40) is None
    expired = security.encode_jwt({"sub": "1", "exp": time.time() - 1}, SECRET)
    assert security.decode_jwt(expired, SECRET) is None
    header, body, signature = token.split(".")
    forged = security.encode_jwt({"sub": "2", "exp": time.time() + 60}, "y" * 40).split(".")[1]
    assert security.decode_jwt(f"{header}.{forged}.{signature}", SECRET) is None


def test_jwt_rejects_alg_none_and_missing_exp():
    header = security._b64e(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    body = security._b64e(json.dumps({"sub": "1", "exp": time.time() + 60}).encode())
    assert security.decode_jwt(f"{header}.{body}.", SECRET) is None
    assert security.decode_jwt(security.encode_jwt({"sub": "1"}, SECRET), SECRET) is None
    assert security.decode_jwt(security.encode_jwt({"sub": "1", "exp": True}, SECRET), SECRET) is None


def test_jwt_rejects_garbage():
    for bad in ["", "a.b", "a.b.c.d", "....", "not-a-token"]:
        assert security.decode_jwt(bad, SECRET) is None


def test_refresh_tokens_are_random_and_hashed():
    a, b = security.new_refresh_token(), security.new_refresh_token()
    assert a != b and len(a) >= 40
    assert security.hash_token(a) != a and len(security.hash_token(a)) == 64
