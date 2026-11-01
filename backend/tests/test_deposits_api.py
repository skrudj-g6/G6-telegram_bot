import pytest

from app.services import players

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100
PDF = b"%PDF-1.7\n" + b"0" * 100


def detail(response) -> dict:
    return response.json()["detail"]


@pytest.fixture
def player(db):
    players.register_user(db, telegram_id=100, username="aliya", first_name="Алия")
    account = players.link_poker_account(db, telegram_id=100, raw_player_id="1234-5678")
    players.approve_poker_account(db, account_id=account.id)
    return 100


def create(client, headers, tg=100, **overrides):
    body = {"method": "fiat", "amount": 5000, "idempotency_key": "key-00000001"}
    body.update(overrides)
    return client.post(f"/bot/v1/users/{tg}/deposits", json=body, headers=headers)


def upload(client, headers, request_id, data=JPEG, name="check.jpg", tg=100):
    return client.post(
        f"/bot/v1/users/{tg}/deposits/{request_id}/receipt",
        files={"file": (name, data, "application/octet-stream")},
        headers=headers,
    )


# ---------- авторизация ----------


def test_endpoints_require_service_token(client, player):
    calls = [
        client.get("/bot/v1/settings/limits"),
        client.get("/bot/v1/quotes/usdt-deposit?usdt_amount=10"),
        client.post("/bot/v1/users/100/deposits", json={}),
        client.get("/bot/v1/users/100/deposits"),
        client.get("/bot/v1/users/100/deposits/1"),
        client.post("/bot/v1/users/100/deposits/1/cancel"),
        client.post("/bot/v1/users/100/deposits/1/receipt", files={"file": ("a.jpg", JPEG)}),
    ]
    for response in calls:
        assert response.status_code == 401
        assert detail(response)["code"] == "unauthorized"


# ---------- лимиты ----------


def test_limits_endpoint(client, bot_headers):
    response = client.get("/bot/v1/settings/limits", headers=bot_headers)
    assert response.status_code == 200
    assert response.json() == {
        "deposit": {"min": 1000, "max": 2_000_000},
        "withdrawal": {"min": 1000, "max": 2_000_000},
        "commission": {"deposit": "0", "withdrawal": "0"},
    }


# ---------- создание ----------


