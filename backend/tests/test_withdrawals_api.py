import pytest

from app.services import players


def detail(response) -> dict:
    return response.json()["detail"]


@pytest.fixture
def player(db):
    players.register_user(db, telegram_id=100, username="aliya", first_name="Алия")
    account = players.link_poker_account(db, telegram_id=100, raw_player_id="1234-5678")
    players.approve_poker_account(db, account_id=account.id)
    return 100


def create(client, headers, banks, tg=100, **overrides):
    body = {
        "method": "fiat",
        "amount": 5000,
        "holder_name": "Алия Серикова",
        "bank_id": banks["Kaspi Bank"],
        "idempotency_key": "key-00000001",
    }
    body.update(overrides)
    body = {k: v for k, v in body.items() if v is not None}
    return client.post(f"/bot/v1/users/{tg}/withdrawals", json=body, headers=headers)


def test_endpoints_require_service_token(client, player):
    calls = [
        client.get("/bot/v1/banks"),
        client.get("/bot/v1/quotes/withdrawal?amount=5000"),
        client.post("/bot/v1/users/100/withdrawals", json={}),
        client.get("/bot/v1/users/100/withdrawals"),
        client.get("/bot/v1/users/100/withdrawals/1"),
        client.post("/bot/v1/users/100/withdrawals/1/cancel"),
    ]
    for response in calls:
        assert response.status_code == 401
        assert detail(response)["code"] == "unauthorized"


def test_banks_list(client, bot_headers, banks):
    response = client.get("/bot/v1/banks", headers=bot_headers)
    assert response.status_code == 200
    assert [b["name"] for b in response.json()] == [
        "Kaspi Bank", "Halyk Bank", "Банк ЦентрКредит", "ForteBank", "Freedom Bank Kazakhstan",
    ]
    assert set(response.json()[0]) == {"id", "name"}


def test_create_fiat_withdrawal(client, bot_headers, player, banks):
    response = create(client, bot_headers, banks)
    assert response.status_code == 201
    body = response.json()
    assert (body["status"], body["amount"], body["payout_amount"]) == ("pending", 5000, 5000)
    assert (body["holder_name"], body["bank_name"]) == ("Алия Серикова", "Kaspi Bank")
    assert set(body) == {
        "id", "method", "amount", "commission_percent", "commission_amount", "payout_amount",
        "holder_name", "bank_name", "payment_details", "status", "reject_reason", "created_at",
    }


def test_replay_returns_200_and_same_request(client, bot_headers, player, banks):
    first = create(client, bot_headers, banks)
    second = create(client, bot_headers, banks)
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["id"] == second.json()["id"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"amount": 0}, {"amount": -1}, {"amount": 5000.5}, {"amount": "5000"},
        {"holder_name": None}, {"bank_id": None}, {"method": "cash"},
        {"idempotency_key": "short"}, {"bank_id": "1"},
    ],
)
def test_invalid_payload_is_422(client, bot_headers, player, banks, overrides):
    assert create(client, bot_headers, banks, **overrides).status_code == 422


def test_bad_name_and_bank_have_codes(client, bot_headers, player, banks):
    r = create(client, bot_headers, banks, holder_name="12345")
    assert (r.status_code, detail(r)["code"]) == (422, "invalid_holder_name")
    r = create(client, bot_headers, banks, bank_id=9999)
    assert (r.status_code, detail(r)["code"]) == (422, "invalid_bank")


def test_amount_out_of_range_reports_limits(client, bot_headers, player, banks):
    r = create(client, bot_headers, banks, amount=500)
    assert r.status_code == 422
    assert detail(r) == {"code": "amount_out_of_range", "min": 1000, "max": 2_000_000}


def test_second_open_withdrawal_is_409(client, bot_headers, player, banks):
    create(client, bot_headers, banks)
    r = create(client, bot_headers, banks, idempotency_key="key-00000002")
    assert (r.status_code, detail(r)["code"]) == (409, "withdrawal_already_open")


def test_unapproved_player_is_403(client, bot_headers, db, banks):
    players.register_user(db, telegram_id=200, username=None, first_name="Новый")
    r = create(client, bot_headers, banks, tg=200)
    assert (r.status_code, detail(r)["code"]) == (403, "account_not_approved")


def test_crypto_without_psp_is_503(client, bot_headers, player):
    r = client.post(
        "/bot/v1/users/100/withdrawals",
        json={"method": "crypto", "amount": 5000, "idempotency_key": "key-00000001"},
        headers=bot_headers,
    )
    assert (r.status_code, detail(r)["code"]) == (503, "no_requisites_available")


def test_crypto_with_psp(client, bot_headers, player, crypto_payout):
    r = client.post(
        "/bot/v1/users/100/withdrawals",
        json={"method": "crypto", "amount": 5000, "idempotency_key": "key-00000001"},
        headers=bot_headers,
    )
    assert r.status_code == 201
    assert r.json()["payment_details"]["psp_ref"] == "TEST-1"


def test_crypto_with_name_is_422(client, bot_headers, player, crypto_payout):
    r = client.post(
        "/bot/v1/users/100/withdrawals",
        json={"method": "crypto", "amount": 5000, "holder_name": "Алия",
              "idempotency_key": "key-00000001"},
        headers=bot_headers,
    )
    assert r.status_code == 422


def test_quote_endpoint(client, bot_headers, db):
    from app.services import app_settings

    app_settings.set_str(db, "withdrawal_commission_percent", "3")
    db.commit()
    r = client.get("/bot/v1/quotes/withdrawal?amount=10000", headers=bot_headers)
    assert r.status_code == 200
    assert r.json() == {
        "amount": 10000, "min": 1000, "max": 2_000_000, "within_limits": True,
        "commission_percent": "3", "commission_amount": 300, "payout_amount": 10300,
    }
    assert client.get("/bot/v1/quotes/withdrawal?amount=0", headers=bot_headers).status_code == 422


def test_get_list_and_cancel(client, bot_headers, player, banks):
    created = create(client, bot_headers, banks).json()
    assert client.get("/bot/v1/users/100/withdrawals", headers=bot_headers).json()[0]["id"] == created["id"]
    one = client.get(f"/bot/v1/users/100/withdrawals/{created['id']}", headers=bot_headers)
    assert one.status_code == 200
    cancelled = client.post(f"/bot/v1/users/100/withdrawals/{created['id']}/cancel", headers=bot_headers)
    assert (cancelled.status_code, cancelled.json()["status"]) == (200, "cancelled")


def test_foreign_request_is_404(client, bot_headers, player, banks, db):
    players.register_user(db, telegram_id=200, username=None, first_name="Другой")
    created = create(client, bot_headers, banks).json()
    r = client.get(f"/bot/v1/users/200/withdrawals/{created['id']}", headers=bot_headers)
    assert (r.status_code, detail(r)["code"]) == (404, "request_not_found")
