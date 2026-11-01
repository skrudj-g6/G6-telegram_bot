import pytest
from sqlalchemy import select

from app.models import AuditLog, User, UserStatus
from app.services import players


def detail(response) -> dict:
    return response.json()["detail"]


@pytest.fixture
def newcomer(db):
    """Игрок привязал ID и ждёт решения админа."""
    players.register_user(db, telegram_id=10, username="newbie", first_name="Новичок")
    players.link_poker_account(db, telegram_id=10, raw_player_id="1111-2222")
    return db.scalar(select(User).where(User.telegram_id == 10)).id


# ---------- игроки ----------


def test_player_endpoints_require_rights(client, auth, newcomer):
    assert client.get("/admin/v1/players").status_code == 401
    fin, _ = auth("finance", "fin1")
    assert client.get("/admin/v1/players", headers=fin).status_code == 200  # просмотр
    for action in ("approve", "unblock"):
        assert client.post(f"/admin/v1/players/{newcomer}/{action}", headers=fin).status_code == 403
    assert client.post(
        f"/admin/v1/players/{newcomer}/reject", json={"reason": "нет"}, headers=fin
    ).status_code == 403


def test_operator_works_with_players(client, auth, newcomer):
    """Q-46: оператор подтверждает игроков наравне с заявками."""
    op, _ = auth("operator", "op1")
    r = client.post(f"/admin/v1/players/{newcomer}/approve", headers=op)
    assert (r.status_code, r.json()["player"]["account_status"]) == (200, "approved")


def test_admin_approves_player_who_can_then_use_the_cashier(client, db, auth, bot_headers, newcomer, provider):
    headers, admin = auth("admin", "adm1")
    r = client.post(f"/admin/v1/players/{newcomer}/approve", headers=headers)
    assert r.status_code == 200 and r.json()["player"]["account_status"] == "approved"
    created = client.post(
        "/bot/v1/users/10/deposits",
        json={"method": "fiat", "amount": 5000, "idempotency_key": "key-00000001"},
        headers=bot_headers,
    )
    assert created.status_code == 201
    log = db.scalars(select(AuditLog).where(AuditLog.action == "player.approved")).all()
    assert [l.staff_id for l in log] == [admin.id]


def test_double_approve_is_409(client, auth, newcomer):
    headers, _ = auth("owner", "own1")
    client.post(f"/admin/v1/players/{newcomer}/approve", headers=headers)
    r = client.post(f"/admin/v1/players/{newcomer}/approve", headers=headers)
    assert (r.status_code, detail(r)["code"]) == (409, "invalid_transition")


def test_reject_with_reason_player_sees_it(client, auth, bot_headers, newcomer):
    headers, _ = auth("admin", "adm1")
    assert client.post(f"/admin/v1/players/{newcomer}/reject", json={}, headers=headers).status_code == 422
    r = client.post(
        f"/admin/v1/players/{newcomer}/reject", json={"reason": "Вас нет в клубе"}, headers=headers
    )
    assert r.json()["player"]["account_status"] == "rejected"
    profile = client.get("/bot/v1/users/10", headers=bot_headers).json()
    assert profile["poker_account"]["reject_reason"] == "Вас нет в клубе"


def test_unknown_player_is_404(client, auth):
    headers, _ = auth("admin", "adm1")
    assert client.get("/admin/v1/players/9999", headers=headers).status_code == 404
    assert client.post("/admin/v1/players/9999/approve", headers=headers).status_code == 404


def test_player_without_account_cannot_be_approved(client, db, auth):
    players.register_user(db, telegram_id=11, username=None, first_name="Без ID")
    uid = db.scalar(select(User.id).where(User.telegram_id == 11))
    headers, _ = auth("admin", "adm1")
    r = client.post(f"/admin/v1/players/{uid}/approve", headers=headers)
    assert (r.status_code, detail(r)["code"]) == (404, "account_not_found")


def test_list_players_filters(client, auth, newcomer):
    headers, _ = auth("admin", "adm1")
    get = lambda **p: client.get("/admin/v1/players", params=p, headers=headers).json()
    assert get(account_status="pending")["total"] == 1
    assert get(account_status="approved")["total"] == 0
    assert get(q="1111")["total"] == 1 and get(q="newbie")["total"] == 1 and get(q="10")["total"] == 1
    assert get(user_status="blocked")["total"] == 0