def test_create_returns_requisites(client, bot_headers, player, provider):
    response = create(client, bot_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "awaiting_receipt"
    assert body["amount"] == 5000
    assert body["payment_details"]["bank"] == "Тестовый банк"
    assert body["receipt_uploaded"] is False
    assert body["expires_at"].endswith(("Z", "+00:00"))
    assert set(body) == {
        "id",
        "method",
        "amount",
        "usdt_amount",
        "exchange_rate",
        "commission_percent",
        "commission_amount",
        "credit_amount",
        "status",
        "payment_details",
        "expires_at",
        "receipt_uploaded",
        "reject_reason",
        "created_at",
    }


def test_replay_with_same_key_returns_200_and_same_request(client, bot_headers, player, provider):
    first = create(client, bot_headers)
    second = create(client, bot_headers)
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["id"] == second.json()["id"]


def test_no_requisites_is_503(client, bot_headers, player):
    """Q-22: платёжка не подключена."""
    response = create(client, bot_headers)
    assert response.status_code == 503
    assert detail(response)["code"] == "no_requisites_available"
    assert client.get("/bot/v1/users/100/deposits", headers=bot_headers).json() == []


def test_amount_out_of_range_reports_limits(client, bot_headers, player, provider):
    response = create(client, bot_headers, amount=500)
    assert response.status_code == 422
    assert detail(response) == {"code": "amount_out_of_range", "min": 1000, "max": 2_000_000}


@pytest.mark.parametrize(
    "overrides",
    [
        {"amount": "5000"},
        {"amount": 5000.5},
        {"amount": 0},
        {"amount": -10},
        {"amount": None},
        {"method": "cash"},
        {"method": ""},
        {"idempotency_key": "short"},
        {"idempotency_key": "has spaces here!"},
    ],
)
def test_invalid_payload_is_422(client, bot_headers, player, provider, overrides):
    assert create(client, bot_headers, **overrides).status_code == 422
    assert provider.calls == []


def test_pending_account_cannot_create_deposit(client, bot_headers, db, provider):
    players.register_user(db, telegram_id=7, username=None, first_name="Новый")
    players.link_poker_account(db, telegram_id=7, raw_player_id="7777-7777")
    response = create(client, bot_headers, tg=7)
    assert response.status_code == 403
    assert detail(response)["code"] == "account_not_approved"


def test_unknown_user_is_404(client, bot_headers, provider):
    assert create(client, bot_headers, tg=999).status_code == 404


def test_second_open_request_is_409(client, bot_headers, player, provider):
    create(client, bot_headers)
    response = create(client, bot_headers, idempotency_key="key-00000002")
    assert response.status_code == 409
    assert detail(response)["code"] == "deposit_awaiting_receipt"


def test_non_positive_telegram_id_is_422(client, bot_headers):
    assert client.get("/bot/v1/users/0/deposits", headers=bot_headers).status_code == 422


# ---------- чек ----------


def test_receipt_flow_to_operator_queue(client, bot_headers, player, provider):
    request_id = create(client, bot_headers).json()["id"]
    response = upload(client, bot_headers, request_id)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["receipt_uploaded"] is True
    assert body["payment_details"] is None  # реквизиты после оплаты больше не показываются


def test_pdf_receipt_is_accepted(client, bot_headers, player, provider):
    request_id = create(client, bot_headers).json()["id"]
    assert upload(client, bot_headers, request_id, data=PDF, name="check.pdf").status_code == 200


def test_declared_filename_is_irrelevant_only_content_matters(client, bot_headers, player, provider):
    request_id = create(client, bot_headers).json()["id"]
    response = upload(client, bot_headers, request_id, data=b"not an image", name="check.jpg")
    assert response.status_code == 422
    assert detail(response)["code"] == "invalid_receipt"


def test_oversized_receipt_is_413(client, bot_headers, player, provider):
    request_id = create(client, bot_headers).json()["id"]
    response = upload(client, bot_headers, request_id, data=JPEG + b"0" * (10 * 1024 * 1024))
    assert response.status_code == 413
    assert detail(response)["code"] == "receipt_too_large"


def test_second_receipt_is_409(client, bot_headers, player, provider):
    request_id = create(client, bot_headers).json()["id"]
    upload(client, bot_headers, request_id)
    response = upload(client, bot_headers, request_id)
    assert response.status_code == 409
    assert detail(response)["code"] == "invalid_transition"


def test_missing_file_is_422(client, bot_headers, player, provider):
    request_id = create(client, bot_headers).json()["id"]
    response = client.post(
        f"/bot/v1/users/100/deposits/{request_id}/receipt", headers=bot_headers
    )
    assert response.status_code == 422


# ---------- отмена ----------


def test_cancel_before_receipt(client, bot_headers, player, provider):
    request_id = create(client, bot_headers).json()["id"]
    response = client.post(f"/bot/v1/users/100/deposits/{request_id}/cancel", headers=bot_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_after_receipt_is_409(client, bot_headers, player, provider):
    request_id = create(client, bot_headers).json()["id"]
    upload(client, bot_headers, request_id)
    response = client.post(f"/bot/v1/users/100/deposits/{request_id}/cancel", headers=bot_headers)
    assert response.status_code == 409
    assert detail(response)["code"] == "invalid_transition"


# ---------- чтение и чужие заявки ----------


def test_get_and_list(client, bot_headers, player, provider):
    request_id = create(client, bot_headers).json()["id"]
    one = client.get(f"/bot/v1/users/100/deposits/{request_id}", headers=bot_headers)
    assert one.status_code == 200 and one.json()["id"] == request_id
    listed = client.get("/bot/v1/users/100/deposits", headers=bot_headers).json()
    assert [r["id"] for r in listed] == [request_id]


def test_other_players_request_is_404(client, bot_headers, player, provider, db):
    players.register_user(db, telegram_id=200, username=None, first_name="Другой")
    request_id = create(client, bot_headers).json()["id"]
    for method, path in [
        ("get", f"/bot/v1/users/200/deposits/{request_id}"),
        ("post", f"/bot/v1/users/200/deposits/{request_id}/cancel"),
    ]:
        response = getattr(client, method)(path, headers=bot_headers)
        assert response.status_code == 404
        assert detail(response)["code"] == "request_not_found"
    assert upload(client, bot_headers, request_id, tg=200).status_code == 404


def test_blocked_player_gets_403_everywhere(client, bot_headers, player, provider, db):
    from app.models import UserStatus

    request_id = create(client, bot_headers).json()["id"]
    players.get_user(db, 100).status = UserStatus.BLOCKED
    db.commit()
    for response in [
        create(client, bot_headers, idempotency_key="key-00000009"),
        client.get("/bot/v1/users/100/deposits", headers=bot_headers),
        client.post(f"/bot/v1/users/100/deposits/{request_id}/cancel", headers=bot_headers),
        upload(client, bot_headers, request_id),
    ]:
        assert response.status_code == 403
        assert detail(response)["code"] == "user_blocked"


# ---------- крипта: ввод в USDT, пересчёт по курсу ----------


def create_crypto(client, headers, usdt="10.00", tg=100, **overrides):
    body = {"method": "crypto", "usdt_amount": usdt, "idempotency_key": "key-crypto-0001"}
    body.update(overrides)
    return client.post(f"/bot/v1/users/{tg}/deposits", json=body, headers=headers)


def test_crypto_deposit_shows_usdt_and_tenge(client, bot_headers, player, provider, usdt_rate):
    response = create_crypto(client, bot_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["method"] == "crypto"
    assert body["usdt_amount"] == "10.00"
    assert body["exchange_rate"] == "500.5"
    assert body["amount"] == 5005  # тенге по курсу
    assert body["payment_details"]["method"] == "crypto"


def test_crypto_accepts_json_number_and_string(client, bot_headers, player, provider, usdt_rate):
    first = create_crypto(client, bot_headers, usdt=12.5)
    assert first.status_code == 201
    assert first.json()["usdt_amount"] == "12.50"
    client.post(
        f"/bot/v1/users/100/deposits/{first.json()['id']}/cancel", headers=bot_headers
    )
    second = create_crypto(client, bot_headers, usdt="12.50", idempotency_key="key-crypto-0002")
    assert second.status_code == 201 and second.json()["amount"] == 6256  # 12.5 × 500.5 = 6256.25


def test_fiat_response_has_no_crypto_fields(client, bot_headers, player, provider):
    body = create(client, bot_headers).json()
    assert (body["usdt_amount"], body["exchange_rate"]) == (None, None)


def test_crypto_without_rate_is_503(client, bot_headers, player, provider):
    response = create_crypto(client, bot_headers)
    assert response.status_code == 503
    assert detail(response)["code"] == "exchange_rate_unavailable"


def test_crypto_below_limit_reports_tenge_equivalent(client, bot_headers, player, provider, usdt_rate):
    response = create_crypto(client, bot_headers, usdt="1")
    assert response.status_code == 422
    assert detail(response) == {
        "code": "amount_out_of_range",
        "min": 1000,
        "max": 2_000_000,
        "amount_kzt": 500,
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"usdt": "10.123"},  # больше двух знаков
        {"usdt": "0"},
        {"usdt": "-5"},
        {"usdt": "abc"},
        {"usdt": None},
        {"amount": 5000},  # тенге при crypto не принимаются
        {"usdt": "10", "amount": 5000},
    ],
)
def test_invalid_crypto_payload_is_422(client, bot_headers, player, provider, usdt_rate, overrides):
    assert create_crypto(client, bot_headers, **overrides).status_code == 422
    assert provider.calls == []


def test_fiat_with_usdt_amount_is_422(client, bot_headers, player, provider, usdt_rate):
    assert create(client, bot_headers, usdt_amount="10").status_code == 422


# ---------- расчёт тенге до подтверждения ----------


def test_quote_endpoint(client, bot_headers, usdt_rate):
    response = client.get("/bot/v1/quotes/usdt-deposit?usdt_amount=10", headers=bot_headers)
    assert response.status_code == 200
    assert response.json() == {
        "usdt_amount": "10.00",
        "rate": "500.5",
        "kzt_amount": 5005,
        "min": 1000,
        "max": 2_000_000,
        "within_limits": True,
        "commission_percent": "0",
        "commission_amount": 0,
        "credit_amount": 5005,
    }


def test_quote_flags_amount_below_limit(client, bot_headers, usdt_rate):
    body = client.get("/bot/v1/quotes/usdt-deposit?usdt_amount=1", headers=bot_headers).json()
    assert (body["kzt_amount"], body["within_limits"]) == (500, False)


def test_quote_without_rate_is_503(client, bot_headers):
    response = client.get("/bot/v1/quotes/usdt-deposit?usdt_amount=10", headers=bot_headers)
    assert response.status_code == 503
    assert detail(response)["code"] == "exchange_rate_unavailable"


@pytest.mark.parametrize("value", ["0", "-1", "abc", "1.234", ""])
def test_quote_rejects_invalid_amount(client, bot_headers, usdt_rate, value):
    response = client.get(f"/bot/v1/quotes/usdt-deposit?usdt_amount={value}", headers=bot_headers)
    assert response.status_code == 422


def test_quote_requires_service_token(client, usdt_rate):
    assert client.get("/bot/v1/quotes/usdt-deposit?usdt_amount=10").status_code == 401
