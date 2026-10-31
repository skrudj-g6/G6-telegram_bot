from sqlalchemy import select

from app.models import PokerAccount, User, UserStatus
from app.services import players

REGISTER = "/bot/v1/users/register"


def register(client, headers, tg=100, username="aliya", name="Алия"):
    return client.post(
        REGISTER,
        json={"telegram_id": tg, "username": username, "first_name": name},
        headers=headers,
    )


def link(client, headers, tg=100, player_id="1234-5678"):
    return client.put(
        f"/bot/v1/users/{tg}/poker-account", json={"player_id": player_id}, headers=headers
    )


def detail_code(response) -> str:
    return response.json()["detail"]["code"]


# ---------- внутренняя авторизация ----------


def test_endpoints_require_service_token(client):
    calls = [
        client.post(REGISTER, json={"telegram_id": 1, "first_name": "A"}),
        client.get("/bot/v1/users/1"),
        client.put("/bot/v1/users/1/poker-account", json={"player_id": "1234-5678"}),
    ]
    for response in calls:
        assert response.status_code == 401
        assert detail_code(response) == "unauthorized"


def test_wrong_service_token_is_refused(client):
    response = client.get("/bot/v1/users/1", headers={"X-Service-Token": "wrong-token-value"})
    assert response.status_code == 401


def test_unauthorized_request_creates_nothing(client, db):
    client.post(REGISTER, json={"telegram_id": 1, "first_name": "A"})
    assert db.scalars(select(User)).all() == []


# ---------- регистрация ----------


def test_register_returns_201_then_200(client, bot_headers):
    first = register(client, bot_headers)
    assert first.status_code == 201
    assert first.json()["created"] is True
    assert first.json()["poker_account"] is None

    second = register(client, bot_headers)
    assert second.status_code == 200
    assert second.json()["created"] is False


def test_register_validates_input(client, bot_headers):
    bad_payloads = [
        {"telegram_id": 0, "first_name": "A"},
        {"telegram_id": -5, "first_name": "A"},
        {"telegram_id": "abc", "first_name": "A"},
        {"telegram_id": 1},
        {"telegram_id": 1, "first_name": ""},
    ]
    for payload in bad_payloads:
        response = client.post(REGISTER, json=payload, headers=bot_headers)
        assert response.status_code == 422, payload


# ---------- профиль (/start для уже зарегистрированного, Q-20) ----------


def test_profile_of_unknown_user_is_404(client, bot_headers):
    response = client.get("/bot/v1/users/999", headers=bot_headers)
    assert response.status_code == 404
    assert detail_code(response) == "user_not_found"


def test_profile_contains_only_public_fields(client, bot_headers):
    register(client, bot_headers)
    link(client, bot_headers)
    body = client.get("/bot/v1/users/100", headers=bot_headers).json()
    assert set(body) == {
        "telegram_id",
        "username",
        "first_name",
        "status",
        "registered_at",
        "poker_account",
    }
    assert set(body["poker_account"]) == {
        "club_id",
        "player_id",
        "status",
        "reject_reason",
        "created_at",
    }


def test_registered_player_is_recognised_after_linking(client, bot_headers):
    """Повторный /start: игрок уже в системе, воронку заново не проходит."""
    register(client, bot_headers)
    link(client, bot_headers)
    again = register(client, bot_headers)
    assert again.status_code == 200
    assert again.json()["created"] is False
    assert again.json()["poker_account"]["player_id"] == "1234-5678"
    assert again.json()["poker_account"]["status"] == "pending"


# ---------- привязка игрового ID ----------


def test_link_poker_account(client, bot_headers):
    register(client, bot_headers)
    response = link(client, bot_headers)
    assert response.status_code == 200
    assert response.json()["player_id"] == "1234-5678"
    assert response.json()["club_id"] == "692609"
    assert response.json()["status"] == "pending"


def test_link_invalid_format_is_422(client, bot_headers):
    register(client, bot_headers)
    response = link(client, bot_headers, player_id="12-34")
    assert response.status_code == 422
    assert detail_code(response) == "invalid_player_id"


def test_link_for_unknown_user_is_404(client, bot_headers):
    response = link(client, bot_headers, tg=555)
    assert response.status_code == 404
    assert detail_code(response) == "user_not_found"


def test_link_duplicate_player_id_is_409(client, bot_headers):
    register(client, bot_headers, tg=100)
    register(client, bot_headers, tg=200, username="b", name="Бек")
    assert link(client, bot_headers, tg=100).status_code == 200
    response = link(client, bot_headers, tg=200)
    assert response.status_code == 409
    assert detail_code(response) == "player_id_taken"
    assert response.json()["detail"]["blocked"] is True

    # Q-27: нарушитель заблокирован, владелец ID — нет.
    offender = client.get("/bot/v1/users/200", headers=bot_headers).json()
    assert offender["status"] == "blocked"
    assert offender["poker_account"] is None
    assert client.get("/bot/v1/users/100", headers=bot_headers).json()["status"] == "active"
    retry = link(client, bot_headers, tg=200, player_id="8765-4321")
    assert retry.status_code == 403
    assert detail_code(retry) == "user_blocked"


def test_link_blocked_user_is_403(client, bot_headers, db):
    register(client, bot_headers)
    user = db.scalar(select(User))
    user.status = UserStatus.BLOCKED
    db.commit()
    response = link(client, bot_headers)
    assert response.status_code == 403
    assert detail_code(response) == "user_blocked"


def test_link_after_approval_is_409(client, bot_headers, db):
    register(client, bot_headers)
    link(client, bot_headers)
    account_id = db.scalar(select(PokerAccount.id))
    players.approve_poker_account(db, account_id=account_id)

    response = link(client, bot_headers, player_id="9999-9999")
    assert response.status_code == 409
    assert detail_code(response) == "account_locked"

    profile = client.get("/bot/v1/users/100", headers=bot_headers).json()
    assert profile["poker_account"]["status"] == "approved"
    assert profile["poker_account"]["player_id"] == "1234-5678"