def test_unblock_after_duplicate_id_attempts(client, db, auth, bot_headers, newcomer):
    admin, _ = auth("admin", "adm1")
    client.post(f"/admin/v1/players/{newcomer}/approve", headers=admin)
    players.register_user(db, telegram_id=20, username=None, first_name="Нарушитель")
    for _ in range(2):
        try:
            players.link_poker_account(db, telegram_id=20, raw_player_id="1111-2222")
        except Exception:
            pass
    offender = db.scalar(select(User).where(User.telegram_id == 20))
    assert offender.status == UserStatus.BLOCKED
    detail_view = client.get(f"/admin/v1/players/{offender.id}", headers=admin).json()
    assert detail_view["block_reason"] and detail_view["duplicate_id_attempts"] == 2
    assert client.get("/bot/v1/users/20/deposits", headers=bot_headers).status_code == 403
    r = client.post(f"/admin/v1/players/{offender.id}/unblock", headers=admin)
    assert r.json()["player"]["user_status"] == "active"
    assert client.get("/bot/v1/users/20/deposits", headers=bot_headers).status_code != 403
    again = client.post(f"/admin/v1/players/{offender.id}/unblock", headers=admin)
    assert again.status_code == 409


def test_player_card_has_request_history(client, auth, db, provider, newcomer):
    admin, _ = auth("admin", "adm1")
    client.post(f"/admin/v1/players/{newcomer}/approve", headers=admin)
    from app.services import deposits

    deposits.create_deposit(
        db, telegram_id=10, method="fiat", amount=5000, idempotency_key="key-00000001"
    )
    card = client.get(f"/admin/v1/players/{newcomer}", headers=admin).json()
    assert len(card["deposits"]) == 1 and card["withdrawals"] == []


# ---------- настройки ----------


def put(client, headers, **settings):
    return client.put("/admin/v1/settings", json={"settings": settings}, headers=headers)


def test_settings_need_rights(client, auth):
    op, _ = auth("operator", "op1")
    fin, _ = auth("finance", "fin1")
    assert client.get("/admin/v1/settings").status_code == 401
    for headers in (op, fin):
        assert client.get("/admin/v1/settings", headers=headers).status_code == 403
        assert put(client, headers, deposit_min_amount=2000).status_code == 403


def test_view_settings(client, auth):
    headers, _ = auth("admin", "adm1")
    body = client.get("/admin/v1/settings", headers=headers).json()
    assert body["deposit_min_amount"] == 1000 and body["withdrawal_max_amount"] == 2_000_000
    assert body["deposit_commission_percent"] == "0" and body["usdt_rate_mode"] == "auto"
    assert body["usdt_rate"]["usable"] is None


def test_limits_change_reaches_bot_and_is_audited(client, db, auth, bot_headers):
    headers, admin = auth("admin", "adm1")
    r = put(client, headers, deposit_min_amount=5000, deposit_max_amount=100000)
    assert r.status_code == 200 and r.json()["deposit_min_amount"] == 5000
    limits = client.get("/bot/v1/settings/limits", headers=bot_headers).json()
    assert limits["deposit"] == {"min": 5000, "max": 100000}
    log = db.scalars(select(AuditLog).where(AuditLog.action == "settings.updated")).one()
    assert log.staff_id == admin.id
    assert log.details["deposit_min_amount"] == {"from": 1000, "to": "5000"}


@pytest.mark.parametrize(
    "settings",
    [
        {"deposit_min_amount": 0},
        {"deposit_min_amount": -5},
        {"deposit_min_amount": "5000"},
        {"deposit_min_amount": True},
        {"deposit_min_amount": 10**10},
        {"deposit_receipt_timeout_minutes": 0},
        {"receipt_retention_days": 1000},
        {"deposit_commission_percent": "51"},
        {"deposit_commission_percent": "-51"},
        {"deposit_commission_percent": "1.234"},
        {"deposit_commission_percent": "abc"},
        {"usdt_rate_mode": "sometimes"},
        {"unknown_key": 1},
        {"usdt_kzt_rate": "500"},  # напрямую ключ курса менять нельзя
        {"deposit_min_amount": 3_000_000},  # больше максимума 2 000 000
        {"withdrawal_max_amount": 500},  # меньше минимума 1000
    ],
)
def test_invalid_settings_are_rejected_and_nothing_changes(client, auth, settings):
    headers, _ = auth("admin", "adm1")
    before = client.get("/admin/v1/settings", headers=headers).json()
    assert put(client, headers, **settings).status_code == 422
    assert client.get("/admin/v1/settings", headers=headers).json() == before


def test_partial_failure_changes_nothing(client, auth):
    headers, _ = auth("admin", "adm1")
    r = put(client, headers, deposit_commission_percent="2", deposit_min_amount=-1)
    assert r.status_code == 422
    assert client.get("/admin/v1/settings", headers=headers).json()["deposit_commission_percent"] == "0"


def test_empty_update_is_422(client, auth):
    headers, _ = auth("admin", "adm1")
    assert client.put("/admin/v1/settings", json={"settings": {}}, headers=headers).status_code == 422


def test_signed_percent_applies_to_new_requests(client, db, auth, bot_headers, provider):
    headers, _ = auth("admin", "adm1")
    assert put(client, headers, deposit_commission_percent="-2.5").json()["deposit_commission_percent"] == "-2.5"
    assert client.get("/bot/v1/settings/limits", headers=bot_headers).json()["commission"]["deposit"] == "-2.5"
    players.register_user(db, telegram_id=30, username=None, first_name="Игрок")
    acc = players.link_poker_account(db, telegram_id=30, raw_player_id="3333-4444")
    players.approve_poker_account(db, account_id=acc.id)
    r = client.post(
        "/bot/v1/users/30/deposits",
        json={"method": "fiat", "amount": 10000, "idempotency_key": "key-00000001"},
        headers=bot_headers,
    )
    assert (r.json()["commission_amount"], r.json()["credit_amount"]) == (-250, 9750)


def test_manual_rate_flow(client, auth, bot_headers, db):
    headers, _ = auth("owner", "own1")
    # Курс без ручного режима не принимается.
    assert put(client, headers, usdt_manual_rate="500").status_code == 422
    # Ручной режим без курса оставил бы крипту без курса.
    assert put(client, headers, usdt_rate_mode="manual").status_code == 422
    ok = put(client, headers, usdt_rate_mode="manual", usdt_manual_rate="505.5")
    assert ok.status_code == 200 and ok.json()["usdt_rate"]["usable"] == "505.5"
    assert ok.json()["usdt_rate"]["source"] == "manual:own1"
    quote = client.get("/bot/v1/quotes/usdt-deposit?usdt_amount=10", headers=bot_headers)
    assert quote.status_code == 200 and quote.json()["kzt_amount"] == 5055
    for bad in ("0", "-1", "abc", "1.234", "NaN"):
        assert put(client, headers, usdt_manual_rate=bad).status_code == 422


def test_switching_back_to_auto_does_not_keep_manual_rate_fresh(client, auth, bot_headers):
    headers, _ = auth("owner", "own1")
    put(client, headers, usdt_rate_mode="manual", usdt_manual_rate="505.5")
    back = put(client, headers, usdt_rate_mode="auto")
    assert back.status_code == 200 and back.json()["usdt_rate"]["usable"] is None
    quote = client.get("/bot/v1/quotes/usdt-deposit?usdt_amount=10", headers=bot_headers)
    assert (quote.status_code, detail(quote)["code"]) == (503, "exchange_rate_unavailable")


# ---------- банки ----------


def test_banks_admin_flow(client, auth, bot_headers, banks):
    headers, _ = auth("admin", "adm1")
    listed = client.get("/admin/v1/banks", headers=headers).json()
    assert len(listed) == 5
    created = client.post("/admin/v1/banks", json={"name": "  Jusan   Bank "}, headers=headers)
    assert (created.status_code, created.json()["name"]) == (201, "Jusan Bank")
    assert client.post("/admin/v1/banks", json={"name": "Jusan Bank"}, headers=headers).status_code == 409
    kaspi = next(b for b in listed if b["name"] == "Kaspi Bank")
    off = client.patch(f"/admin/v1/banks/{kaspi['id']}", json={"is_active": False}, headers=headers)
    assert off.json()["is_active"] is False
    names = [b["name"] for b in client.get("/bot/v1/banks", headers=bot_headers).json()]
    assert "Kaspi Bank" not in names and "Jusan Bank" in names
    assert client.patch("/admin/v1/banks/9999", json={"is_active": True}, headers=headers).status_code == 404
    clash = client.patch(f"/admin/v1/banks/{kaspi['id']}", json={"name": "Halyk Bank"}, headers=headers)
    assert clash.status_code == 409


def test_banks_need_edit_right(client, auth, banks):
    op, _ = auth("operator", "op1")
    assert client.get("/admin/v1/banks", headers=op).status_code == 403
    assert client.post("/admin/v1/banks", json={"name": "X Bank"}, headers=op).status_code == 403


# ---------- журнал аудита ----------


def test_audit_log_is_visible_only_to_owner_and_admin(client, auth, newcomer):
    owner, _ = auth("owner", "own1")
    op, _ = auth("operator", "op1")
    client.post(f"/admin/v1/players/{newcomer}/approve", headers=owner)
    assert client.get("/admin/v1/audit", headers=op).status_code == 403
    assert client.get("/admin/v1/audit").status_code == 401
    page = client.get("/admin/v1/audit", params={"action": "player.approved"}, headers=owner).json()
    assert page["total"] == 1 and page["items"][0]["entity_type"] == "poker_account"
    assert client.get("/admin/v1/audit?limit=1000", headers=owner).status_code == 422


def test_audit_never_contains_secrets(client, db, auth, newcomer):
    owner, _ = auth("owner", "own1")
    put(client, owner, deposit_commission_percent="1")
    client.post(
        "/admin/v1/staff",
        json={"login": "newop", "display_name": "N", "role": "operator", "password": "super-secret-password"},
        headers=owner,
    )
    dump = " ".join(f"{r.details} {r.entity_id}" for r in db.scalars(select(AuditLog)).all())
    assert "super-secret-password" not in dump and "password_hash" not in dump
